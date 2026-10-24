"""
Activity ingestion: store validated events, then run the detection pipeline on the affected days.

Used by POST /api/v1/activities, POST /api/v1/activities/batch, the simulator endpoint and
the demo seeding command, so every event (real or simulated) goes through the same path.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.detection.pipeline import analyze_days
from backend.models import Activity, AnalysisResult, Device, MonitoredUser
from backend.schemas import ActivityCreate
from backend.timeutils import org_now, to_org_local

FUTURE_TOLERANCE = timedelta(minutes=5)  # small clock differences between machines are fine


class IngestionError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def device_type_for(event: ActivityCreate) -> str:
    if event.event_type in ("USB_CONNECT", "USB_TRANSFER"):
        return "USB_STORAGE"
    return "WORKSTATION"


def upsert_device(db: Session, event: ActivityCreate, timestamp, known: dict[str, Device]) -> None:
    device = known.get(event.device_id) or db.scalar(select(Device).where(Device.device_id == event.device_id))
    if device is None:
        device = Device(device_id=event.device_id, user_id=event.user_id, device_type=device_type_for(event))
        db.add(device)
    if device.last_seen is None or timestamp > device.last_seen:
        device.last_seen = timestamp
    known[event.device_id] = device


def ingest_activities(db: Session, items: list[ActivityCreate], analyze: bool = True
                      ) -> tuple[list[Activity], list[AnalysisResult]]:
    """Validate references, save all events in one transaction, then analyze each affected user-day."""
    user_ids = {item.user_id for item in items}
    users = {user.id: user for user in db.scalars(select(MonitoredUser).where(MonitoredUser.id.in_(user_ids)))}
    missing = sorted(user_ids - users.keys())
    if missing:
        raise IngestionError(f"Unknown user_id(s): {', '.join(map(str, missing))}", status_code=404)

    latest_allowed = org_now() + FUTURE_TOLERANCE
    activities: list[Activity] = []
    devices: dict[str, Device] = {}
    affected_days = set()

    for item in items:
        timestamp = to_org_local(item.timestamp)
        if timestamp > latest_allowed:
            raise IngestionError(f"Event timestamp {timestamp.isoformat()} is in the future")
        activity = Activity(
            user_id=item.user_id, timestamp=timestamp, event_type=item.event_type, resource=item.resource,
            sensitivity=item.sensitivity, file_size_bytes=item.file_size_bytes, device_id=item.device_id,
            source=item.source, is_simulated=item.is_simulated or item.source == "SIMULATOR", details=item.details,
        )
        activities.append(activity)
        affected_days.add((item.user_id, timestamp.date()))

        user = users[item.user_id]
        if user.last_activity_at is None or timestamp > user.last_activity_at:
            user.last_activity_at = timestamp
        if item.event_type == "LOGIN" and (user.last_login is None or timestamp > user.last_login):
            user.last_login = timestamp
        if item.device_id:
            upsert_device(db, item, timestamp, devices)

    db.add_all(activities)
    db.commit()

    analyses = analyze_days(db, affected_days) if analyze else []
    return activities, analyses
