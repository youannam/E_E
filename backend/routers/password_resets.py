"""Password reset requests: users may request; only administrators may review and reset."""
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from backend.audit import record_audit
from backend.database import get_db
from backend.models import Account, PasswordResetRequest, utc_now
from backend.config import get_settings
from backend.email_service import send_email
from backend.security import hash_password, require_admin

router = APIRouter(prefix="/password-reset-requests", tags=["Password reset requests"])

class RequestBody(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=120)

class CompleteResetBody(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    temporary_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)
    confirm_password: str = Field(min_length=10, max_length=200)

class ReviewBody(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    new_password: str | None = Field(default=None, min_length=10, max_length=200)

@router.post("", status_code=202)
def request_reset(body: RequestBody, db: Session = Depends(get_db)):
    # Always acknowledge identically; do not reveal whether an account exists.
    key = body.username.strip().lower()
    if not key: return {"message": "If the account matches our records, the administrator has been notified."}
    existing = db.scalar(select(PasswordResetRequest).where(PasswordResetRequest.username == key, PasswordResetRequest.status == "PENDING"))
    if not existing:
        # Resolve the registered email from the account record; never trust a client-supplied
        # recipient address for sending a temporary password.
        account = db.scalar(select(Account).where(
            (func.lower(Account.username) == key) | (func.lower(Account.email) == key)
        ))
        registered_email = account.email if account and account.email else None
        request_row = PasswordResetRequest(username=key[:50], email=registered_email)
        db.add(request_row)
        db.commit()
        settings = get_settings()
        notification_subject = "Eagle Eye Smart — Password reset request"
        notification_body = (
            "A password reset request needs your review.\n\n"
            f"Username/email entered: {key}\n"
            f"Registered account email: {registered_email or 'Not available'}\n"
            f"Request ID: {request_row.id}\n\n"
            "Sign in to the Eagle Eye dashboard to review this request."
        )
        # Admin and analyst receive separate notifications through their own configured
        # sender profiles. The admin notification remains the primary workflow.
        send_email(settings.admin_email, notification_subject, notification_body, sender_profile="admin")
        if settings.analyst_email and settings.analyst_email.lower() != settings.admin_email.lower():
            send_email(settings.analyst_email, notification_subject, notification_body, sender_profile="analyst")
    return {"message": "If the account matches our records, the administrator has been notified. You will need administrator approval to reset your password."}

@router.get("/status", summary="Check the latest password reset request status")
def reset_status(username: str, db: Session = Depends(get_db)):
    key = username.strip().lower()
    if not key:
        return {"status": "NONE"}
    req = db.scalar(
        select(PasswordResetRequest)
        .where(PasswordResetRequest.username == key)
        .order_by(PasswordResetRequest.created_at.desc(), PasswordResetRequest.id.desc())
    )
    return {"status": req.status if req else "NONE"}


@router.post("/complete", summary="Set a new password using an administrator-issued temporary password")
def complete_reset(body: CompleteResetBody, db: Session = Depends(get_db)):
    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=422, detail="New password and confirmation do not match")
    key = body.username.strip().lower()
    account = db.scalar(select(Account).where((func.lower(Account.username) == key) | (func.lower(Account.email) == key)))
    if account is None or not account.is_active or not account.must_change_password:
        raise HTTPException(status_code=400, detail="Invalid username or temporary password, or no approved reset is waiting")
    from backend.security import verify_password
    if not verify_password(body.temporary_password, account.password_hash):
        raise HTTPException(status_code=400, detail="Invalid username or temporary password")
    account.password_hash = hash_password(body.new_password)
    account.must_change_password = False
    record_audit(db, account.username, "PASSWORD_RESET_COMPLETED", "account", account.id, {})
    db.commit()
    return {"message": "Password changed successfully. You can now sign in with your new password."}


@router.get("")
def list_requests(db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    rows = db.scalars(select(PasswordResetRequest).order_by(PasswordResetRequest.created_at.desc()).limit(200)).all()
    return [{"id": r.id, "username": r.username, "email": r.email, "status": r.status, "created_at": r.created_at, "reviewed_at": r.reviewed_at} for r in rows]

@router.post("/{request_id}/review")
def review_request(request_id: int, body: ReviewBody, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    req = db.get(PasswordResetRequest, request_id)
    if req is None: raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "PENDING": raise HTTPException(status_code=409, detail="Request has already been reviewed")
    if body.action == "approve":
        if not body.new_password: raise HTTPException(status_code=422, detail="Set a temporary password of at least 10 characters")
        account = db.scalar(select(Account).where((func.lower(Account.username) == req.username.lower()) | (func.lower(Account.email) == req.username.lower())))
        # Also allow matching the separately supplied email, without disclosing existence to the requester.
        if account is None and req.email: account = db.scalar(select(Account).where(func.lower(Account.email) == req.email.lower()))
        if account is None: raise HTTPException(status_code=404, detail="No login account matches this request")
        if not account.email:
            raise HTTPException(status_code=422, detail="This account has no registered email address; add one before approving password reset")
        # Deliver to the email stored on the user's account, not to the shared user mailbox.
        delivered = send_email(
            account.email,
            "Eagle Eye Smart — Your temporary password",
            "Your password reset request was approved.\n\n"
            f"Username: {account.username}\n"
            f"Temporary password: {body.new_password}\n\n"
            "Open the Reset Password page and enter this temporary password with a new password. "
            "Do not share this email. If you did not request this reset, contact the Eagle Eye administrator immediately.",
            sender_profile="admin",
        )
        if not delivered:
            raise HTTPException(status_code=503, detail="Email was not sent. Configure SMTP in the backend .env and retry; the password was not changed.")
        account.password_hash = hash_password(body.new_password)
        account.must_change_password = True
        req.status = "APPROVED"
        record_audit(db, admin.username, "PASSWORD_RESET_APPROVED", "account", account.id, {"request_id": req.id})
    else:
        req.status = "REJECTED"
        record_audit(db, admin.username, "PASSWORD_RESET_REJECTED", "password_reset_request", req.id, {})
    req.reviewed_at = utc_now(); req.reviewed_by_id = admin.id
    db.commit()
    return {"id": req.id, "status": req.status, "message": "Request reviewed"}
