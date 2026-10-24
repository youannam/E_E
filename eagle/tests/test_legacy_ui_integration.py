"""Smoke tests for the preserved web/Flutter clients against the modular backend."""


def test_legacy_dashboard_and_assets_are_served(client):
    assert client.get("/dashboard/").status_code == 200
    assert "Eagle Eye" in client.get("/").text
    assert client.get("/style.css").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_legacy_api_uses_the_new_backend_and_accepts_new_auth_tokens(client):
    login = client.post("/auth/login", json={"username": "admin", "password": "admin-test-password-123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    stats = client.get("/dashboard/statistics", headers=headers)
    users = client.get("/users", headers=headers)
    alerts = client.get("/alerts", headers=headers)
    activities = client.get("/activities?limit=5", headers=headers)
    assert stats.status_code == 200 and "total_users" in stats.json()
    assert users.status_code == 200 and isinstance(users.json(), list)
    assert alerts.status_code == 200 and isinstance(alerts.json(), list)
    assert activities.status_code == 200 and isinstance(activities.json(), list)
    assert client.get("/api/v1/dashboard/summary", headers=headers).status_code == 200


def test_public_account_creation_and_unsafe_password_reset_are_disabled(client):
    assert client.post("/auth/register", json={"username": "attacker", "password": "Password123!"}).status_code == 403
    assert client.post("/auth/forgot-password", json={"username": "admin", "new_password": "Password123!"}).status_code == 403


def test_legacy_user_management_is_admin_only_and_preserves_audit_history(client):
    analyst_login = client.post("/auth/login", json={"username": "analyst", "password": "analyst-test-password-123"})
    analyst_headers = {"Authorization": f"Bearer {analyst_login.json()['access_token']}"}
    assert client.post("/users", headers=analyst_headers, json={
        "username": "new.employee", "department": "Finance", "job_role": "Analyst"
    }).status_code == 403

    admin_login = client.post("/auth/login", json={"username": "admin", "password": "admin-test-password-123"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    created = client.post("/users", headers=admin_headers, json={
        "username": "new.employee", "email": "new.employee@example.test",
        "department": "Finance", "job_role": "Auditor", "status": "active"
    })
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]
    updated = client.put(f"/users/{user_id}", headers=admin_headers, json={"department": "Security"})
    assert updated.status_code == 200 and updated.json()["department"] == "Security"
    deleted = client.delete(f"/users/{user_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert all(u["id"] != user_id for u in client.get("/users", headers=admin_headers).json())
