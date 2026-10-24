"""
Convert database rows into API response models.

Kept in one place so the same object always looks the same in every endpoint
(for example an alert in /alerts, /users/{id}/alerts and the simulator response).
"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.models import Activity, Alert, AlertHistory, AnalysisResult, MonitoredUser
from backend.schemas import (
    ActivityOut,
    AlertDetail,
    AlertHistoryOut,
    AlertSummary,
    AnalysisOut,
    TriggeredRule,
    UserSummary,
)


def activity_out(activity: Activity) -> ActivityOut:
    return ActivityOut(
        id=activity.id, user_id=activity.user_id, username=activity.user.username, timestamp=activity.timestamp,
        event_type=activity.event_type, resource=activity.resource, sensitivity=activity.sensitivity,
        file_size_bytes=activity.file_size_bytes, device_id=activity.device_id, source=activity.source,
        is_simulated=activity.is_simulated, details=activity.details or {},
    )


def analysis_out(db: Session, analysis: AnalysisResult) -> AnalysisOut:
    user = db.get(MonitoredUser, analysis.user_id)
    return AnalysisOut(
        id=analysis.id, user_id=analysis.user_id, username=user.username, window_date=analysis.window_date,
        event_count=analysis.event_count, features=analysis.features, baseline_type=analysis.baseline_type,
        rule_score=analysis.rule_score, triggered_rules=[TriggeredRule(**rule) for rule in analysis.triggered_rules],
        ai_status=analysis.ai_status, ai_is_anomaly=analysis.ai_is_anomaly, ai_score=analysis.ai_score,
        ai_raw_score=analysis.ai_raw_score, model_version=analysis.model_version, risk_score=analysis.risk_score,
        risk_level=analysis.risk_level, score_breakdown=analysis.score_breakdown or {}, alert_id=analysis.alert_id,
        analyzed_at=analysis.analyzed_at,
    )


def alert_counts_by_user(db: Session, user_ids: list[int]) -> dict[int, tuple[int, int]]:
    """{user_id: (all alerts, open or investigating alerts)} in one query."""
    if not user_ids:
        return {}
    open_case = case((Alert.status.in_(("OPEN", "INVESTIGATING")), 1), else_=0)
    rows = db.execute(
        select(Alert.user_id, func.count(Alert.id), func.sum(open_case))
        .where(Alert.user_id.in_(user_ids)).group_by(Alert.user_id)
    )
    return {user_id: (total, int(open_count or 0)) for user_id, total, open_count in rows}


def user_summary(user: MonitoredUser, counts: dict[int, tuple[int, int]]) -> UserSummary:
    total, open_count = counts.get(user.id, (0, 0))
    return UserSummary(
        id=user.id, username=user.username, email=user.email, department=user.department, job_role=user.job_role, job_permissions=user.job_permissions or [],
        status=user.status, is_synthetic=user.is_synthetic, current_risk_score=user.current_risk_score,
        current_risk_level=user.current_risk_level, alert_count=total, open_alert_count=open_count,
        last_activity_at=user.last_activity_at, last_login=user.last_login,
    )


def alert_summary(alert: Alert) -> AlertSummary:
    return AlertSummary(
        id=alert.id, user_id=alert.user_id, username=alert.user.username, department=alert.user.department,
        window_date=alert.window_date, created_at=alert.created_at, updated_at=alert.updated_at,
        risk_score=alert.risk_score, risk_level=alert.risk_level, rule_score=alert.rule_score,
        ai_status=alert.ai_status, ai_score=alert.ai_score, ai_is_anomaly=alert.ai_is_anomaly,
        model_version=alert.model_version, status=alert.status,
        triggered_rule_ids=[rule["rule_id"] for rule in alert.triggered_rules],
        occurrence_count=alert.occurrence_count,
        assigned_to=alert.assigned_to.username if alert.assigned_to else None,
    )


def history_out(entry: AlertHistory) -> AlertHistoryOut:
    return AlertHistoryOut(
        id=entry.id, action=entry.action, old_status=entry.old_status, new_status=entry.new_status,
        note=entry.note, actor=entry.account.username if entry.account else "system", created_at=entry.created_at,
    )


def alert_detail(db: Session, alert: Alert) -> AlertDetail:
    analysis = db.scalar(select(AnalysisResult).where(
        AnalysisResult.user_id == alert.user_id, AnalysisResult.window_date == alert.window_date))
    counts = alert_counts_by_user(db, [alert.user_id])
    return AlertDetail(
        **alert_summary(alert).model_dump(),
        triggered_rules=[TriggeredRule(**rule) for rule in alert.triggered_rules],
        explanation=alert.explanation, resolved_at=alert.resolved_at, resolution_notes=alert.resolution_notes,
        user=user_summary(alert.user, counts),
        activities=[activity_out(activity) for activity in alert.activities],
        history=[history_out(entry) for entry in alert.history],
        analysis=analysis_out(db, analysis) if analysis else None,
    )
