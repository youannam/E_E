"""Users, dashboard, simulator, rules, model status and manual analysis endpoints."""

from datetime import timedelta

from backend.detection import anomaly_service
from backend.models import Alert
from backend.timeutils import org_today
from simulator.catalog import find_demo_employee
from tests.conftest import add_normal_history, add_user, yesterday

EMPLOYEE = find_demo_employee("salma.ibrahim")


def setup_user(db):
    user = add_user(db, EMPLOYEE.username, EMPLOYEE.department, EMPLOYEE.job_role)
    add_normal_history(db, user, EMPLOYEE, days=14)
    return user


def test_users_endpoints(client, db, admin_headers):
    user = setup_user(db)
    page = client.get("/api/v1/users", headers=admin_headers).json()
    assert page["total"] == 1 and page["items"][0]["username"] == EMPLOYEE.username

    detail = client.get(f"/api/v1/users/{user.id}", headers=admin_headers).json()
    assert detail["profile"]["baseline_type"] in ("INDIVIDUAL", "PEER_GROUP", "DEFAULT")
    assert detail["statistics"]["active_days"] > 5 and detail["statistics"]["devices"]

    assert client.get(f"/api/v1/users/{user.id}/activities?page_size=5", headers=admin_headers).json()["total"] > 100
    history = client.get(f"/api/v1/users/{user.id}/risk-history", headers=admin_headers).json()
    assert len(history) > 5 and all(0 <= point["risk_score"] <= 100 for point in history)
    assert client.get(f"/api/v1/users/{user.id}/alerts", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/users/9999", headers=admin_headers).status_code == 404
    assert client.get("/api/v1/users?risk_level=CRITICAL", headers=admin_headers).json()["total"] == 0


def test_create_monitored_user(client, db, admin_headers, analyst_headers):
    body = {"username": "new.hire", "department": "Sales", "job_role": "Sales Representative"}
    assert client.post("/api/v1/users", json=body, headers=analyst_headers).status_code == 403
    assert client.post("/api/v1/users", json=body, headers=admin_headers).status_code == 201
    assert client.post("/api/v1/users", json=body, headers=admin_headers).status_code == 409
    assert client.post("/api/v1/users", json={**body, "username": "Bad Name!"}, headers=admin_headers).status_code == 422


def test_simulator_runs_real_pipeline(client, db, admin_headers):
    user = setup_user(db)
    scenarios = client.get("/api/v1/simulator/scenarios", headers=admin_headers).json()
    assert {s["id"] for s in scenarios} >= {"NORMAL_USER", "COMBINED_ANOMALY", "BENIGN_EXCEPTION"}

    response = client.post("/api/v1/simulator/run", headers=admin_headers,
                           json={"scenario_id": "COMBINED_ANOMALY", "user_id": user.id, "seed": 11})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["date"] == yesterday().isoformat()
    assert body["events_created"] > 50 and all(a["is_simulated"] for a in body["activities"])
    assert body["analysis"]["ai_status"] == "OK"
    assert body["alert"] is not None
    assert db.query(Alert).count() == 1


def test_simulator_validation(client, db, admin_headers):
    user = setup_user(db)
    tomorrow = (org_today() + timedelta(days=1)).isoformat()
    assert client.post("/api/v1/simulator/run", json={"scenario_id": "NOPE", "user_id": user.id},
                       headers=admin_headers).status_code == 422
    assert client.post("/api/v1/simulator/run", json={"scenario_id": "NORMAL_USER", "user_id": user.id, "date": tomorrow},
                       headers=admin_headers).status_code == 422
    assert client.post("/api/v1/simulator/run", json={"scenario_id": "NORMAL_USER", "user_id": 999},
                       headers=admin_headers).status_code == 404
    assert client.post("/api/v1/simulator/run", json={"scenario_id": "NORMAL_USER", "user_id": user.id, "intensity": 9},
                       headers=admin_headers).status_code == 422


def test_dashboard_endpoints(client, db, admin_headers):
    user = setup_user(db)
    client.post("/api/v1/simulator/run", json={"scenario_id": "COMBINED_ANOMALY", "user_id": user.id},
                headers=admin_headers)
    summary = client.get("/api/v1/dashboard/summary", headers=admin_headers).json()
    assert summary["total_users"] == 1 and summary["active_users"] == 1
    assert summary["open_alerts"] == 1 and summary["model_loaded"] is True
    assert summary["high_risk_users"] == 1

    distribution = client.get("/api/v1/dashboard/risk-distribution", headers=admin_headers).json()
    assert [item["level"] for item in distribution] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert sum(item["count"] for item in distribution) == 1

    over_time = client.get("/api/v1/dashboard/alerts-over-time?days=7", headers=admin_headers).json()
    assert len(over_time) == 7 and sum(day["total"] for day in over_time) == 1

    activity = client.get("/api/v1/dashboard/activity-distribution?days=30", headers=admin_headers).json()
    assert any(item["event_type"] == "LOGIN" for item in activity)


def test_rules_can_be_viewed_and_configured(client, db, admin_headers):
    rules = client.get("/api/v1/rules", headers=admin_headers).json()
    assert len(rules) == 8
    response = client.patch("/api/v1/rules/EXCESSIVE_DOWNLOADS", headers=admin_headers,
                            json={"weight": 35, "parameters": {"minimum_count": 25}})
    assert response.status_code == 200
    assert response.json()["weight"] == 35 and response.json()["parameters"]["minimum_count"] == 25
    assert client.patch("/api/v1/rules/EXCESSIVE_DOWNLOADS", json={"parameters": {"bogus": 1}},
                        headers=admin_headers).status_code == 422
    assert client.patch("/api/v1/rules/EXCESSIVE_DOWNLOADS", json={"parameters": {"minimum_count": -1}},
                        headers=admin_headers).status_code == 422
    assert client.patch("/api/v1/rules/NOT_A_RULE", json={"enabled": False}, headers=admin_headers).status_code == 404


def test_disabled_rule_is_not_applied_by_pipeline(client, db, admin_headers):
    user = setup_user(db)
    client.patch("/api/v1/rules/USB_SENSITIVE_TRANSFER", json={"enabled": False}, headers=admin_headers)
    body = client.post("/api/v1/simulator/run", json={"scenario_id": "USB_TRANSFER", "user_id": user.id},
                       headers=admin_headers).json()
    assert "USB_SENSITIVE_TRANSFER" not in [rule["rule_id"] for rule in body["analysis"]["triggered_rules"]]


def test_model_status_and_manual_analysis(client, db, admin_headers):
    user = setup_user(db)
    status = client.get("/api/v1/models/status", headers=admin_headers).json()
    assert status["loaded"] is True and status["feature_names"]
    assert "evaluation_note" in status["metrics"]

    day = org_today() - timedelta(days=2)
    while day.weekday() in (4, 5):
        day -= timedelta(days=1)
    response = client.post("/api/v1/analysis/run", json={"user_id": user.id, "date": day.isoformat()},
                           headers=admin_headers)
    assert response.status_code == 200 and response.json()["window_date"] == day.isoformat()
    empty_day = (org_today() - timedelta(days=200)).isoformat()
    assert client.post("/api/v1/analysis/run", json={"user_id": user.id, "date": empty_day},
                       headers=admin_headers).status_code == 404


def test_pipeline_runs_with_rules_only_when_model_missing(client, db, admin_headers, monkeypatch):
    user = setup_user(db)
    monkeypatch.setattr(anomaly_service, "_detector", None)
    monkeypatch.setattr(anomaly_service, "_loaded", True)
    assert client.get("/api/v1/models/status", headers=admin_headers).json()["loaded"] is False
    body = client.post("/api/v1/simulator/run", json={"scenario_id": "USB_TRANSFER", "user_id": user.id},
                       headers=admin_headers).json()
    analysis = body["analysis"]
    assert analysis["ai_status"] == "UNAVAILABLE" and analysis["ai_score"] is None
    assert analysis["risk_score"] >= 50  # rules (and the CRITICAL floor) still work
    assert "AI unavailable" in analysis["score_breakdown"]["formula"]
