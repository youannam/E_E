from datetime import datetime

import pandas as pd
import pytest

from ai.features import FEATURE_NAMES, build_feature_table, compute_daily_features, empty_features, validate_feature_vector


def event(hour, event_type, resource=None, sensitivity=None, size=None, minute=0):
    return {"timestamp": datetime(2026, 10, 5, hour, minute), "event_type": event_type,
            "resource": resource, "sensitivity": sensitivity, "file_size_bytes": size}


def test_counts_each_event_type():
    events = [
        event(9, "LOGIN"),
        event(9, "FILE_ACCESS", "fs://a", "INTERNAL", minute=5),
        event(10, "FILE_DOWNLOAD", "fs://b", "CONFIDENTIAL", 2 * 1024 * 1024),
        event(10, "FILE_DOWNLOAD", "fs://b", "CONFIDENTIAL", 1024 * 1024, minute=30),
        event(11, "FILE_UPLOAD", "fs://c", "PUBLIC", 100),
        event(12, "FILE_DELETE", "fs://d", "INTERNAL"),
        event(13, "USB_CONNECT"),
        event(13, "USB_TRANSFER", "fs://e", "RESTRICTED", 500, minute=2),
        event(14, "EMAIL_SENT"),
        event(17, "LOGOUT"),
    ]
    features = compute_daily_features(events)
    assert features["total_events"] == 10
    assert features["login_count"] == 1
    assert features["download_count"] == 2
    assert features["download_mb"] == pytest.approx(3.0)
    assert features["upload_count"] == 1
    assert features["delete_count"] == 1
    assert features["usb_event_count"] == 2
    assert features["usb_sensitive_transfer_count"] == 1
    assert features["email_count"] == 1
    assert features["sensitive_access_count"] == 3  # two confidential downloads + restricted USB transfer
    assert features["unique_resources"] == 5
    assert features["unique_active_hours"] == 7  # hours 9, 10, 11, 12, 13, 14 and 17


def test_night_logins_and_events():
    features = compute_daily_features([event(2, "LOGIN"), event(23, "FILE_ACCESS", "fs://x", "PUBLIC"), event(6, "LOGIN")])
    assert features["night_login_count"] == 1  # 06:00 is no longer night
    assert features["night_event_count"] == 2


def test_empty_day_is_all_zero():
    assert compute_daily_features([]) == empty_features()
    assert set(empty_features()) == set(FEATURE_NAMES)


def test_missing_optional_values_are_handled():
    features = compute_daily_features([event(9, "FILE_DOWNLOAD", "fs://a", "INTERNAL", None)])
    assert features["download_mb"] == 0


def test_build_feature_table_one_row_per_user_day():
    rows = [
        {"user_id": "u1", "timestamp": "2026-10-05 09:00", "event_type": "LOGIN", "resource": None, "sensitivity": None, "file_size_bytes": None},
        {"user_id": "u1", "timestamp": "2026-10-05 10:00", "event_type": "FILE_DELETE", "resource": "fs://a", "sensitivity": "INTERNAL", "file_size_bytes": None},
        {"user_id": "u1", "timestamp": "2026-10-06 09:00", "event_type": "LOGIN", "resource": None, "sensitivity": None, "file_size_bytes": None},
        {"user_id": "u2", "timestamp": "2026-10-05 09:00", "event_type": "LOGIN", "resource": None, "sensitivity": None, "file_size_bytes": None},
    ]
    table = build_feature_table(pd.DataFrame(rows))
    assert len(table) == 3
    first = table[(table.user_id == "u1")].iloc[0]
    assert first["delete_count"] == 1 and first["login_count"] == 1


def test_validate_feature_vector_rejects_bad_input():
    good = empty_features()
    assert len(validate_feature_vector(good)) == len(FEATURE_NAMES)

    missing = dict(good)
    del missing["download_count"]
    with pytest.raises(ValueError, match="Missing"):
        validate_feature_vector(missing)
    with pytest.raises(ValueError, match="negative"):
        validate_feature_vector({**good, "download_count": -1})
    with pytest.raises(ValueError, match="NaN"):
        validate_feature_vector({**good, "download_mb": float("nan")})
    with pytest.raises(ValueError, match="number"):
        validate_feature_vector({**good, "email_count": "ten"})
