"""
Synthetic activity generator.

Every function receives a random.Random object. Passing a Random created with a fixed
seed makes the output repeatable: the same seed always produces the same events.

An event is a plain dict:
    {
        "timestamp": datetime,            # local organization time
        "event_type": "FILE_DOWNLOAD",    # one of ai.features.EVENT_TYPES
        "resource": "fs://finance/...",   # or None
        "sensitivity": "CONFIDENTIAL",    # or None
        "file_size_bytes": 2400000,       # or None
        "device_id": "WS-OMAR-HASSAN",    # or None
        "details": {...},                 # extra info, e.g. the scenario name
    }
The caller adds the user identity before sending events to the backend.
"""

import random
from datetime import date, datetime, timedelta

from ai.features import BYTES_PER_MB, SENSITIVITY_LEVELS
from simulator.catalog import (
    APPLICATIONS,
    DEPARTMENT_RESOURCES,
    ROLE_HABIT_MAX_SENSITIVITY,
    SHARED_RESOURCES,
    Employee,
)

USUAL_RESOURCE_COUNT = 8
CHANCE_OF_UNUSUAL_RESOURCE = 0.08  # small chance a normal event touches a less familiar file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def workstation_id(employee: Employee) -> str:
    return "WS-" + employee.username.replace(".", "-").upper()


def usb_device_id(employee: Employee) -> str:
    return "USB-" + employee.username.replace(".", "-").upper()


def sensitivity_rank(level: str) -> int:
    return SENSITIVITY_LEVELS.index(level)


def resources_within(employee: Employee, max_level: str) -> dict[str, str]:
    """Department + shared resources whose sensitivity is at most max_level."""
    department_files = DEPARTMENT_RESOURCES.get(employee.department, {})
    candidates = {**department_files, **SHARED_RESOURCES}
    limit = sensitivity_rank(max_level)
    return {path: level for path, level in candidates.items() if sensitivity_rank(level) <= limit}


def usual_resources(employee: Employee) -> dict[str, str]:
    """
    The handful of files this employee touches most days.

    Seeded by the username (not by the day), so the same employee always gets the
    same set. This gives every user a stable "normal" that unusual access can stand out from.
    """
    habit_level = ROLE_HABIT_MAX_SENSITIVITY.get(employee.job_role, "INTERNAL")
    allowed = sorted(resources_within(employee, habit_level))
    personal_rng = random.Random("usual-resources:" + employee.username)
    count = min(USUAL_RESOURCE_COUNT, len(allowed))
    chosen = personal_rng.sample(allowed, count)
    everything = resources_within(employee, habit_level)
    return {path: everything[path] for path in chosen}


def pick_normal_resource(employee: Employee, rng: random.Random) -> tuple[str, str]:
    if rng.random() < CHANCE_OF_UNUSUAL_RESOURCE:
        habit_level = ROLE_HABIT_MAX_SENSITIVITY.get(employee.job_role, "INTERNAL")
        pool = resources_within(employee, habit_level)
    else:
        pool = usual_resources(employee)
    path = rng.choice(sorted(pool))
    return path, pool[path]


def random_time_between(start: datetime, end: datetime, rng: random.Random) -> datetime:
    seconds = max(1, int((end - start).total_seconds()))
    return start + timedelta(seconds=rng.randint(0, seconds - 1))


def file_size_bytes(rng: random.Random, typical_mb: float = 2.0, max_mb: float = 60.0) -> int:
    """Most office files are small; a few are large (a log-normal distribution)."""
    size_mb = min(max_mb, rng.lognormvariate(0, 0.9) * typical_mb)
    return int(max(0.01, size_mb) * BYTES_PER_MB)


def make_event(timestamp, event_type, device_id, resource=None, sensitivity=None, size=None, details=None) -> dict:
    return {
        "timestamp": timestamp.replace(microsecond=0),
        "event_type": event_type,
        "resource": resource,
        "sensitivity": sensitivity,
        "file_size_bytes": size,
        "device_id": device_id,
        "details": details or {},
    }


def count_around(rng: random.Random, average: float, spread: float) -> int:
    """A whole number near `average` (never negative)."""
    return max(0, round(rng.gauss(average, spread)))


# ---------------------------------------------------------------------------
# Normal behavior
# ---------------------------------------------------------------------------

def working_hours(employee: Employee, day: date, rng: random.Random) -> tuple[datetime, datetime]:
    """Start and end of the employee's working day."""
    if employee.night_shift:
        start = datetime(day.year, day.month, day.day, 0, 30) + timedelta(minutes=rng.randint(0, 50))
        return start, start + timedelta(hours=8, minutes=rng.randint(-20, 20))
    start = datetime(day.year, day.month, day.day, employee.work_start_hour) + timedelta(minutes=rng.randint(0, 50))
    end = start + timedelta(hours=8, minutes=rng.randint(-30, 45))
    return start, end


