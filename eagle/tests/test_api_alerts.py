"""Alert generation, deduplication and the investigation workflow."""

from backend.models import Alert, AuditLog
from backend.schemas import ActivityCreate
from backend.ingestion import ingest_activities
from simulator.catalog import find_demo_employee
from simulator.scenarios import run_scenario
from tests.conftest import add_normal_history, add_user, yesterday

EMPLOYEE = find_demo_employee("omar.hassan")


def user_with_history(db, username="omar.hassan"):
    user = add_user(db, username, EMPLOYEE.department, EMPLOYEE.job_role)
    add_normal_history(db, user, EMPLOYEE)
    return user


def ingest_scenario(db, user, scenario_id, seed=42, intensity=1):
    events = run_scenario(scenario_id, EMPLOYEE, yesterday(), seed=seed, intensity=intensity)
    items = [ActivityCreate(user_id=user.id, source="SIMULATOR", is_simulated=True, **event) for event in events]
    return ingest_activities(db, items)


def test_combined_anomaly_creates_one_explainable_alert(client, db, admin_headers):
    user = user_with_history(db)
    ingest_scenario(db, user, "COMBINED_ANOMALY")
    alerts = client.get("/api/v1/alerts", headers=admin_headers).json()
    assert alerts["total"] == 1
    alert = client.get(f"/api/v1/alerts/{alerts['items'][0]['id']}", headers=admin_headers).json()
    assert alert["status"] == "OPEN" and alert["risk_level"] in ("HIGH", "CRITICAL")
    assert alert["ai_status"] == "OK" and alert["model_version"]
    assert "USB_SENSITIVE_TRANSFER" in alert["triggered_rule_ids"]
    assert alert["activities"], "the alert must link the evidence events"
    assert all(activity["is_simulated"] for activity in alert["activities"])
    assert "not proof of malicious intent" in alert["explanation"]
    assert alert["analysis"]["score_breakdown"]["formula"]
    assert alert["history"][0]["action"] == "CREATED"


def test_normal_day_does_not_create_alert(client, db, admin_headers):
    user = user_with_history(db)
    _, analyses = ingest_scenario(db, user, "NORMAL_USER")
    assert analyses[0].risk_level in ("LOW", "MEDIUM")
    assert db.query(Alert).count() == 0


def test_burst_in_several_batches_is_deduplicated(client, db, admin_headers):
    user = user_with_history(db)
    events = run_scenario("COMBINED_ANOMALY", EMPLOYEE, yesterday())
    items = [ActivityCreate(user_id=user.id, source="SIMULATOR", is_simulated=True, **event) for event in events]
    for start in range(0, len(items), 20):  # the same day arrives in several chunks
        ingest_activities(db, items[start:start + 20])
    alerts = db.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].occurrence_count >= 2


def test_closed_alert_is_not_reraised_without_new_information(client, db, admin_headers):
    user = user_with_history(db)
    ingest_scenario(db, user, "USB_TRANSFER")
    alert = db.query(Alert).one()
    client.patch(f"/api/v1/alerts/{alert.id}", json={"status": "FALSE_POSITIVE", "note": "Approved backup"},
                 headers=admin_headers)
    # More ordinary events on the same day: the analyst's decision stands.
    ingest_scenario(db, user, "NORMAL_USER", seed=7)
    assert db.query(Alert).count() == 1
    # A new kind of suspicious behaviour on that day creates a new alert.
    ingest_scenario(db, user, "EXCESSIVE_DOWNLOADS", seed=8, intensity=2)
    assert db.query(Alert).count() == 2


def test_status_workflow_persists_with_history_and_audit(client, db, analyst_headers):
    user = user_with_history(db)
    ingest_scenario(db, user, "COMBINED_ANOMALY")
    alert_id = db.query(Alert).one().id
    url = f"/api/v1/alerts/{alert_id}"

    response = client.patch(url, json={"status": "INVESTIGATING", "assign_to_me": True}, headers=analyst_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "INVESTIGATING" and response.json()["assigned_to"] == "analyst"

    assert client.patch(url, json={"note": "Called the employee's manager"}, headers=analyst_headers).status_code == 200
    assert client.patch(url, json={"status": "RESOLVED"}, headers=analyst_headers).status_code == 422  # note required
    resolved = client.patch(url, json={"status": "RESOLVED", "note": "Confirmed policy violation, escalated to HR"},
                            headers=analyst_headers).json()
    assert resolved["status"] == "RESOLVED" and resolved["resolved_at"]
    assert resolved["resolution_notes"].startswith("Confirmed")

    again = client.get(url, headers=analyst_headers).json()  # persisted
    actions = [entry["action"] for entry in again["history"]]
    assert actions == ["CREATED", "STATUS_CHANGED", "ASSIGNED", "NOTE_ADDED", "STATUS_CHANGED"]
    assert again["history"][1]["actor"] == "analyst"
    assert db.query(AuditLog).filter_by(action="ALERT_UPDATED").count() == 3


def test_update_validation(client, db, admin_headers):
    user = user_with_history(db)
    ingest_scenario(db, user, "COMBINED_ANOMALY")
    alert_id = db.query(Alert).one().id
    assert client.patch(f"/api/v1/alerts/{alert_id}", json={}, headers=admin_headers).status_code == 422
    assert client.patch(f"/api/v1/alerts/{alert_id}", json={"status": "DELETED"}, headers=admin_headers).status_code == 422
    assert client.patch(f"/api/v1/alerts/{alert_id}", json={"status": "OPEN"}, headers=admin_headers).status_code == 422
    assert client.patch("/api/v1/alerts/9999", json={"note": "x"}, headers=admin_headers).status_code == 404


def test_alert_filters_and_statistics(client, db, admin_headers):
    user = user_with_history(db)
    ingest_scenario(db, user, "COMBINED_ANOMALY")
    level = db.query(Alert).one().risk_level
    assert client.get(f"/api/v1/alerts?risk_level={level}", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/v1/alerts?status=RESOLVED", headers=admin_headers).json()["total"] == 0
    assert client.get("/api/v1/alerts?search=omar", headers=admin_headers).json()["total"] == 1
    assert client.get(f"/api/v1/alerts?date_from={yesterday()}&date_to={yesterday()}",
                      headers=admin_headers).json()["total"] == 1
    assert client.get("/api/v1/alerts?sort=risk_score&order=asc", headers=admin_headers).status_code == 200
    stats = client.get("/api/v1/alerts/statistics", headers=admin_headers).json()
    assert stats["total"] == 1 and stats["by_status"]["OPEN"] == 1 and stats["open_by_level"][level] == 1


def test_analyst_can_resolve_alert_through_legacy_mobile_api(client, db, analyst_headers):
    user = user_with_history(db, username="mobile.analyst.target")
    ingest_scenario(db, user, "COMBINED_ANOMALY", seed=902)
    alert = db.query(Alert).one()
    response = client.put("/alerts/" + str(alert.id), json={"status": "RESOLVED"}, headers=analyst_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RESOLVED"
    assert db.query(AuditLog).filter_by(action="ALERT_UPDATED").count() == 1
