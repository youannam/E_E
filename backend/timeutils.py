"""
Time handling.

Detection works per calendar day and "night" is defined by the clock (22:00-06:00), so
timestamps must be in the organization's local time. We store them WITHOUT timezone
information, in local organization time (ORG_TIMEZONE).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.config import get_settings


def org_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().org_timezone)


def to_org_local(timestamp: datetime) -> datetime:
    """Aware timestamps are converted to organization time; naive ones are assumed to already be local."""
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(org_zone()).replace(tzinfo=None)
    return timestamp.replace(microsecond=0)


def org_now() -> datetime:
    return datetime.now(org_zone()).replace(tzinfo=None, microsecond=0)


def org_today() -> date:
    return org_now().date()