def generate_normal_day(employee: Employee, day: date, rng: random.Random) -> list[dict]:
    """One ordinary working day: login, routine file work, emails, logout."""
    device = workstation_id(employee)
    level = employee.activity_level
    start, end = working_hours(employee, day, rng)
    events = [make_event(start, "LOGIN", device, details={"method": "password"})]

    # Some people log in again after lunch (screen lock / laptop restart).
    if rng.random() < 0.3:
        midday = start + timedelta(hours=4, minutes=rng.randint(0, 40))
        events.append(make_event(midday, "LOGIN", device, details={"method": "password"}))

    def add_file_events(event_type: str, how_many: int, typical_mb: float | None = None):
        for _ in range(how_many):
            path, sensitivity = pick_normal_resource(employee, rng)
            size = file_size_bytes(rng, typical_mb) if typical_mb else None
            when = random_time_between(start, end, rng)
            events.append(make_event(when, event_type, device, path, sensitivity, size))

    add_file_events("FILE_ACCESS", count_around(rng, 16 * level, 4))
    add_file_events("FILE_DOWNLOAD", count_around(rng, 3 * level, 1.5), typical_mb=2.0)
    add_file_events("FILE_UPLOAD", count_around(rng, 2 * level, 1.2), typical_mb=1.5)
    add_file_events("FILE_DELETE", count_around(rng, 1 * level, 1.0))

    for _ in range(count_around(rng, 10 * level, 3)):
        events.append(make_event(random_time_between(start, end, rng), "EMAIL_SENT", device,
                                 details={"recipients": rng.randint(1, 4), "external": rng.random() < 0.15}))
    for _ in range(count_around(rng, 8, 2)):
        events.append(make_event(random_time_between(start, end, rng), "APPLICATION_USAGE", device,
                                 details={"application": rng.choice(APPLICATIONS)}))

    # Occasionally a normal user plugs in a USB stick and copies a non-sensitive file.
    if rng.random() < 0.05:
        usb = usb_device_id(employee)
        when = random_time_between(start, end - timedelta(minutes=20), rng)
        events.append(make_event(when, "USB_CONNECT", usb))
        public_files = resources_within(employee, "INTERNAL")
        path = rng.choice(sorted(public_files))
        events.append(make_event(when + timedelta(minutes=3), "USB_TRANSFER", usb, path,
                                 public_files[path], file_size_bytes(rng)))

    events.append(make_event(end, "LOGOUT", device))
    events.sort(key=lambda event: event["timestamp"])
    return events


# ---------------------------------------------------------------------------
# Suspicious and unusual behavior that scenarios add on top of a normal day
# ---------------------------------------------------------------------------

def other_department_sensitive_files(employee: Employee) -> dict[str, str]:
    """CONFIDENTIAL / RESTRICTED files that belong to OTHER departments."""
    found = {}
    for department, files in DEPARTMENT_RESOURCES.items():
        if department == employee.department:
            continue
        for path, level in files.items():
            if level in ("CONFIDENTIAL", "RESTRICTED"):
                found[path] = level
    return found


def own_sensitive_files(employee: Employee) -> dict[str, str]:
    files = DEPARTMENT_RESOURCES.get(employee.department, {})
    return {path: level for path, level in files.items() if level in ("CONFIDENTIAL", "RESTRICTED")}


def at(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute)


def add_night_login(employee: Employee, day: date, rng: random.Random, hour: int = 2) -> list[dict]:
    device = workstation_id(employee)
    login_time = at(day, hour, rng.randint(0, 40))
    events = [make_event(login_time, "LOGIN", device, details={"method": "vpn"})]
    for minute in range(3):
        path, sensitivity = pick_normal_resource(employee, rng)
        events.append(make_event(login_time + timedelta(minutes=2 + minute * 4), "FILE_ACCESS", device, path, sensitivity))
    events.append(make_event(login_time + timedelta(minutes=25), "LOGOUT", device))
    return events


def add_download_burst(employee: Employee, start: datetime, rng: random.Random, count: int, typical_mb: float) -> list[dict]:
    device = workstation_id(employee)
    pool = resources_within(employee, ROLE_HABIT_MAX_SENSITIVITY.get(employee.job_role, "INTERNAL"))
    events = []
    for index in range(count):
        path = rng.choice(sorted(pool))
        when = start + timedelta(seconds=index * rng.randint(40, 90))
        events.append(make_event(when, "FILE_DOWNLOAD", device, path, pool[path],
                                 file_size_bytes(rng, typical_mb, max_mb=typical_mb * 4)))
    return events


def add_sensitive_access(employee: Employee, start: datetime, rng: random.Random, count: int) -> list[dict]:
    device = workstation_id(employee)
    pool = other_department_sensitive_files(employee)
    events = []
    for index in range(count):
        path = rng.choice(sorted(pool))
        events.append(make_event(start + timedelta(minutes=index * 3), "FILE_ACCESS", device, path, pool[path]))
    return events


def add_mass_deletion(employee: Employee, start: datetime, rng: random.Random, count: int) -> list[dict]:
    device = workstation_id(employee)
    pool = resources_within(employee, "CONFIDENTIAL")
    events = []
    for index in range(count):
        path = rng.choice(sorted(pool))
        # Different file names so each deletion is a separate file in the same folder.
        deleted = f"{path.rsplit('.', 1)[0]}_copy{index}.{path.rsplit('.', 1)[-1]}" if "." in path else f"{path}/item{index}"
        events.append(make_event(start + timedelta(seconds=index * 15), "FILE_DELETE", device, deleted, pool[path]))
    return events


def add_usb_exfiltration(employee: Employee, start: datetime, rng: random.Random, count: int) -> list[dict]:
    usb = usb_device_id(employee)
    pool = {**own_sensitive_files(employee), **other_department_sensitive_files(employee)}
    events = [make_event(start, "USB_CONNECT", usb, details={"device_label": "Removable Disk"})]
    for index in range(count):
        path = rng.choice(sorted(pool))
        events.append(make_event(start + timedelta(minutes=2 + index * 2), "USB_TRANSFER", usb, path, pool[path],
                                 file_size_bytes(rng, typical_mb=20, max_mb=120)))
    return events


def tag(events: list[dict], scenario_id: str) -> list[dict]:
    """Mark every event with the scenario that produced it (shown in the UI)."""
    for event in events:
        event["details"] = {**event.get("details", {}), "scenario": scenario_id, "simulated": True}
    return events
