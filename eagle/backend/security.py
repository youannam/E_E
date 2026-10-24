"""
Authentication and authorization.

Passwords
    Stored as scrypt hashes (Python standard library, hashlib.scrypt). scrypt is a
    deliberately slow, memory-hard password hashing function: checking one guess takes
    noticeable time and memory, which makes brute-forcing a stolen database expensive.
    Each password gets a random salt, so identical passwords produce different hashes.
    Stored format:  scrypt$<n>$<r>$<p>$<salt base64>$<hash base64>

Tokens
    After a successful login the API returns a JWT (JSON Web Token) signed with
    JWT_SECRET_KEY. The client sends it back in the header  Authorization: Bearer <token>.
    The token contains the account id, role and an expiry time; it cannot be modified
    without the secret key.

Roles
    ADMIN   - all dashboards, users, raw activity, accounts, rules, ingestion and detection
    ANALYST - alerts, investigation workflow and synthetic Detection Lab only; no user directory,
              raw activity stream, aggregate dashboard, account management or rule configuration
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models import Account

SCRYPT_N = 2 ** 15  # CPU/memory cost
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
MIN_PASSWORD_LENGTH = 10

bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from POST /api/v1/auth/login")


# --------------------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM)
    encoded_salt = base64.b64encode(salt).decode()
    encoded_hash = base64.b64encode(digest).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${encoded_salt}${encoded_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_hash = stored_hash.split("$")
        if algorithm != "scrypt":
            return False
        expected = base64.b64decode(encoded_hash)
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(encoded_salt),
                                n=int(n), r=int(r), p=int(p), maxmem=SCRYPT_MAXMEM)
    except (ValueError, TypeError):
        return False
    # compare_digest takes the same time whether the first or last byte differs (no timing leak).
    return hmac.compare_digest(digest, expected)


# Used when the username does not exist, so a failed login always takes the same time
# (otherwise an attacker could tell valid usernames from invalid ones by response time).
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def verify_against_dummy(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


# --------------------------------------------------------------------------- login rate limiting

class LoginRateLimiter:
    """
    Blocks a username for a while after too many failed logins (simple brute-force protection).
    Kept in memory: enough for a single-server demo; it resets when the server restarts.
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window_seconds
        recent = [moment for moment in self._failures.get(key, []) if moment > cutoff]
        self._failures[key] = recent
        return recent

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)


login_limiter = LoginRateLimiter()


# --------------------------------------------------------------------------- tokens

def create_access_token(account: Account) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(account.id),
        "role": account.role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Account:
    """FastAPI dependency: the logged-in account, or 401 if the token is missing/invalid/expired."""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        account_id = int(payload["sub"])
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired, please log in again")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _unauthorized("Invalid token")

    account = db.get(Account, account_id)
    if account is None or not account.is_active:
        raise _unauthorized("Account not found or disabled")
    return account


def require_roles(*roles: str):
    """Dependency factory: require_roles("ADMIN") lets only administrators through (403 otherwise)."""

    def check(account: Account = Depends(get_current_account)) -> Account:
        if account.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"This action requires one of these roles: {', '.join(roles)}")
        return account

    return check


require_admin = require_roles("ADMIN")
require_analyst_or_admin = require_roles("ADMIN", "ANALYST")
