"""
End-to-end acceptance scenario (specification section 16), through the HTTP API only.

The web dashboard and Flutter app read the same endpoints used here; the browser test in
tests/e2e/ checks the web dashboard on top of a running server.
"""

from backend.models import AnalysisResult, MonitoredUser
from tests.conftest import add_normal_history, yesterday
from simulator.catalog import find_demo_employee


def test_full_detection_workflow(client, db, admin_headers, analyst_headers):
    # 1-3. Clean database (fixture), demo accounts exist, the real model is trained and loaded.
    assert client.get("/api/v1/models/status", headers=admin_headers).json()["loaded"] is True

    # 4-6. A brand-new user with a normal day must not get an unjustified critical alert.
    new_user = client.post("/api/v1/users", headers=admin_headers,
                           json={"username": "brand.new", "department": "Finance", "job_role": "Accountant"}).json()
    normal = client.post("/api/v1/simulator/run", headers=admin_headers,
                         json={"scenario_id": "NORMAL_USER", "user_id": new_user["id"], "seed": 5}).json()
    assert normal["analysis"]["baseline_type"] == "DEFAULT"
    assert normal["analysis"]["risk_level"] != "CRITICAL"
    assert normal["alert"] is None

    # A user with history then performs the combined suspicious scenario.
    employee = find_demo_employee("omar.hassan")
    user = MonitoredUser(username=employee.username, department=employee.department, job_role=employee.job_role)
    db.add(user)
    db.commit()
    add_normal_history(db, user, employee)
    result = client.post("/api/v1/simulator/run", headers=admin_headers,
                         json={"scenario_id": "COMBINED_ANOMALY", "user_id": user.id, "seed": 42}).json()
    analysis = result["analysis"]

    # 8. Rules executed.  9. The AI model executed.  10. The combined score was calculated.
    assert len(analysis["triggered_rules"]) >= 3
    assert analysis["ai_status"] == "OK" and analysis["ai_score"] is not None and analysis["model_version"]
    breakdown = analysis["score_breakdown"]
    expected = round(breakdown["rule_weight"] * analysis["rule_score"] + breakdown["ai_weight"] * analysis["ai_score"], 1)
    assert breakdown["weighted_score"] == expected
    assert analysis["risk_score"] >= expected

    # 11. The alert is persisted.  12-13. Any client (web or Flutter) reading the API gets it.
    alert_id = result["alert"]["id"]
    stored = db.get(AnalysisResult, analysis["id"])
    assert stored.alert_id == alert_id
    as_analyst = client.get(f"/api/v1/alerts/{alert_id}", headers=analyst_headers).json()
    assert as_analyst["risk_score"] == analysis["risk_score"]

    # 14-15. Change the status; the change persists and every client sees it.
    client.patch(f"/api/v1/alerts/{alert_id}", headers=analyst_headers, json={"status": "INVESTIGATING"})
    listed = client.get("/api/v1/alerts?status=INVESTIGATING", headers=admin_headers).json()
    assert [item["id"] for item in listed["items"]] == [alert_id]
    assert result["date"] == yesterday().isoformat()
