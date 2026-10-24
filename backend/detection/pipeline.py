"""
The detection pipeline: turns one user's activity on one day into a risk decision.

    activities of the day
        -> features            (ai/features.py)
        -> baseline            (baseline.py, history BEFORE the day only)
        -> rule engine         (rules.py)
        -> AI anomaly score    (anomaly_service.py -> ai/model.py)
        -> risk score          (risk.py)
        -> alert or no alert   (alerts.py)
        -> saved as an AnalysisResult row (the user's risk history)

`analyze_user_day` is called automatically after activities are ingested, and can be
called manually through POST /api/v1/analysis/run.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.features import compute_daily_features
from backend.config import Settings, get_settings
from backend.detection import anomaly_service
from backend.detection.alerts import apply_alert_policy
from backend.detection.baseline import Baseline, compute_baseline
from backend.detection.risk import calculate_risk, risk_level
from backend.detection.rule_config import BASELINE_HISTORY_DAYS, DEFAULT_RULE_SETTINGS, MIN_INDIVIDUAL_DAYS
from backend.detection.rules import evaluate_rules
from backend.models import Activity, AnalysisResult, BehavioralProfile, MonitoredUser, RuleSetting, utc_now
from backend.timeutils import org_today

logger = logging.getLogger(__name__)

CURRENT_RISK_DAYS = 7  # a user's "current risk" is their highest daily risk in the last 7 days


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def activity_to_event(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "timestamp": activity.timestamp,
        "event_type": activity.event_type,
        "resource": activity.resource,
        "sensitivity": activity.sensitivity,
        "file_size_bytes": activity.file_size_bytes,
    }


def load_rule_settings(db: Session) -> dict[str, dict]:
    """Defaults from rule_config.py, overridden by whatever an admin saved in the database."""
    settings = {
        rule_id: {"enabled": True, "weight": values["weight"], "parameters": dict(values["parameters"])}
        for rule_id, values in DEFAULT_RULE_SETTINGS.items()
    }
    for row in db.scalars(select(RuleSetting)):
        if row.rule_id in settings:
            settings[row.rule_id] = {"enabled": row.enabled, "weight": row.weight,
                                     "parameters": {**settings[row.rule_id]["parameters"], **row.parameters}}
    return settings


def daily_feature_history(activities: list[Activity]) -> dict[tuple[int, date], dict]:
    """Group activities by (user, day) and compute the features of each group."""
    groups: dict[tuple[int, date], list[dict]] = defaultdict(list)
    for activity in activities:
        groups[(activity.user_id, activity.timestamp.date())].append(activity_to_event(activity))
    return {key: compute_daily_features(events) for key, events in groups.items()}


def build_user_baseline(db: Session, user: MonitoredUser, day: date) -> Baseline:
    history_start = day - timedelta(days=BASELINE_HISTORY_DAYS)
    start, _ = day_bounds(history_start)
    end, _ = day_bounds(day)  # strictly before the analyzed day: no future information

    user_activities = list(db.scalars(
        select(Activity).where(Activity.user_id == user.id, Activity.timestamp >= start, Activity.timestamp < end)
    ))
    user_history = list(daily_feature_history(user_activities).values())
    known_resources = {activity.resource for activity in user_activities if activity.resource}

    peer_history: list[dict] = []
    if len(user_history) < MIN_INDIVIDUAL_DAYS:  # only look at peers when they are needed
        peer_activities = list(db.scalars(
            select(Activity).join(MonitoredUser)
            .where(MonitoredUser.department == user.department, MonitoredUser.id != user.id,
                   Activity.timestamp >= start, Activity.timestamp < end)
        ))
        peer_history = list(daily_feature_history(peer_activities).values())

    return compute_baseline(user_history, peer_history, known_resources, history_start, day - timedelta(days=1))


def save_profile(db: Session, user: MonitoredUser, baseline: Baseline) -> None:
    profile = db.scalar(select(BehavioralProfile).where(BehavioralProfile.user_id == user.id))
    if profile is None:
        profile = BehavioralProfile(user_id=user.id)
        db.add(profile)
    profile.baseline_type = baseline.baseline_type
    profile.window_start = baseline.window_start
    profile.window_end = baseline.window_end
    profile.observation_days = baseline.observation_days
    profile.feature_means = baseline.means
    profile.feature_stds = baseline.stds
    profile.generated_at = utc_now()


def refresh_current_risk(db: Session, user: MonitoredUser, settings: Settings, today: date | None = None) -> None:
    today = today or org_today()
    since = today - timedelta(days=CURRENT_RISK_DAYS - 1)
    highest = db.scalar(
        select(func.max(AnalysisResult.risk_score))
        .where(AnalysisResult.user_id == user.id, AnalysisResult.window_date >= since)
    )
    user.current_risk_score = float(highest or 0)
    user.current_risk_level = risk_level(user.current_risk_score, settings)


def analyze_user_day(db: Session, user: MonitoredUser, day: date, settings: Settings | None = None,
                     update_profile: bool = True) -> AnalysisResult | None:
    """Run the full pipeline for one user-day and commit the result. Returns None if the day has no activity."""
    settings = settings or get_settings()
    start, end = day_bounds(day)
    day_activities = list(db.scalars(
        select(Activity).where(Activity.user_id == user.id, Activity.timestamp >= start, Activity.timestamp < end)
        .order_by(Activity.timestamp)
    ))
    if not day_activities:
        return None

    events = [activity_to_event(activity) for activity in day_activities]
    features = compute_daily_features(events)
    baseline = build_user_baseline(db, user, day)
    rule_result = evaluate_rules(features, events, baseline, user.job_role, load_rule_settings(db))
    ai_result = anomaly_service.score_features(features)
    ai_score = ai_result.get("anomaly_score") if ai_result["status"] == "OK" else None
    risk = calculate_risk(rule_result["rule_score"], ai_score, rule_result["triggered_rules"], settings)

    analysis = db.scalar(select(AnalysisResult).where(AnalysisResult.user_id == user.id, AnalysisResult.window_date == day))
    if analysis is None:
        analysis = AnalysisResult(user_id=user.id, window_date=day)
        db.add(analysis)
    analysis.event_count = len(events)
    analysis.features = features
    analysis.baseline_type = baseline.baseline_type
    analysis.rule_score = rule_result["rule_score"]
    analysis.triggered_rules = rule_result["triggered_rules"]
    analysis.ai_status = ai_result["status"]
    analysis.ai_is_anomaly = ai_result.get("is_anomaly")
    analysis.ai_score = ai_score
    analysis.ai_raw_score = ai_result.get("raw_score")
    analysis.model_version = ai_result.get("model_version")
    analysis.risk_score = risk["risk_score"]
    analysis.risk_level = risk["risk_level"]
    analysis.score_breakdown = {**risk["breakdown"], "ai_unavailable_reason": ai_result.get("reason")}
    analysis.analyzed_at = utc_now()

    alert = apply_alert_policy(db, user, day, analysis, day_activities, rule_result["matched_event_ids"], settings)
    analysis.alert_id = alert.id if alert else None

    if update_profile:
        save_profile(db, user, baseline)
    db.flush()
    refresh_current_risk(db, user, settings)
    db.commit()
    return analysis


def analyze_days(db: Session, user_days: set[tuple[int, date]], settings: Settings | None = None) -> list[AnalysisResult]:
    """Analyze several user-days in time order (older days first, so baselines build up correctly)."""
    results = []
    for user_id, day in sorted(user_days, key=lambda pair: (pair[1], pair[0])):
        user = db.get(MonitoredUser, user_id)
        if user is None:
            continue
        result = analyze_user_day(db, user, day, settings)
        if result is not None:
            results.append(result)
    return results
