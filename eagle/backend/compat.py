"""Compatibility API for the preserved legacy web and Flutter clients.

All data and detection are owned by the modular SQLAlchemy backend. This adapter only
translates response/request shapes; it does not maintain a second database or AI pipeline.
"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.models import Account, Activity, Alert, MonitoredUser, utc_now
from backend.routers.common import get_or_404
from backend.schemas import UserCreate
from backend.security import get_current_account, require_admin, require_analyst_or_admin
from backend.serializers import alert_summary
from backend.config import get_settings
from backend.security import create_access_token, login_limiter, verify_against_dummy, verify_password
from sqlalchemy import or_

router = APIRouter(tags=["Legacy UI compatibility"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_FRONTEND = PROJECT_ROOT / "legacy_frontend"


def _activity_out(row: Activity) -> dict:
    return {
        "id": row.id, "user_id": row.user_id, "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "event_type": row.event_type, "file_name": row.resource, "resource": row.resource,
        "file_sensitivity": row.sensitivity, "sensitivity": row.sensitivity,
        "file_size_bytes": row.file_size_bytes, "device_id": row.device_id,
        "source": row.source, "is_simulated": row.is_simulated, "details": row.details or {},
    }


def _user_out(user: MonitoredUser) -> dict:
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "department": user.department, "job_role": user.job_role,
        "status": user.status.lower(), "role": "analyst", "is_synthetic": user.is_synthetic,
        "current_risk_score": user.current_risk_score, "current_risk_level": user.current_risk_level,
        "alert_count": user.alert_count if hasattr(user, "alert_count") else None,
        "open_alert_count": user.open_alert_count if hasattr(user, "open_alert_count") else None,
        "last_activity_at": user.last_activity_at.isoformat() if user.last_activity_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def _alert_out(alert: Alert) -> dict:
    return {
        "id": alert.id, "user_id": alert.user_id, "username": alert.user.username,
        "department": alert.user.department, "risk_score": alert.risk_score,
        "risk_level": alert.risk_level, "rule_score": alert.rule_score,
        "ai_score": alert.ai_score, "ai_anomaly": alert.ai_is_anomaly,
        "ai_is_anomaly": alert.ai_is_anomaly, "status": alert.status,
        "timestamp": alert.created_at.isoformat() if alert.created_at else None,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "reason": alert.explanation, "explanation": alert.explanation,
        "triggered_rules": alert.triggered_rules or [], "model_version": alert.model_version,
    }


@router.post("/auth/login", include_in_schema=False)
def legacy_login(body: dict, db: Session = Depends(get_db)):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    key = username.lower()
    if not username or not password:
        raise HTTPException(422, "Username and password are required")
    if login_limiter.is_blocked(key):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    account = db.scalar(select(Account).where(or_(Account.username == username, Account.email == username)))
    valid = bool(account and account.is_active and verify_password(password, account.password_hash))
    if not valid:
        if account is None:
            verify_against_dummy(password)
        login_limiter.record_failure(key)
        record_audit(db, username[:50], "LOGIN_FAILED", "account")
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    login_limiter.reset(key)
    account.last_login = utc_now()
    record_audit(db, account.username, "LOGIN", "account", account.id)
    db.commit()
    token, expires = create_access_token(account)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires,
            "account": {"id": account.id, "username": account.username, "role": account.role}}


@router.post("/auth/register", include_in_schema=False)
def disabled_public_registration():
    raise HTTPException(status_code=403, detail="Public account registration is disabled. Ask an administrator to create an account.")


@router.post("/auth/forgot-password", include_in_schema=False)
def disabled_unsafe_password_reset():
    raise HTTPException(status_code=403, detail="For security, password resets must be performed by an administrator after verifying your identity.")


@router.get("/dashboard/statistics", include_in_schema=False)
def legacy_dashboard(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    total = db.scalar(select(func.count(MonitoredUser.id))) or 0
    active = db.scalar(select(func.count(MonitoredUser.id)).where(MonitoredUser.status == "ACTIVE")) or 0
    open_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.status.in_(("OPEN", "INVESTIGATING")))) or 0
    high_risk = db.scalar(select(func.count(MonitoredUser.id)).where(MonitoredUser.current_risk_level.in_(("HIGH", "CRITICAL")))) or 0
    critical = db.scalar(select(func.count(Alert.id)).where(Alert.risk_level == "CRITICAL", Alert.status.in_(("OPEN", "INVESTIGATING")))) or 0
    return {"total_users": total, "active_users": active, "open_alerts": open_alerts,
            "high_risk_users": high_risk, "critical_alerts": critical}


@router.get("/users", include_in_schema=False)
def legacy_users(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    rows = db.scalars(select(MonitoredUser).where(MonitoredUser.status == "ACTIVE").order_by(MonitoredUser.username)).all()
    return [_user_out(row) for row in rows]


@router.post("/users", include_in_schema=False)
def legacy_create_user(body: dict, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    payload = {"username": str(body.get("username", "")).strip().lower(),
               "email": (str(body.get("email", "")).strip() or None),
               "department": str(body.get("department", "General")).strip() or "General",
               "job_role": str(body.get("job_role", "Employee")).strip() or "Employee",
               "is_synthetic": True}
    try:
        validated = UserCreate(**payload)
    except Exception as exc:
        raise HTTPException(422, str(exc))
    if db.scalar(select(MonitoredUser).where(MonitoredUser.username == validated.username)):
        raise HTTPException(409, f"User '{validated.username}' already exists")
    user = MonitoredUser(**validated.model_dump())
    db.add(user)
    db.flush()
    record_audit(db, admin.username, "MONITORED_USER_CREATED", "monitored_user", user.id, {"username": user.username})
    db.commit(); db.refresh(user)
    return _user_out(user)


@router.put("/users/{user_id}", include_in_schema=False)
def legacy_update_user(user_id: int, body: dict, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    user = get_or_404(db, MonitoredUser, user_id, "User")
    for field in ("email", "department", "job_role"):
        if field in body:
            value = str(body[field]).strip() if body[field] is not None else None
            setattr(user, field, value or (None if field == "email" else getattr(user, field)))
    if "username" in body:
        name = str(body["username"]).strip().lower()
        if len(name) < 3 or len(name) > 80:
            raise HTTPException(422, "Username must contain 3 to 80 characters")
        duplicate = db.scalar(select(MonitoredUser).where(MonitoredUser.username == name, MonitoredUser.id != user_id))
        if duplicate:
            raise HTTPException(409, "Username already exists")
        user.username = name
    if "status" in body:
        value = str(body["status"]).upper()
        if value not in ("ACTIVE", "INACTIVE"):
            raise HTTPException(422, "Status must be active or inactive")
        user.status = value
    record_audit(db, admin.username, "MONITORED_USER_UPDATED", "monitored_user", user.id,
                 {"fields": [k for k in body if k in ("username", "email", "department", "job_role", "status")]})
    db.commit(); db.refresh(user)
    return _user_out(user)


@router.delete("/users/{user_id}", include_in_schema=False)
def legacy_delete_user(user_id: int, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    user = get_or_404(db, MonitoredUser, user_id, "User")
    user.status = "INACTIVE"  # preserve the event/alert audit trail and foreign-key integrity
    record_audit(db, admin.username, "MONITORED_USER_DEACTIVATED", "monitored_user", user.id)
    db.commit()
    return {"ok": True, "status": "inactive"}


@router.get("/alerts", include_in_schema=False)
def legacy_alerts(db: Session = Depends(get_db), _: Account = Depends(require_analyst_or_admin)):
    rows = db.scalars(select(Alert).join(MonitoredUser).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(300)).all()
    return [_alert_out(row) for row in rows]


@router.put("/alerts/{alert_id}", include_in_schema=False)
def legacy_update_alert(alert_id: int, body: dict, db: Session = Depends(get_db), account: Account = Depends(require_analyst_or_admin)):
    alert = get_or_404(db, Alert, alert_id, "Alert")
    new_status = str(body.get("status", "")).upper()
    if new_status not in ("OPEN", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"):
        raise HTTPException(422, "Invalid alert status")
    if new_status in ("RESOLVED", "FALSE_POSITIVE") and not str(body.get("note", "")).strip():
        body["note"] = f"{new_status.replace('_', ' ').title()} from the legacy dashboard"
    old = alert.status
    alert.status = new_status
    if new_status in ("RESOLVED", "FALSE_POSITIVE"):
        alert.resolved_at = utc_now(); alert.resolution_notes = str(body.get("note", ""))
    else:
        alert.resolved_at = None
    from backend.models import AlertHistory
    alert.history.append(AlertHistory(action="STATUS_CHANGED", account_id=account.id, old_status=old,
                                      new_status=new_status, note=body.get("note")))
    record_audit(db, account.username, "ALERT_UPDATED", "alert", alert.id, {"status": [old, new_status]})
    db.commit(); db.refresh(alert)
    return _alert_out(alert)


@router.get("/activities", include_in_schema=False)
def legacy_activities(limit: int = Query(150, ge=1, le=1000), db: Session = Depends(get_db),
                      _: Account = Depends(require_admin)):
    rows = db.scalars(select(Activity).order_by(Activity.timestamp.desc(), Activity.id.desc()).limit(limit)).all()
    return [_activity_out(row) for row in rows]


@router.get("/", include_in_schema=False)
@router.get("/dashboard/", include_in_schema=False)
def legacy_dashboard_page():
    return FileResponse(LEGACY_FRONTEND / "index.html")


@router.get("/style.css", include_in_schema=False)
def legacy_css():
    return FileResponse(LEGACY_FRONTEND / "style.css", media_type="text/css")


@router.get("/app.js", include_in_schema=False)
def legacy_js():
    return FileResponse(LEGACY_FRONTEND / "app.js", media_type="application/javascript")
