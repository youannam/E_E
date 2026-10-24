"""
Behavioral feature engineering.

Raw activity events (one row per LOGIN, FILE_DOWNLOAD, ...) are too detailed for a
model or a rule to reason about directly. This module turns all events of ONE user
on ONE calendar day into a fixed list of numbers called a "feature vector".

The same function is used in three places, so training and live detection always
agree on what each feature means:
  * ai/train.py           -> builds the training table
  * backend/detection     -> builds the vector for the day being analyzed
  * the rule engine       -> reads counts such as download_count

This module is also the single source of truth for the event types and
sensitivity levels used across the whole project.
"""

from datetime import datetime

import pandas as pd

FEATURE_SCHEMA_VERSION = "1.0"

EVENT_TYPES = [
    "LOGIN",
    "LOGOUT",
    "FILE_ACCESS",
    "FILE_DOWNLOAD",
    "FILE_UPLOAD",
    "FILE_DELETE",
    "USB_CONNECT",
    "USB_TRANSFER",
    "EMAIL_SENT",
    "APPLICATION_USAGE",
]

# Ordered from least to most sensitive. The order matters: the rule engine compares
# positions in this list to decide whether a role is cleared for a resource.
SENSITIVITY_LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
SENSITIVE_LEVELS = {"CONFIDENTIAL", "RESTRICTED"}

# Events that touch a file or document and therefore count as "resource access".
RESOURCE_EVENT_TYPES = {"FILE_ACCESS", "FILE_DOWNLOAD", "FILE_UPLOAD", "FILE_DELETE", "USB_TRANSFER"}

# A login between 22:00 and 05:59 (local organization time) is a "night login".
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6

BYTES_PER_MB = 1024 * 1024

# The exact order of this list is the order of the columns the model is trained on.
FEATURE_NAMES = [
    "total_events",
    "login_count",
    "night_login_count",
    "night_event_count",
    "unique_active_hours",
    "file_access_count",
    "sensitive_access_count",
    "download_count",
    "download_mb",
    "upload_count",
    "delete_count",
    "usb_event_count",
    "usb_sensitive_transfer_count",
    "email_count",
    "unique_resources",
]

FEATURE_DESCRIPTIONS = {
    "total_events": "Number of events of any type during the day",
    "login_count": "Number of LOGIN events",
    "night_login_count": "LOGIN events between 22:00 and 05:59",
    "night_event_count": "Events of any type between 22:00 and 05:59",
    "unique_active_hours": "Number of distinct clock hours with at least one event",
    "file_access_count": "Number of FILE_ACCESS events",
    "sensitive_access_count": "Events touching CONFIDENTIAL or RESTRICTED resources",
    "download_count": "Number of FILE_DOWNLOAD events",
    "download_mb": "Total size of downloaded files in megabytes",
    "upload_count": "Number of FILE_UPLOAD events",
    "delete_count": "Number of FILE_DELETE events",
    "usb_event_count": "USB_CONNECT plus USB_TRANSFER events",
    "usb_sensitive_transfer_count": "USB_TRANSFER events involving CONFIDENTIAL or RESTRICTED files",
    "email_count": "Number of EMAIL_SENT events",
    "unique_resources": "Number of distinct resources (files) touched",
}


def is_night_hour(hour: int) -> bool:
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


def empty_features() -> dict[str, float]:
    """A day with no activity: every feature is zero."""
    return {name: 0.0 for name in FEATURE_NAMES}


def compute_daily_features(events: list[dict]) -> dict[str, float]:
    """
    Turn a list of events (all from the same user and the same day) into features.

    Each event is a dict with at least "event_type" and "timestamp" (a datetime).
    Optional keys: "resource", "sensitivity", "file_size_bytes".
    Missing optional values are treated as "not applicable" (size 0, no resource).
    """
    features = empty_features()
    active_hours = set()
    resources = set()

    for event in events:
        event_type = event["event_type"]
        timestamp: datetime = event["timestamp"]
        sensitivity = event.get("sensitivity")
        resource = event.get("resource")
        size_bytes = event.get("file_size_bytes") or 0
        is_sensitive = sensitivity in SENSITIVE_LEVELS
        at_night = is_night_hour(timestamp.hour)

        features["total_events"] += 1
        active_hours.add(timestamp.hour)
        if at_night:
            features["night_event_count"] += 1

        if event_type == "LOGIN":
            features["login_count"] += 1
            if at_night:
                features["night_login_count"] += 1
        elif event_type == "FILE_ACCESS":
            features["file_access_count"] += 1
        elif event_type == "FILE_DOWNLOAD":
            features["download_count"] += 1
            features["download_mb"] += size_bytes / BYTES_PER_MB
        elif event_type == "FILE_UPLOAD":
            features["upload_count"] += 1
        elif event_type == "FILE_DELETE":
            features["delete_count"] += 1
        elif event_type == "USB_CONNECT":
            features["usb_event_count"] += 1
        elif event_type == "USB_TRANSFER":
            features["usb_event_count"] += 1
            if is_sensitive:
                features["usb_sensitive_transfer_count"] += 1
        elif event_type == "EMAIL_SENT":
            features["email_count"] += 1

        if event_type in RESOURCE_EVENT_TYPES and resource:
            resources.add(resource)
            if is_sensitive:
                features["sensitive_access_count"] += 1

    features["unique_active_hours"] = float(len(active_hours))
    features["unique_resources"] = float(len(resources))
    features["download_mb"] = round(features["download_mb"], 3)
    return features


def build_feature_table(events: pd.DataFrame) -> pd.DataFrame:
    """
    Build one feature row per (user_id, day) from a table of raw events.

    Expected columns: user_id, timestamp, event_type, resource, sensitivity, file_size_bytes.
    Returns columns: user_id, day, and every name in FEATURE_NAMES.
    Used for training and evaluation, where thousands of user-days are processed at once.
    """
    if events.empty:
        return pd.DataFrame(columns=["user_id", "day", *FEATURE_NAMES])

    events = events.copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    events["day"] = events["timestamp"].dt.date

    rows = []
    for (user_id, day), group in events.groupby(["user_id", "day"], sort=True):
        # pandas uses NaN for empty cells; turn those back into None before computing.
        records = group.astype(object).where(group.notna(), None).to_dict("records")
        for record in records:
            record["timestamp"] = pd.Timestamp(record["timestamp"]).to_pydatetime()
        row = {"user_id": user_id, "day": day}
        row.update(compute_daily_features(records))
        rows.append(row)
    return pd.DataFrame(rows, columns=["user_id", "day", *FEATURE_NAMES])


def validate_feature_vector(features: dict) -> list[float]:
    """
    Check a feature dict before it reaches the model and return it as an ordered list.

    Raises ValueError for missing features, non-numbers, NaN or negative values,
    because the model would otherwise silently produce a meaningless score.
    """
    missing = [name for name in FEATURE_NAMES if name not in features]
    if missing:
        raise ValueError(f"Missing features: {', '.join(missing)}")

    values = []
    for name in FEATURE_NAMES:
        value = features[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Feature '{name}' must be a number, got {value!r}")
        if value != value:  # NaN is the only value that is not equal to itself
            raise ValueError(f"Feature '{name}' is NaN")
        if value < 0:
            raise ValueError(f"Feature '{name}' cannot be negative, got {value}")
        values.append(float(value))
    return values
