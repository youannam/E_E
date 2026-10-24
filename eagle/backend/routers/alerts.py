"""Alert listing, details, statistics and analyst updates (the investigation workflow)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.models import Account, Alert, AlertHistory, MonitoredUser, utc_now
from backend.routers.common import Pagination, get_or_404, paginate
from backend.schemas import AlertDetail, AlertStatistics, AlertStatus, AlertSummary, AlertUpdate, Page, RiskLevel
from backend.security import require_analyst_or_admin
from backend.serializers import alert_detail, alert_summary

router = APIRouter(prefix="/alerts", tags=["Alerts"])

CLOSED = ("RESOLVED", "FALSE_POSITIVE")
SORT_COLUMNS = {"created_at": Alert.created_at, "risk_score": Alert.risk_score, "window_date": Alert.window_date}


@router.get("", response_model=Page[AlertSummary], summary="List alerts with filters")
def list_alerts(
    status: AlertStatus | None = None,
    risk_level: RiskLevel | None = None,
    user_id: int | None = Query(None, gt=0),
    date_from: date | None = Query(None, description="Activity day from (inclusive)"),
    date_to: date | None = Query(None, description="Activity day until (inclusive)"),
    search: str | None = Query(None, max_length=80, description="Username or department"),
    sort: str = Query("created_at", pattern="^(created_at|risk_score|window_date)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
    _: Account = Depends(require_analyst_or_admin),
):
    query = select(Alert).join(MonitoredUser)
    if status:
        query = query.where(Alert.status == status)
    if risk_level:
        query = query.where(Alert.risk_level == risk_level)
    if user_id:
        query = query.where(Alert.user_id == user_id)
    if date_from:
        query = query.where(Alert.window_date >= date_from)
    if date_to:
        query = query.where(Alert.window_date <= date_to)
    if search:
        query = query.where(or_(MonitoredUser.username.ilike(f"%{search}%"),
                                MonitoredUser.department.ilike(f"%{search}%")))
    column = SORT_COLUMNS[sort]
    query = query.order_by(column.desc() if order == "desc" else column.asc(), Alert.id.desc())
    rows, total = paginate(db, query, pagination)
    return Page(items=[alert_summary(row) for row in rows], total=total,
                page=pagination.page, page_size=pagination.page_size)


@router.get("/statistics", response_model=AlertStatistics, summary="Alert counts by status and level")
def alert_statistics(db: Session = Depends(get_db), _: Account = Depends(require_analyst_or_admin)):
    by_status = {status: 0 for status in ("OPEN", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE")}
    by_level = {level: 0 for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
    open_by_level = dict(by_level)
    rows = db.execute(select(Alert.status, Alert.risk_level, func.count(Alert.id)).group_by(Alert.status, Alert.risk_level))
    total = 0
    for status, level, count in rows:
        total += count
        by_status[status] = by_status.get(status, 0) + count
        by_level[level] = by_level.get(level, 0) + count
        if status not in CLOSED:
            open_by_level[level] += count
    return AlertStatistics(total=total, by_status=by_status, by_level=by_level, open_by_level=open_by_level)


@router.get("/{alert_id}", response_model=AlertDetail, summary="Full alert details for investigation")
def get_alert(alert_id: int, db: Session = Depends(get_db), _: Account = Depends(require_analyst_or_admin)):
    return alert_detail(db, get_or_404(db, Alert, alert_id, "Alert"))


@router.patch("/{alert_id}", response_model=AlertDetail, summary="Change status, add a note or assign to yourself")
def update_alert(alert_id: int, body: AlertUpdate, db: Session = Depends(get_db),
                 account: Account = Depends(require_analyst_or_admin)):
    alert = get_or_404(db, Alert, alert_id, "Alert")
    note = body.note.strip() if body.note else None
    changes = {}

    if body.status and body.status != alert.status:
        old_status = alert.status
        alert.status = body.status
        if body.status in CLOSED:
            alert.resolved_at = utc_now()
            alert.resolution_notes = note
        else:
            alert.resolved_at = None  # re-opened
        alert.history.append(AlertHistory(action="STATUS_CHANGED", account_id=account.id,
                                          old_status=old_status, new_status=body.status, note=note))
        changes["status"] = [old_status, body.status]
    elif body.status == alert.status and not note and body.assign_to_me is None:
        raise HTTPException(status_code=422, detail=f"Alert is already {alert.status}")
    elif note:
        alert.history.append(AlertHistory(action="NOTE_ADDED", account_id=account.id, note=note))
        changes["note_added"] = True

    if body.assign_to_me is not None:
        alert.assigned_to_id = account.id if body.assign_to_me else None
        alert.history.append(AlertHistory(action="ASSIGNED" if body.assign_to_me else "UNASSIGNED",
                                          account_id=account.id))
        changes["assigned_to_me"] = body.assign_to_me

    record_audit(db, account.username, "ALERT_UPDATED", "alert", alert.id, changes)
    db.commit()
    db.refresh(alert)
    return alert_detail(db, alert)

# Shared response playbooks consumed by both the web and Flutter clients.
def _response_actions(alert):
    text_blob = " ".join([alert.explanation or "", str(alert.triggered_rules or ""),
                         " ".join((a.event_type + " " + (a.resource or "") + " " + (a.device_id or "")) for a in alert.activities)]).lower()
    actions = [
        {"id": "review_evidence", "title": "Review evidence timeline", "description": "Inspect the correlated events, resources and timestamps.", "permission": "alerts.investigate"},
        {"id": "add_investigation_note", "title": "Record investigation findings", "description": "Document what was checked and the next step.", "permission": "alerts.investigate"},
    ]
    if any(k in text_blob for k in ("download", "bulk", "file access", "file_read")):
        actions.insert(0, {"id": "check_bulk_download", "title": "Check unusual bulk downloads", "description": "Compare file volume and sensitivity with the employee's baseline; preserve relevant logs.", "permission": "alerts.investigate"})
    if any(k in text_blob for k in ("login", "authentication", "failed_login", "after-hours", "unusual hour")):
        actions.insert(0, {"id": "correlate_logins", "title": "Correlate login attempts", "description": "Review failed/successful sign-ins, source devices and time-of-day baseline.", "permission": "alerts.investigate"})
    if any(k in text_blob for k in ("usb", "removable", "device", "transfer", "exfiltration")):
        actions.insert(0, {"id": "review_device_transfer", "title": "Review device/data transfer", "description": "Check device identifiers, transferred files and evidence-retention requirements.", "permission": "alerts.investigate"})
    if alert.risk_level in ("HIGH", "CRITICAL"):
        actions.append({"id": "escalate_case", "title": "Escalate to security lead", "description": "Prioritize the case, assign an owner and follow the incident-response policy.", "permission": "actions.escalate"})
    actions.append({"id": "assign_case", "title": "Assign case to me", "description": "Make ownership explicit for follow-up.", "permission": "alerts.investigate"})
    # These are synthetic monitored employees, not external identity-provider accounts.
    # Admin can change their project-side status and the change is persisted/audited.
    if alert.user.status == "ACTIVE":
        actions.append({"id": "suspend_user", "title": "Suspend monitored user", "description": "Set this demo employee to INACTIVE in the project database; no external account is touched.", "permission": "users.manage"})
    else:
        actions.append({"id": "reactivate_user", "title": "Reactivate monitored user", "description": "Return this demo employee to ACTIVE in the project database.", "permission": "users.manage"})
    actions.append({"id": "restrict_user", "title": "Restrict job permissions", "description": "Remove the demo employee's configured job permissions until an admin restores them.", "permission": "users.manage"})
    return actions


@router.get("/{alert_id}/response-actions", summary="Recommended response actions for an alert")
def get_response_actions(alert_id: int, db: Session = Depends(get_db), account: Account = Depends(require_analyst_or_admin)):
    from backend.rbac import ROLE_DEFAULTS
    alert = get_or_404(db, Alert, alert_id, "Alert")
    grants = set(account.permissions or ROLE_DEFAULTS.get(account.role, []))
    return {"alert_id": alert.id, "job_role": alert.user.job_role,
            "actions": [a for a in _response_actions(alert) if account.role == "ADMIN" or a["permission"] in grants]}


@router.post("/{alert_id}/response-actions/{action_id}", summary="Execute a supported response workflow action")
def execute_response_action(alert_id: int, action_id: str, db: Session = Depends(get_db), account: Account = Depends(require_analyst_or_admin)):
    from backend.rbac import ROLE_DEFAULTS
    alert = get_or_404(db, Alert, alert_id, "Alert")
    available = {a["id"]: a for a in _response_actions(alert)}
    if action_id not in available:
        raise HTTPException(status_code=400, detail="Action is not available for this alert")
    action = available[action_id]
    grants = set(account.permissions or ROLE_DEFAULTS.get(account.role, []))
    if account.role != "ADMIN" and action["permission"] not in grants:
        raise HTTPException(status_code=403, detail=f"Permission required: {action['permission']}")
    if action_id in ("suspend_user", "reactivate_user", "restrict_user"):
        user = alert.user
        if action_id == "suspend_user":
            if user.status != "ACTIVE":
                raise HTTPException(status_code=409, detail="User is already inactive")
            user.status = "INACTIVE"
            note = f"Monitored demo user {user.username} suspended by {account.username}."
            event = "MONITORED_USER_SUSPENDED"
        elif action_id == "reactivate_user":
            if user.status != "INACTIVE":
                raise HTTPException(status_code=409, detail="User is already active")
            user.status = "ACTIVE"
            note = f"Monitored demo user {user.username} reactivated by {account.username}."
            event = "MONITORED_USER_REACTIVATED"
        else:
            user.job_permissions = []
            note = f"Job permissions cleared for monitored demo user {user.username} by {account.username}; admin must restore them explicitly."
            event = "MONITORED_USER_RESTRICTED"
        alert.history.append(AlertHistory(action="NOTE_ADDED", account_id=account.id, note=note))
        record_audit(db, account.username, event, "monitored_user", user.id, {"status": user.status, "job_permissions": user.job_permissions or []})
    elif action_id == "assign_case":
        alert.assigned_to_id = account.id
        alert.history.append(AlertHistory(action="ASSIGNED", account_id=account.id, note="Assigned through response actions"))
    else:
        notes = {
            "review_evidence": "Response action selected: review evidence timeline.",
            "add_investigation_note": "Response action selected: record investigation findings.",
            "check_bulk_download": "Response action selected: review unusual bulk downloads and preserve relevant logs.",
            "correlate_logins": "Response action selected: correlate login attempts with baseline.",
            "review_device_transfer": "Response action selected: review device/data transfer and preserve evidence.",
            "escalate_case": "Response action selected: escalation requested; follow the organization's incident-response policy.",
        }
        note = notes[action_id]
        if action_id == "escalate_case":
            alert.status = "INVESTIGATING"
            alert.history.append(AlertHistory(action="STATUS_CHANGED", account_id=account.id, old_status="OPEN", new_status="INVESTIGATING", note=note))
        else:
            alert.history.append(AlertHistory(action="NOTE_ADDED", account_id=account.id, note=note))
    record_audit(db, account.username, "ALERT_RESPONSE_ACTION", "alert", alert.id, {"action_id": action_id})
    db.commit()
    return {"ok": True, "action_id": action_id, "alert_id": alert.id, "status": alert.status, "assigned_to": alert.assigned_to.username if alert.assigned_to else None}
