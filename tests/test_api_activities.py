"""Activity ingestion: validation, persistence and automatic analysis."""

from datetime import timedelta

from backend.models import Activity, AnalysisResult, Device
from backend.timeutils import org_now
from tests.conftest import add_user, yesterday


def activity(user_id, hour=9, **overrides):
    day = yesterday()
    body = {"user_id": user_id, "timestamp": f"{day.isoformat()}T{hour:02d}:00:00", "event_type": "LOGIN",
            "device_id": "WS-TEST-1"}
    body.update(overrides)
    return body


def test_ingest_single_activity_runs_analysis(client, db, admin_headers):
    user = add_user(db)
    response = client.post("/api/v1/activities", json=activity(user.id), headers=admin_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 1 and len(body["analyses"]) == 1
    analysis = body["analyses"][0]
    assert analysis["ai_status"] == "OK" and analysis["model_version"]
    assert analysis["baseline_type"] == "DEFAULT"  # brand-new user, nobody else has history
    assert db.query(Activity).count() == 1
    assert db.query(Device).filter_by(device_id="WS-TEST-1").one().user_id == user.id


def test_batch_ingestion_analyzes_each_day_once(client, db, admin_headers):
    user = add_user(db)
    day1 = [activity(user.id, hour) for hour in (9, 10, 11)]
    day2 = [dict(item, timestamp=item["timestamp"].replace(yesterday().isoformat(),
                                                           (yesterday() - timedelta(days=1)).isoformat()))
            for item in day1]
    response = client.post("/api/v1/activities/batch", json={"activities": day1 + day2}, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["created"] == 6
    assert len(response.json()["analyses"]) == 2
    assert db.query(AnalysisResult).count() == 2


def test_validation_errors(client, db, admin_headers):
    user = add_user(db)
    cases = [
        activity(user.id, event_type="HACK_THE_PLANET"),                       # unknown event type
        activity(user.id, event_type="FILE_DOWNLOAD"),                          # resource required
        activity(user.id, resource="fs://a"),                                   # sensitivity required with resource
        activity(user.id, event_type="FILE_DOWNLOAD", resource="fs://a", sensitivity="TOP_SECRET"),
        activity(user.id, file_size_bytes=-5),
        activity(user.id, device_id="bad device id with spaces"),
        activity(user.id, unexpected_field=1),
        activity(0),
    ]
    for body in cases:
        assert client.post("/api/v1/activities", json=body, headers=admin_headers).status_code == 422, body
    assert client.post("/api/v1/activities/batch", json={"activities": []}, headers=admin_headers).status_code == 422


def test_future_timestamp_and_unknown_user(client, db, admin_headers):
    user = add_user(db)
    future = (org_now() + timedelta(hours=2)).isoformat()
    response = client.post("/api/v1/activities", json=activity(user.id, timestamp=future), headers=admin_headers)
    assert response.status_code == 422 and "future" in response.json()["detail"]
    assert client.post("/api/v1/activities", json=activity(9999), headers=admin_headers).status_code == 404
    assert db.query(Activity).count() == 0


def test_timezone_aware_timestamps_are_converted(client, db, admin_headers):
    user = add_user(db)
    day = yesterday().isoformat()
    client.post("/api/v1/activities", json=activity(user.id, timestamp=f"{day}T07:00:00+00:00"), headers=admin_headers)
    stored = db.query(Activity).one()
    assert stored.timestamp.hour == 10  # Africa/Cairo is UTC+3 in October 2026


def test_activity_list_filters(client, db, admin_headers):
    user = add_user(db)
    other = add_user(db, "other.user")
    items = [activity(user.id), activity(user.id, 10, event_type="FILE_ACCESS", resource="fs://payroll", sensitivity="RESTRICTED"),
             activity(other.id, 11)]
    client.post("/api/v1/activities/batch", json={"activities": items}, headers=admin_headers)
    page = client.get(f"/api/v1/activities?user_id={user.id}", headers=admin_headers).json()
    assert page["total"] == 2
    assert client.get("/api/v1/activities?sensitivity=RESTRICTED", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/v1/activities?search=payroll", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/v1/activities?event_type=LOGIN&page_size=1", headers=admin_headers).json()["items"][0]["event_type"] == "LOGIN"
