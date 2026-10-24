"""
Demonstration scenarios (A-H from the project specification).

Each scenario builds the events of ONE employee for ONE day. Suspicious scenarios
start from a normal working day and add suspicious activity on top, because real
insiders also do their normal job on the day they misbehave.

`intensity` (1, 2 or 3) multiplies how much suspicious activity is added.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from simulator import generator as gen
from simulator.catalog import Employee


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    expected_signals: list[str]  # what an analyst should expect to see (not guaranteed numbers)
    suspicious: bool
    build: Callable[[Employee, date, random.Random, int], list[dict]]


def normal_user(employee, day, rng, intensity):
    return gen.generate_normal_day(employee, day, rng)


def unusual_login(employee, day, rng, intensity):
    events = gen.generate_normal_day(employee, day, rng)
    return events + gen.add_night_login(employee, day, rng, hour=2)


def excessive_downloads(employee, day, rng, intensity):
    events = gen.generate_normal_day(employee, day, rng)
    burst_start = gen.at(day, 14, rng.randint(0, 30))
    return events + gen.add_download_burst(employee, burst_start, rng, count=30 * intensity, typical_mb=15)


def sensitive_access(employee, day, rng, intensity):
    events = gen.generate_normal_day(employee, day, rng)
    return events + gen.add_sensitive_access(employee, gen.at(day, 11, rng.randint(0, 30)), rng, count=5 * intensity)


def mass_deletion(employee, day, rng, intensity):
    events = gen.generate_normal_day(employee, day, rng)
    return events + gen.add_mass_deletion(employee, gen.at(day, 15, rng.randint(0, 30)), rng, count=40 * intensity)


def usb_transfer(employee, day, rng, intensity):
    events = gen.generate_normal_day(employee, day, rng)
    return events + gen.add_usb_exfiltration(employee, gen.at(day, 13, rng.randint(0, 30)), rng, count=4 * intensity)


def combined_anomaly(employee, day, rng, intensity):
    """Night login, then sensitive access, a download burst and USB copying within ~2 hours."""
    events = gen.generate_normal_day(employee, day, rng)
    night_start = gen.at(day, 1, rng.randint(10, 40))
    events.append(gen.make_event(night_start, "LOGIN", gen.workstation_id(employee), details={"method": "vpn"}))
    events += gen.add_sensitive_access(employee, night_start + timedelta(minutes=5), rng, count=4 * intensity)
    events += gen.add_download_burst(employee, night_start + timedelta(minutes=20), rng, count=25 * intensity, typical_mb=20)
    events += gen.add_usb_exfiltration(employee, night_start + timedelta(minutes=70), rng, count=4 * intensity)
    return events


def benign_exception(employee, day, rng, intensity):
    """
    A deadline day: the employee starts early, stays late (but not at night), and
    works with many more of their OWN department's normal files than usual.
    Nothing here breaks policy, but it is unusual, so the AI may still score it higher.
    This scenario exists to show why an anomaly is not proof of wrongdoing.
    """
    events = gen.generate_normal_day(employee, day, rng)
    device = gen.workstation_id(employee)
    early = gen.at(day, 7, rng.randint(0, 20))
    late = gen.at(day, 21, rng.randint(0, 20))
    events.append(gen.make_event(early, "LOGIN", device, details={"method": "password", "note": "deadline"}))
    pool = gen.resources_within(employee, "INTERNAL")
    for _ in range(12 * intensity):
        path = rng.choice(sorted(pool))
        events.append(gen.make_event(gen.random_time_between(early, late, rng), "FILE_ACCESS", device, path, pool[path]))
    for _ in range(4 * intensity):
        path = rng.choice(sorted(pool))
        events.append(gen.make_event(gen.random_time_between(early, late, rng), "FILE_UPLOAD", device, path,
                                     pool[path], gen.file_size_bytes(rng)))
    for _ in range(5 * intensity):
        events.append(gen.make_event(gen.random_time_between(early, late, rng), "EMAIL_SENT", device,
                                     details={"recipients": 3, "external": False}))
    events.append(gen.make_event(late, "LOGOUT", device))
    return events


SCENARIOS: dict[str, Scenario] = {
    scenario.id: scenario
    for scenario in [
        Scenario("NORMAL_USER", "A - Normal user",
                 "An ordinary working day during the employee's usual hours.",
                 ["Low risk score", "No cybersecurity rules triggered in most runs"], False, normal_user),
        Scenario("UNUSUAL_LOGIN", "B - Unusual login time",
                 "A normal day plus a short VPN login at about 02:00.",
                 ["UNUSUAL_LOGIN_TIME rule (unless the user normally works nights)"], True, unusual_login),
        Scenario("EXCESSIVE_DOWNLOADS", "C - Excessive downloads",
                 "A normal day plus a burst of large file downloads in the afternoon.",
                 ["EXCESSIVE_DOWNLOADS rule", "EXCESSIVE_DOWNLOAD_VOLUME rule", "Elevated AI anomaly score"], True,
                 excessive_downloads),
        Scenario("SENSITIVE_ACCESS", "D - Sensitive resource access",
                 "A normal day plus access to CONFIDENTIAL/RESTRICTED files of other departments.",
                 ["SENSITIVE_RESOURCE_ACCESS rule", "UNUSUAL_RESOURCE_ACCESS rule"], True, sensitive_access),
        Scenario("MASS_DELETION", "E - Mass file deletion",
                 "A normal day plus dozens of file deletions within a few minutes.",
                 ["MASS_FILE_DELETION rule", "Elevated AI anomaly score"], True, mass_deletion),
        Scenario("USB_TRANSFER", "F - USB transfer of sensitive files",
                 "A normal day plus copying sensitive files to a USB storage device.",
                 ["USB_SENSITIVE_TRANSFER rule (CRITICAL severity)"], True, usb_transfer),
        Scenario("COMBINED_ANOMALY", "G - Combined anomaly",
                 "Night login, sensitive access, a large download burst and USB copying within about two hours.",
                 ["Several rules at once", "High AI anomaly score", "HIGH or CRITICAL alert"], True, combined_anomaly),
        Scenario("BENIGN_EXCEPTION", "H - Benign exception (deadline day)",
                 "Legitimate but unusual: a long deadline day with more of the user's own normal files.",
                 ["Few or no rules", "AI score may be elevated: shows why an anomaly is not proof of wrongdoing"],
                 False, benign_exception),
    ]
}


def run_scenario(scenario_id: str, employee: Employee, day: date, seed: int = 42, intensity: int = 1) -> list[dict]:
    """Generate the events for one scenario. Same inputs + same seed = same events."""
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario_id}'")
    if intensity not in (1, 2, 3):
        raise ValueError("intensity must be 1, 2 or 3")
    # The seed is combined with the user and day so that two users never get identical days.
    rng = random.Random(f"{seed}:{scenario_id}:{employee.username}:{day.isoformat()}")
    events = SCENARIOS[scenario_id].build(employee, day, rng, intensity)
    events.sort(key=lambda event: event["timestamp"])
    return gen.tag(events, scenario_id)
