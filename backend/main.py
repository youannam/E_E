"""
FastAPI application entry point.

Start it from the project root with:
    uvicorn backend.main:app --reload
Then open http://localhost:8000/docs for the interactive API documentation (Swagger).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from backend.config import get_settings
from backend.database import SessionLocal, engine
from backend.models import Account, FinanceRecord, PasswordResetRequest, WorkspaceItem
from backend.rbac import normalize_account_permissions
from backend.detection import anomaly_service
from backend.routers import accounts, activities, alerts, analysis, auth, dashboard, rules, simulator, users, password_resets, workspace, business_workspaces
from backend.compat import router as compatibility_router

API_PREFIX = "/api/v1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eagle_eye")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: check configuration and load the AI model (if one has been trained)."""
    get_settings().validate()
    # Backward-compatible local DB upgrade for forced password-change support.
    with engine.begin() as conn:
        if "accounts" in inspect(engine).get_table_names():
            cols = {c["name"] for c in inspect(engine).get_columns("accounts")}
            if "must_change_password" not in cols:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))
            if "permissions" not in cols:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN permissions JSON NOT NULL DEFAULT '[]'"))
            if "job_role" not in cols:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN job_role VARCHAR(60) NOT NULL DEFAULT 'Security Analyst'"))
        if "monitored_users" in inspect(engine).get_table_names():
            cols = {c["name"] for c in inspect(engine).get_columns("monitored_users")}
            if "job_permissions" not in cols:
                conn.execute(text("ALTER TABLE monitored_users ADD COLUMN job_permissions JSON NOT NULL DEFAULT '[]'"))
    PasswordResetRequest.__table__.create(bind=engine, checkfirst=True)
    WorkspaceItem.__table__.create(bind=engine, checkfirst=True)
    FinanceRecord.__table__.create(bind=engine, checkfirst=True)
    # Add workspace grants without removing any existing explicit permissions. Legacy accounts
    # with no saved grants receive defaults for their business job role, not blanket analyst access.
    with SessionLocal() as db:
        changed = False
        for account in db.query(Account).all():
            current = list(account.permissions or [])
            if not current:
                account.permissions = normalize_account_permissions(account.role, [], account.job_role)
                changed = True
            elif account.role == "ADMIN":
                normalized = normalize_account_permissions(account.role, current, account.job_role)
                if current != normalized:
                    account.permissions = normalized
                    changed = True
            else:
                merged = sorted(set(current) | {"workspace.view", "workspace.create", "workspace.update"})
                if merged != current:
                    account.permissions = merged
                    changed = True
        if changed:
            db.commit()
    anomaly_service.load_detector()
    with SessionLocal() as db:
        try:
            anomaly_service.register_model_version(db)
        except Exception:
            logger.exception("Could not record the model version (has the database been initialized? "
                             "Run: python -m backend.cli init-db)")
    yield


app = FastAPI(
    title="Eagle Eye API",
    description="AI-powered insider threat detection (graduation project). All demo data is synthetic.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,  # only the configured web dashboard origins
    allow_credentials=False,  # tokens travel in the Authorization header, not in cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Log the full error for developers, but never send stack traces to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for module in (auth, accounts, users, activities, analysis, alerts, dashboard, simulator, rules, password_resets, workspace, business_workspaces):
    app.include_router(module.router, prefix=API_PREFIX)

# Legacy UI endpoints translate to the new backend models; the modular API remains canonical.
app.include_router(compatibility_router)


@app.get(f"{API_PREFIX}/health", tags=["Health"], summary="Is the API running? (no login needed)")
def health():
    return {"status": "ok", "model_loaded": anomaly_service.get_detector() is not None}
