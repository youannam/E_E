"""Numbers for the dashboard overview. Everything is counted from the database at request time."""

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.detection import anomaly_service
from backend.models import Account, Activity, Alert, MonitoredUser
from backend.schemas import ActivityDistributionItem, AlertsOverTimeItem, DashboardSummary, RiskDistributionItem
from backend.security import require_admin
from backend.timeutils import org_now, org_today

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

ACTIVE_USER_DAYS = 7
LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    now = org_now()
    active_since = now - timedelta(days=ACTIVE_USER_DAYS)

    def count(query) -> int:
        return db.scalar(query) or 0

    detector = anomaly_service.get_detector()
    return DashboardSummary(
        total_users=count(select(func.count(MonitoredUser.id))),
        active_users=count(select(func.count(MonitoredUser.id)).where(MonitoredUser.last_activity_at >= active_since)),
        active_users_definition=f"Users with at least one activity in the last {ACTIVE_USER_DAYS} days",
        open_alerts=count(select(func.count(Alert.id)).where(Alert.status == "OPEN")),
        investigating_alerts=count(select(func.count(Alert.id)).where(Alert.status == "INVESTIGATING")),
        critical_alerts=count(select(func.count(Alert.id)).where(
            Alert.risk_level == "CRITICAL", Alert.status.in_(("OPEN", "INVESTIGATING")))),
        high_risk_users=count(select(func.count(MonitoredUser.id)).where(
            MonitoredUser.current_risk_level.in_(("HIGH", "CRITICAL")))),
        activities_last_24h=count(select(func.count(Activity.id)).where(Activity.timestamp >= now - timedelta(hours=24))),
        model_loaded=detector is not None,
        model_version=detector.version if detector else None,
    )


@router.get("/risk-distribution", response_model=list[RiskDistributionItem], summary="Users per current risk level")
def risk_distribution(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    counts = dict(db.execute(select(MonitoredUser.current_risk_level, func.count(MonitoredUser.id))
                             .group_by(MonitoredUser.current_risk_level)).all())
    return [RiskDistributionItem(level=level, count=counts.get(level, 0)) for level in LEVELS]


@router.get("/alerts-over-time", response_model=list[AlertsOverTimeItem],
            summary="Alerts per activity day and risk level")
def alerts_over_time(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db),
                     _: Account = Depends(require_admin)):
    first_day = org_today() - timedelta(days=days - 1)
    rows = db.execute(select(Alert.window_date, Alert.risk_level, func.count(Alert.id))
                      .where(Alert.window_date >= first_day).group_by(Alert.window_date, Alert.risk_level))
    table = {first_day + timedelta(days=offset): {level: 0 for level in LEVELS} for offset in range(days)}
    for day, level, count in rows:
        if day in table:
            table[day][level] = count
    return [AlertsOverTimeItem(date=day, total=sum(levels.values()), **levels) for day, levels in table.items()]


@router.get("/activity-distribution", response_model=list[ActivityDistributionItem], summary="Events per type")
def activity_distribution(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db),
                          _: Account = Depends(require_admin)):
    since = datetime.combine(org_today() - timedelta(days=days - 1), time.min)
    rows = db.execute(select(Activity.event_type, func.count(Activity.id)).where(Activity.timestamp >= since)
                      .group_by(Activity.event_type).order_by(func.count(Activity.id).desc()))
    return [ActivityDistributionItem(event_type=event_type, count=count) for event_type, count in rows]
