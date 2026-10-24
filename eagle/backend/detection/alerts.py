"""
Alert generation and deduplication.

Alert policy: an alert is raised when the final risk score of a user-day reaches
ALERT_THRESHOLD (default 50 = HIGH). A CRITICAL rule always reaches it because of the
severity floor in risk.py.

Deduplication (one alert per user per day):
  Events usually arrive in bursts (e.g. 40 downloads in 10 minutes). Each batch re-analyses
  the whole day, so without deduplication one incident could create dozens of alerts.
  * If the user already has an OPEN or INVESTIGATING alert for that day, that alert is
    UPDATED with the newest analysis (scores, rules, evidence) instead of creating another.
  * If the alert for that day was already closed (RESOLVED or FALSE_POSITIVE), a new alert
    is created only when something NEW appears: a rule that was not in the closed alert,
    or a higher risk level. Otherwise the analyst's decision is respected.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models import Activity, Alert, AlertHistory, AnalysisResult, MonitoredUser

ACTIVE_STATUSES = ("OPEN", "INVESTIGATING")
CLOSED_STATUSES = ("RESOLVED", "FALSE_POSITIVE")
LEVEL_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
MAX_LINKED_ACTIVITIES = 200


def build_explanation(user: MonitoredUser, day: date, analysis: AnalysisResult) -> str:
    """Plain-English summary shown on the alert. It never claims the person is malicious."""
    lines = [
        f"{user.username} ({user.job_role}, {user.department}) on {day.isoformat()}: "
        f"risk score {analysis.risk_score:g}/100 ({analysis.risk_level}).",
    ]
    if analysis.triggered_rules:
        lines.append(f"Cybersecurity rules: {len(analysis.triggered_rules)} triggered, rule score {analysis.rule_score:g}/100.")
        for rule in analysis.triggered_rules:
            lines.append(f"- {rule['name']} [{rule['severity']}]: {rule['reason']}")
    else:
        lines.append("Cybersecurity rules: none triggered.")

    if analysis.ai_status == "OK":
        verdict = "unusual compared with the normal days it was trained on" if analysis.ai_is_anomaly \
            else "within the range of normal days it was trained on"
        lines.append(f"AI model ({analysis.model_version}): anomaly score {analysis.ai_score:g}/100, {verdict}.")
    else:
        lines.append("AI model: unavailable, the score is based on rules only.")

    lines.append(f"How the score was calculated: {analysis.score_breakdown.get('formula', '')}.")
    lines.append("This is an indicator for review, not proof of malicious intent. An analyst must investigate.")
    return "\n".join(lines)


def find_alert_for_day(db: Session, user_id: int, day: date) -> Alert | None:
    # populate_existing re-reads the row from the database, so a status change made by an
    # analyst in another session (another request) is always seen here.
    return db.scalar(
        select(Alert).where(Alert.user_id == user_id, Alert.window_date == day).order_by(Alert.id.desc())
        .execution_options(populate_existing=True)
    )


def linked_activities(db: Session, day_activities: list[Activity], matched_ids: list[int]) -> list[Activity]:
    """Evidence for the alert: the events that triggered rules, or (AI-only alerts) the day's events."""
    if matched_ids:
        wanted = set(matched_ids)
        chosen = [activity for activity in day_activities if activity.id in wanted]
    else:
        chosen = list(day_activities)
    return chosen[:MAX_LINKED_ACTIVITIES]


def copy_analysis_to_alert(alert: Alert, analysis: AnalysisResult, explanation: str) -> None:
    alert.risk_score = analysis.risk_score
    alert.risk_level = analysis.risk_level
    alert.rule_score = analysis.rule_score
    alert.ai_status = analysis.ai_status
    alert.ai_is_anomaly = analysis.ai_is_anomaly
    alert.ai_score = analysis.ai_score
    alert.model_version = analysis.model_version
    alert.triggered_rules = analysis.triggered_rules
    alert.explanation = explanation


def is_new_information(closed_alert: Alert, analysis: AnalysisResult) -> bool:
    old_rules = {rule["rule_id"] for rule in closed_alert.triggered_rules}
    new_rules = {rule["rule_id"] for rule in analysis.triggered_rules}
    level_increased = LEVEL_ORDER.index(analysis.risk_level) > LEVEL_ORDER.index(closed_alert.risk_level)
    return bool(new_rules - old_rules) or level_increased


def apply_alert_policy(db: Session, user: MonitoredUser, day: date, analysis: AnalysisResult,
                       day_activities: list[Activity], matched_ids: list[int], settings: Settings) -> Alert | None:
    """Create, update or skip an alert for this analysis. Returns the alert that covers the day, if any."""
    existing = find_alert_for_day(db, user.id, day)

    if analysis.risk_score < settings.alert_threshold:
        # Below the policy: never create an alert. Keep any existing alert as the analyst left it.
        return existing

    explanation = build_explanation(user, day, analysis)
    evidence = linked_activities(db, day_activities, matched_ids)

    if existing and existing.status in ACTIVE_STATUSES:
        old_level, old_rules = existing.risk_level, {rule["rule_id"] for rule in existing.triggered_rules}
        copy_analysis_to_alert(existing, analysis, explanation)
        existing.occurrence_count += 1
        already_linked = {activity.id for activity in existing.activities}
        for activity in evidence:
            if activity.id not in already_linked and len(existing.activities) < MAX_LINKED_ACTIVITIES:
                existing.activities.append(activity)
        new_rules = {rule["rule_id"] for rule in analysis.triggered_rules} - old_rules
        if new_rules or old_level != analysis.risk_level:
            note = f"New detection activity: risk {old_level} -> {analysis.risk_level}"
            if new_rules:
                note += f"; new rules: {', '.join(sorted(new_rules))}"
            existing.history.append(AlertHistory(action="UPDATED_BY_DETECTION", note=note))
        return existing

    if existing and existing.status in CLOSED_STATUSES and not is_new_information(existing, analysis):
        return existing  # the analyst already handled this; nothing new to report

    alert = Alert(user_id=user.id, window_date=day, status="OPEN", explanation=explanation)
    copy_analysis_to_alert(alert, analysis, explanation)
    alert.activities = evidence
    note = "Created by the detection pipeline"
    if existing:
        note += f" (new information after alert #{existing.id} was closed)"
    alert.history = [AlertHistory(action="CREATED", new_status="OPEN", note=note)]
    db.add(alert)
    db.flush()
    return alert
