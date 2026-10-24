"""Unit tests for every cybersecurity rule: triggered, not triggered and edge cases."""

from copy import deepcopy
from datetime import datetime

import pytest

from ai.features import compute_daily_features
from backend.detection.baseline import Baseline
from backend.detection.rule_config import DEFAULT_BASELINE_MEANS, DEFAULT_BASELINE_STDS, DEFAULT_RULE_SETTINGS
from backend.detection.rules import RULES, baseline_threshold, evaluate_rules

MB = 1024 * 1024


def settings():
    return {rule_id: {"enabled": True, "weight": v["weight"], "parameters": deepcopy(v["parameters"])}
            for rule_id, v in DEFAULT_RULE_SETTINGS.items()}


def baseline(kind="INDIVIDUAL", known=None, **means):
    m = dict(DEFAULT_BASELINE_MEANS)
    m.update(means)
    return Baseline(kind, 20, m, dict(DEFAULT_BASELINE_STDS), set(known or []))


def ev(event_id, hour, event_type, resource=None, sensitivity=None, size=None, minute=0):
    return {"id": event_id, "timestamp": datetime(2026, 10, 5, hour, minute), "event_type": event_type,
            "resource": resource, "sensitivity": sensitivity, "file_size_bytes": size}


def run(events, base=None, role="Software Engineer", rule_settings=None):
    base = base or baseline(known=[e["resource"] for e in events if e["resource"]])
    return evaluate_rules(compute_daily_features(events), events, base, role, rule_settings or settings())


def triggered_ids(result):
    return [rule["rule_id"] for rule in result["triggered_rules"]]


def normal_day():
    return [ev(1, 9, "LOGIN"), ev(2, 10, "FILE_ACCESS", "fs://a", "INTERNAL"),
            ev(3, 11, "FILE_DOWNLOAD", "fs://a", "INTERNAL", 2 * MB), ev(4, 17, "LOGOUT")]


def test_every_rule_has_required_metadata():
    for rule in RULES:
        assert rule.rule_id and rule.name and rule.description and rule.required_fields
        assert rule.severity in ("MEDIUM", "HIGH", "CRITICAL")
        assert rule.rule_id in DEFAULT_RULE_SETTINGS


def test_normal_day_triggers_nothing():
    result = run(normal_day())
    assert result["triggered_rules"] == [] and result["rule_score"] == 0


def test_unusual_login_time_triggers_for_day_worker():
    result = run(normal_day() + [ev(9, 2, "LOGIN", minute=15)])
    assert triggered_ids(result) == ["UNUSUAL_LOGIN_TIME"]
    assert 9 in result["matched_event_ids"]
    assert "02:15" in result["triggered_rules"][0]["reason"]


def test_unusual_login_time_respects_night_shift_baseline():
    result = run(normal_day() + [ev(9, 2, "LOGIN")], base=baseline(night_login_count=1.0, known=["fs://a"]))
    assert "UNUSUAL_LOGIN_TIME" not in triggered_ids(result)


def test_excessive_downloads_and_volume():
    downloads = [ev(100 + i, 14, "FILE_DOWNLOAD", "fs://a", "INTERNAL", 20 * MB, minute=i) for i in range(30)]
    result = run(normal_day() + downloads)
    assert {"EXCESSIVE_DOWNLOADS", "EXCESSIVE_DOWNLOAD_VOLUME"} <= set(triggered_ids(result))
    finding = next(r for r in result["triggered_rules"] if r["rule_id"] == "EXCESSIVE_DOWNLOADS")
    assert finding["evidence"]["observed"] == 31 and finding["severity"] == "HIGH"


def test_download_threshold_is_personal():
    downloads = [ev(100 + i, 14, "FILE_DOWNLOAD", "fs://a", "INTERNAL", MB, minute=i) for i in range(20)]
    busy_user = baseline(download_count=25, known=["fs://a"])
    assert "EXCESSIVE_DOWNLOADS" not in triggered_ids(run(downloads, base=busy_user))
    assert "EXCESSIVE_DOWNLOADS" in triggered_ids(run(downloads))


def test_count_exactly_at_threshold_does_not_trigger():
    base = baseline(known=["fs://a"])
    threshold = baseline_threshold(base, "delete_count", 3, 20)
    deletions = [ev(i, 15, "FILE_DELETE", "fs://a", "INTERNAL", minute=i % 60) for i in range(int(threshold))]
    assert "MASS_FILE_DELETION" not in triggered_ids(run(deletions, base=base))
    deletions.append(ev(999, 16, "FILE_DELETE", "fs://a", "INTERNAL"))
    assert "MASS_FILE_DELETION" in triggered_ids(run(deletions, base=base))


