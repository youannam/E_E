"""Monitored users (the synthetic employees whose activity is analyzed)."""

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.models import Account, Activity, Alert, AlertHistory, AnalysisResult, BehavioralProfile, Device, MonitoredUser, alert_activities
from backend.routers.common import Pagination, get_or_404, paginate
from backend.schemas import (
    ActivityOut,
    AlertSummary,
    BaselineOut,
    Page,
    RiskHistoryPoint,
    RiskLevel,
    UserCreate,
    UserUpdate,
    UserDetail,
    UserStatistics,
    UserSummary,
)
from backend.security import require_admin
from backend.rbac import default_job_permissions
from backend.serializers import activity_out, alert_counts_by_user, alert_summary, user_summary
from backend.timeutils import org_today

router = APIRouter(prefix="/users", tags=["Monitored users"])
STATISTICS_DAYS = 30


@router.get("", response_model=Page[UserSummary], summary="List monitored users")
def list_users(
    search: str | None = Query(None, max_length=80, description="Part of the username"),
    department: str | None = Query(None, max_length=60),
    risk_level: RiskLevel | None = None,
    sort: str = Query("risk", pattern="^(risk|username|last_activity)$"),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    query = select(MonitoredUser)
    if search:
        query = query.where(MonitoredUser.username.ilike(f"%{search}%"))
    if department:
        query = query.where(MonitoredUser.department == department)
    if risk_level:
        query = query.where(MonitoredUser.current_risk_level == risk_level)
    order = {
        "risk": [MonitoredUser.current_risk_score.desc(), MonitoredUser.username],
        "username": [MonitoredUser.username],
        "last_activity": [MonitoredUser.last_activity_at.desc()],
    }[sort]
    users, total = paginate(db, query.order_by(*order), pagination)
    counts = alert_counts_by_user(db, [user.id for user in users])
    return Page(items=[user_summary(user, counts) for user in users], total=total,
                page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=UserSummary, status_code=201, summary="Register a monitored user (admin)")
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    if db.scalar(select(MonitoredUser).where(MonitoredUser.username == body.username)):
        raise HTTPException(status_code=409, detail=f"User '{body.username}' already exists")
    payload = body.model_dump()
    payload["job_permissions"] = payload.get("job_permissions") or default_job_permissions(payload.get("job_role"))
    user = MonitoredUser(**payload)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists")
    record_audit(db, admin.username, "MONITORED_USER_CREATED", "monitored_user", user.id, {"username": user.username})
    db.commit()
    return user_summary(user, {})


@router.get("/{user_id}", response_model=UserDetail, summary="User profile, baseline and statistics")
def get_user(user_id: int, db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    user = get_or_404(db, MonitoredUser, user_id, "User")
    since = datetime.combine(org_today() - timedelta(days=STATISTICS_DAYS - 1), time.min)

    counts_by_type = dict(db.execute(
        select(Activity.event_type, func.count(Activity.id))
        .where(Activity.user_id == user_id, Activity.timestamp >= since).group_by(Activity.event_type)
    ).all())
    active_days = db.scalar(
        select(func.count(func.distinct(func.date(Activity.timestamp))))
        .where(Activity.user_id == user_id, Activity.timestamp >= since)
    ) or 0
    total_events = sum(counts_by_type.values())
    devices = list(db.scalars(select(Device.device_id).where(Device.user_id == user_id).order_by(Device.device_id)))

    profile = db.scalar(select(BehavioralProfile).where(BehavioralProfile.user_id == user_id))
    summary = user_summary(user, alert_counts_by_user(db, [user_id]))
    return UserDetail(
        **summary.model_dump(),
        profile=BaselineOut(
            baseline_type=profile.baseline_type, observation_days=profile.observation_days,
            window_start=profile.window_start, window_end=profile.window_end,
            feature_means=profile.feature_means, feature_stds=profile.feature_stds, generated_at=profile.generated_at,
        ) if profile else None,
        statistics=UserStatistics(
            period_days=STATISTICS_DAYS, event_counts=counts_by_type, active_days=active_days,
            average_events_per_active_day=round(total_events / active_days, 1) if active_days else 0.0,
            devices=devices,
        ),
    )


@router.get("/{user_id}/activities", response_model=Page[ActivityOut], summary="A user's activities, newest first")
def user_activities(user_id: int, pagination: Pagination = Depends(), db: Session = Depends(get_db),
                    _: Account = Depends(require_admin)):
    get_or_404(db, MonitoredUser, user_id, "User")
    query = select(Activity).where(Activity.user_id == user_id).order_by(Activity.timestamp.desc(), Activity.id.desc())
    rows, total = paginate(db, query, pagination)
    return Page(items=[activity_out(row) for row in rows], total=total,
                page=pagination.page, page_size=pagination.page_size)


@router.get("/{user_id}/alerts", response_model=Page[AlertSummary], summary="A user's alerts, newest first")
def user_alerts(user_id: int, pagination: Pagination = Depends(), db: Session = Depends(get_db),
                _: Account = Depends(require_admin)):
    get_or_404(db, MonitoredUser, user_id, "User")
    query = select(Alert).where(Alert.user_id == user_id).order_by(Alert.window_date.desc(), Alert.id.desc())
    rows, total = paginate(db, query, pagination)
    return Page(items=[alert_summary(row) for row in rows], total=total,
                page=pagination.page, page_size=pagination.page_size)


@router.get("/{user_id}/risk-history", response_model=list[RiskHistoryPoint], summary="Daily risk scores")
def risk_history(user_id: int, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
                 _: Account = Depends(require_admin)):
    get_or_404(db, MonitoredUser, user_id, "User")
    since = org_today() - timedelta(days=days - 1)
    rows = db.scalars(select(AnalysisResult).where(AnalysisResult.user_id == user_id,
                                                   AnalysisResult.window_date >= since)
                      .order_by(AnalysisResult.window_date))
    return [RiskHistoryPoint(window_date=row.window_date, risk_score=row.risk_score, risk_level=row.risk_level,
                             rule_score=row.rule_score, ai_score=row.ai_score, ai_is_anomaly=row.ai_is_anomaly,
                             event_count=row.event_count, alert_id=row.alert_id) for row in rows]


@router.patch("/{user_id}", response_model=UserSummary, summary="Edit a monitored employee (admin only)")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    user = get_or_404(db, MonitoredUser, user_id, "User")
    changes = body.model_dump(exclude_unset=True)
    if "job_role" in changes and "job_permissions" not in changes:
        changes["job_permissions"] = default_job_permissions(changes["job_role"])
    for field, value in changes.items():
        setattr(user, field, value)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists")
    record_audit(db, admin.username, "MONITORED_USER_UPDATED", "monitored_user", user.id, changes)
    db.commit()
    db.refresh(user)
    return user_summary(user, alert_counts_by_user(db, [user.id]))


@router.delete("/{user_id}", status_code=204, summary="Delete a monitored employee and its associated demo history (admin only)")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    user = get_or_404(db, MonitoredUser, user_id, "User")
    alert_ids = list(db.scalars(select(Alert.id).where(Alert.user_id == user_id)))
    if alert_ids:
        db.execute(delete(alert_activities).where(alert_activities.c.alert_id.in_(alert_ids)))
        db.execute(delete(AlertHistory).where(AlertHistory.alert_id.in_(alert_ids)))
        db.execute(delete(Alert).where(Alert.id.in_(alert_ids)))
    db.execute(delete(AnalysisResult).where(AnalysisResult.user_id == user_id))
    db.execute(delete(BehavioralProfile).where(BehavioralProfile.user_id == user_id))
    db.execute(delete(Device).where(Device.user_id == user_id))
    db.execute(delete(Activity).where(Activity.user_id == user_id))
    record_audit(db, admin.username, "MONITORED_USER_DELETED", "monitored_user", user.id,
                 {"username": user.username, "deleted_alerts": len(alert_ids)})
    db.delete(user)
    db.commit()
