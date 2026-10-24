"""Login and "who am I" endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.models import Account, utc_now
from backend.schemas import AccountOut, LoginRequest, TokenResponse
from backend.security import create_access_token, get_current_account, login_limiter, verify_against_dummy, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse, summary="Log in with username (or email) and password")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    key = body.username.strip().lower()
    if login_limiter.is_blocked(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many failed attempts. Try again in a few minutes.")

    account = db.scalar(select(Account).where(or_(Account.username == body.username.strip(),
                                                  Account.email == body.username.strip())))
    if account is None:
        verify_against_dummy(body.password)  # same response time as a wrong password
        valid = False
    else:
        valid = verify_password(body.password, account.password_hash) and account.is_active

    if not valid:
        login_limiter.record_failure(key)
        record_audit(db, actor=body.username.strip()[:50], action="LOGIN_FAILED", entity_type="account")
        db.commit()
        # The same message for "no such user" and "wrong password", so usernames cannot be guessed.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    login_limiter.reset(key)
    account.last_login = utc_now()
    record_audit(db, actor=account.username, action="LOGIN", entity_type="account", entity_id=account.id)
    db.commit()
    token, expires_in = create_access_token(account)
    return TokenResponse(access_token=token, expires_in=expires_in, account=AccountOut.model_validate(account))


@router.get("/me", response_model=AccountOut, summary="The account that owns the token")
def me(account: Account = Depends(get_current_account)):
    return account