def test_sensitive_access_above_clearance():
    restricted = ev(50, 11, "FILE_ACCESS", "fs://hr/records/employee_records.xlsx", "RESTRICTED")
    result = run(normal_day() + [restricted])
    assert "SENSITIVE_RESOURCE_ACCESS" in triggered_ids(result)
    assert 50 in result["matched_event_ids"]
    # The same file is fine for a role cleared for RESTRICTED data.
    assert "SENSITIVE_RESOURCE_ACCESS" not in triggered_ids(run(normal_day() + [restricted], role="HR Manager"))


def test_unknown_role_uses_default_clearance():
    confidential = ev(50, 11, "FILE_ACCESS", "fs://x", "CONFIDENTIAL")
    assert "SENSITIVE_RESOURCE_ACCESS" in triggered_ids(run([confidential], role="Intern"))


def test_usb_sensitive_transfer_is_critical():
    usb = [ev(60, 13, "USB_CONNECT"), ev(61, 13, "USB_TRANSFER", "fs://a", "CONFIDENTIAL", 5 * MB, minute=2)]
    result = run(normal_day() + usb)
    finding = next(r for r in result["triggered_rules"] if r["rule_id"] == "USB_SENSITIVE_TRANSFER")
    assert finding["severity"] == "CRITICAL"


def test_usb_transfer_of_public_file_is_not_flagged():
    usb = [ev(60, 13, "USB_CONNECT"), ev(61, 13, "USB_TRANSFER", "fs://a", "PUBLIC", MB, minute=2)]
    assert "USB_SENSITIVE_TRANSFER" not in triggered_ids(run(normal_day() + usb))


def test_unusual_resource_access_needs_individual_history():
    new_files = [ev(70 + i, 12, "FILE_ACCESS", f"fs://new/{i}", "INTERNAL", minute=i) for i in range(6)]
    events = normal_day() + new_files
    assert "UNUSUAL_RESOURCE_ACCESS" in triggered_ids(run(events, base=baseline(known=["fs://a"])))
    assert "UNUSUAL_RESOURCE_ACCESS" not in triggered_ids(run(events, base=baseline("PEER_GROUP")))
    assert "UNUSUAL_RESOURCE_ACCESS" not in triggered_ids(run(events, base=baseline("DEFAULT")))


def test_high_activity_volume():
    emails = [ev(200 + i, 10 + i % 7, "EMAIL_SENT", minute=i % 60) for i in range(130)]
    assert "HIGH_ACTIVITY_VOLUME" in triggered_ids(run(normal_day() + emails))


def test_disabled_rule_is_skipped():
    rule_settings = settings()
    rule_settings["UNUSUAL_LOGIN_TIME"]["enabled"] = False
    result = run(normal_day() + [ev(9, 2, "LOGIN")], rule_settings=rule_settings)
    assert result["triggered_rules"] == []


def test_configurable_threshold_changes_result():
    rule_settings = settings()
    rule_settings["EXCESSIVE_DOWNLOADS"]["parameters"]["minimum_count"] = 2
    downloads = [ev(100 + i, 14, "FILE_DOWNLOAD", "fs://a", "INTERNAL", MB, minute=i) for i in range(12)]
    base = baseline(download_count=0, known=["fs://a"])
    base.stds["download_count"] = 0
    assert "EXCESSIVE_DOWNLOADS" not in triggered_ids(run(downloads, base=base))
    assert "EXCESSIVE_DOWNLOADS" in triggered_ids(run(downloads, base=base, rule_settings=rule_settings))


def test_rule_score_is_sum_of_weights_capped_at_100():
    events = (normal_day() + [ev(9, 2, "LOGIN"), ev(10, 2, "FILE_ACCESS", "fs://secret", "RESTRICTED", minute=5),
                              ev(11, 2, "USB_CONNECT", minute=6),
                              ev(12, 2, "USB_TRANSFER", "fs://secret", "RESTRICTED", 50 * MB, minute=7)]
              + [ev(100 + i, 3, "FILE_DOWNLOAD", "fs://a", "INTERNAL", 30 * MB, minute=i) for i in range(30)])
    result = run(events, base=baseline(known=["fs://a"]))
    assert sum(r["contribution"] for r in result["triggered_rules"]) > 100
    assert result["rule_score"] == pytest.approx(100)
