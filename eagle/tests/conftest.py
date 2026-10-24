"""
Shared test setup.

Environment variables are set BEFORE the backend is imported, so the tests use their own
temporary SQLite database and model folder and never touch eagle_eye.db or ai/models.
A real Isolation Forest model is trained once per test session; tests never fake the AI.
"""

import os
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="eagle_eye_tests_"))
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR / 'test.db'}"
os.environ["MODEL_DIR"] = str(TEST_DIR / "models")
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["ORG_TIMEZONE"] = "Africa/Cairo"
for name in ("RISK_RULE_WEIGHT", "RISK_AI_WEIGHT", "ALERT_THRESHOLD", "RISK_MEDIUM_MIN", "RISK_HIGH_MIN", "RISK_CRITICAL_MIN"):
    os.environ.pop(name, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ai.train import run_training  # noqa: E402
from backend.database import Base, SessionLocal, engine  # noqa: E402
from backend.detection import anomaly_service  # noqa: E402
from backend.detection.rule_config import DEFAULT_RULE_SETTINGS  # noqa: E402
from backend.ingestion import ingest_activities  # noqa: E402
from backend.models import Account, MonitoredUser, RuleSetting  # noqa: E402
from backend.schemas import ActivityCreate  # noqa: E402
from backend.security import hash_password, login_limiter  # noqa: E402
from backend.timeutils import org_today  # noqa: E402
from simulator.catalog import WEEKEND_DAYS, Employee  # noqa: E402
from simulator.generator import generate_normal_day  # noqa: E402

# Browser end-to-end tests need the real servers running, so they are skipped unless RUN_E2E=1.
collect_ignore_glob = [] if os.getenv("RUN_E2E") == "1" else ["e2e/*"]

ADMIN_PASSWORD = "admin-test-password-123"
ANALYST_PASSWORD = "analyst-test-password-123"


@pytest.fixture(scope="session")
def trained_model_dir():
    """Train the real model once (about 10 seconds) into the temporary model folder."""
    model_dir = Path(os.environ["MODEL_DIR"])
    run_training(seed=42, model_dir=model_dir)
    anomaly_service.load_detector()
    yield model_dir
    shutil.rmtree(TEST_DIR, ignore_errors=True)


@pytest.fixture
def db(trained_model_dir):
    """A clean database for every test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    anomaly_service.load_detector()
    login_limiter.reset()
    session = SessionLocal()
    for rule_id, values in DEFAULT_RULE_SETTINGS.items():
        session.add(RuleSetting(rule_id=rule_id, enabled=True, weight=values["weight"], parameters=values["parameters"]))
    session.add(Account(username="admin", email="admin@test.example", role="ADMIN", password_hash=hash_password(ADMIN_PASSWORD)))
    session.add(Account(username="analyst", role="ANALYST", password_hash=hash_password(ANALYST_PASSWORD)))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db):
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def login(client, username: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client):
    return login(client, "admin", ADMIN_PASSWORD)


@pytest.fixture
def analyst_headers(client):
    return login(client, "analyst", ANALYST_PASSWORD)


def add_user(db, username="test.user", department="Engineering", job_role="Software Engineer") -> MonitoredUser:
    user = MonitoredUser(username=username, department=department, job_role=job_role, is_synthetic=True)
    db.add(user)
    db.commit()
    return user


def add_normal_history(db, user: MonitoredUser, employee: Employee, days: int = 20, seed: int = 1) -> None:
    """Ingest `days` calendar days of normal activity ending the day before yesterday."""
    import random

    rng = random.Random(seed)
    last = org_today() - timedelta(days=2)
    items = []
    for offset in range(days - 1, -1, -1):
        day = last - timedelta(days=offset)
        if day.weekday() in WEEKEND_DAYS:
            continue
        for event in generate_normal_day(employee, day, rng):
            items.append(ActivityCreate(user_id=user.id, source="SIMULATOR", is_simulated=True, **event))
    ingest_activities(db, items)


def yesterday() -> date:
    return org_today() - timedelta(days=1)
