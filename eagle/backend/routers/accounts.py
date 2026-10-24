"""Administrator-only management of Eagle Eye login accounts and roles."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.models import Account
from backend.schemas import AccountCreate, AccountOut, AccountUpdate
from backend.security import hash_password, require_admin
from backend.rbac import normalize_account_permissions

router = APIRouter(prefix="/accounts", tags=["Account administration"])


@router.get("", response_model=list[AccountOut], summary="List login accounts (admin only)")
def list_accounts(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    return list(db.scalars(select(Account).order_by(Account.username)))


@router.post("", response_model=AccountOut, status_code=201, summary="Create an admin or analyst account")
def create_account(body: AccountCreate, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    account = Account(username=body.username.strip(), email=body.email, password_hash=hash_password(body.password),
                      role=body.role, job_role=body.job_role, permissions=normalize_account_permissions(body.role, body.permissions), is_active=body.is_active)
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists")
    record_audit(db, admin.username, "ACCOUNT_CREATED", "account", account.id,
                 {"username": account.username, "role": account.role})
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=AccountOut, summary="Edit an account, role or status")
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db),
                   admin: Account = Depends(require_admin)):
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    changes = body.model_dump(exclude_unset=True)
    if account.id == admin.id and changes.get("is_active") is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    if account.role == "ADMIN" and account.is_active and (changes.get("role") == "ANALYST" or changes.get("is_active") is False):
        active_admins = db.scalar(select(func.count(Account.id)).where(Account.role == "ADMIN", Account.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="At least one active administrator must remain")
    password = changes.pop("password", None)
    if password:
        account.password_hash = hash_password(password)
    for field, value in changes.items():
        if field == "permissions":
            account.permissions = normalize_account_permissions(changes.get("role", account.role), value)
        else:
            setattr(account, field, value)
    if "role" in changes and "permissions" not in changes:
        account.permissions = normalize_account_permissions(account.role, account.permissions or [])
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists")
    record_audit(db, admin.username, "ACCOUNT_UPDATED", "account", account.id,
                 {key: ("[changed]" if key == "password" else value) for key, value in body.model_dump(exclude_unset=True).items()})
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204, summary="Delete an account (admin only)")
def delete_account(account_id: int, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete the account you are currently using")
    if account.role == "ADMIN" and account.is_active:
        active_admins = db.scalar(select(func.count(Account.id)).where(Account.role == "ADMIN", Account.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="At least one active administrator must remain")
    record_audit(db, admin.username, "ACCOUNT_DELETED", "account", account.id, {"username": account.username})
    db.delete(account)
    db.commit()
