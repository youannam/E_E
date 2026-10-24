from datetime import date

import pytest

from ai.features import EVENT_TYPES, SENSITIVITY_LEVELS, compute_daily_features
from simulator.catalog import DEMO_EMPLOYEES, find_demo_employee
from simulator.scenarios import SCENARIOS, run_scenario

DAY = date(2026, 10, 5)
EMPLOYEE = find_demo_employee("omar.hassan")


def test_same_seed_gives_same_events():
    assert run_scenario("COMBINED_ANOMALY", EMPLOYEE, DAY, seed=1) == run_scenario("COMBINED_ANOMALY", EMPLOYEE, DAY, seed=1)
    assert run_scenario("COMBINED_ANOMALY", EMPLOYEE, DAY, seed=1) != run_scenario("COMBINED_ANOMALY", EMPLOYEE, DAY, seed=2)


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_every_scenario_produces_valid_tagged_events(scenario_id):
    events = run_scenario(scenario_id, EMPLOYEE, DAY)
    assert events
    for event in events:
        assert event["event_type"] in EVENT_TYPES
        assert event["timestamp"].date() == DAY
        assert event["sensitivity"] is None or event["sensitivity"] in SENSITIVITY_LEVELS
        assert event["details"]["scenario"] == scenario_id and event["details"]["simulated"] is True
    assert [e["timestamp"] for e in events] == sorted(e["timestamp"] for e in events)


def test_combined_anomaly_contains_all_signals():
    features = compute_daily_features(run_scenario("COMBINED_ANOMALY", EMPLOYEE, DAY))
    normal = compute_daily_features(run_scenario("NORMAL_USER", EMPLOYEE, DAY))
    assert features["night_login_count"] >= 1
    assert features["usb_sensitive_transfer_count"] >= 1
    assert features["download_count"] > normal["download_count"] + 20


def test_intensity_scales_suspicious_activity():
    low = compute_daily_features(run_scenario("MASS_DELETION", EMPLOYEE, DAY, intensity=1))
    high = compute_daily_features(run_scenario("MASS_DELETION", EMPLOYEE, DAY, intensity=3))
    assert high["delete_count"] > low["delete_count"] + 50


def test_invalid_input():
    with pytest.raises(ValueError):
        run_scenario("NOT_A_SCENARIO", EMPLOYEE, DAY)
    with pytest.raises(ValueError):
        run_scenario("NORMAL_USER", EMPLOYEE, DAY, intensity=5)


def test_demo_employees_are_unique_and_synthetic():
    usernames = [employee.username for employee in DEMO_EMPLOYEES]
    assert len(usernames) == len(set(usernames))
    assert any(employee.night_shift for employee in DEMO_EMPLOYEES)
