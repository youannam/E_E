"""Authentication, authorization and API misuse protection."""

from backend.models import AuditLog
from backend.security import hash_password, verify_password
from tests.conftest import ADMIN_PASSWORD, login


def test_password_hashing():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password!!", stored)
    assert hash_password("correct horse battery") != stored  # random salt


def test_login_success_returns_token_without_secrets(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] > 0
    assert body["account"]["role"] == "ADMIN"
    assert "password" not in response.text and "scrypt" not in response.text


def test_login_by_email(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin@test.example", "password": ADMIN_PASSWORD})
    assert response.status_code == 200


def test_wrong_password_and_unknown_user_give_same_error(client):
    wrong = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope-nope-nope"})
    unknown = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope-nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid username or password"}


def test_login_validation(client):
    assert client.post("/api/v1/auth/login", json={"username": "", "password": "x"}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"username": "admin"}).status_code == 422


def test_repeated_failures_are_rate_limited(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad-password-x"})
    blocked = client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert blocked.status_code == 429


def test_me_requires_valid_token(client, admin_headers):
    assert client.get("/api/v1/auth/me", headers=admin_headers).json()["username"] == "admin"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_sensitive_endpoints_reject_anonymous_requests(client):
    for path in ["/api/v1/users", "/api/v1/alerts", "/api/v1/activities", "/api/v1/dashboard/summary",
                 "/api/v1/simulator/scenarios", "/api/v1/rules", "/api/v1/models/status"]:
        assert client.get(path).status_code == 401, path
    assert client.get("/api/v1/health").status_code == 200  # health check stays public


def test_analyst_can_run_detection_but_cannot_ingest_raw_activity(client, analyst_headers):
    activity = {"user_id": 1, "timestamp": "2026-10-01T09:00:00", "event_type": "LOGIN"}
    assert client.post("/api/v1/activities", json=activity, headers=analyst_headers).status_code == 403
    # Simulation/detection is explicitly allowed to analysts. A missing user returns 404,
    # proving the request passed role authorization instead of being rejected with 403.
    response = client.post("/api/v1/simulator/run", json={"scenario_id": "NORMAL_USER", "user_id": 1},
                           headers=analyst_headers)
    assert response.status_code != 403
    assert client.get("/api/v1/users", headers=analyst_headers).status_code == 403
    assert client.get("/api/v1/accounts", headers=analyst_headers).status_code == 403
    assert client.patch("/api/v1/rules/UNUSUAL_LOGIN_TIME", json={"enabled": False},
                        headers=analyst_headers).status_code == 403
    # ...but can read data
    assert client.get("/api/v1/alerts", headers=analyst_headers).status_code == 200


def test_logins_are_audited(client, db):
    login(client, "admin", ADMIN_PASSWORD)
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-password-1"})
    actions = [row.action for row in db.query(AuditLog).all()]
    assert "LOGIN" in actions and "LOGIN_FAILED" in actions


def test_pagination_limit_is_enforced(client, admin_headers):
    assert client.get("/api/v1/activities?page_size=1000", headers=admin_headers).status_code == 422


def test_security_headers(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_analyst_is_limited_to_alerts_and_detection(client, analyst_headers):
    # The analyst may investigate alerts and run detection, but cannot enumerate
    # the employee directory, inspect raw activity, or use administrator dashboards.
    for path in ["/api/v1/users", "/api/v1/activities", "/api/v1/dashboard/summary",
                 "/users", "/activities?limit=5", "/dashboard/statistics"]:
        response = client.get(path, headers=analyst_headers)
        assert response.status_code == 403, (path, response.status_code, response.text)
    assert client.get("/api/v1/alerts", headers=analyst_headers).status_code == 200
    assert client.get("/api/v1/simulator/scenarios", headers=analyst_headers).status_code == 200
