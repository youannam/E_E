"""
Cybersecurity rule engine.

Each rule checks for one KNOWN suspicious pattern using an explicit condition, so an
analyst can always see exactly why it fired. Rules are plain functions; the engine runs
every enabled rule and collects structured findings.

A rule function receives a RuleContext (today's features and events, the user's
baseline and job role, and the rule's parameters) and returns either None (not
triggered) or a RuleMatch (reason, evidence and the events that matched).

Rule score = sum of the weights of the triggered rules, capped at 100.
"""

from dataclasses import dataclass, field
from typing import Callable

from ai.features import RESOURCE_EVENT_TYPES, SENSITIVITY_LEVELS, is_night_hour
from backend.detection.baseline import Baseline

MAX_RULE_SCORE = 100


@dataclass
class RuleContext:
    features: dict[str, float]
    events: list[dict]  # each has id, timestamp, event_type, resource, sensitivity, file_size_bytes
    baseline: Baseline
    job_role: str
    parameters: dict


@dataclass
class RuleMatch:
    reason: str
    evidence: dict
    matched_event_ids: list[int] = field(default_factory=list)


@dataclass
class RuleDefinition:
    rule_id: str
    name: str
    description: str
    severity: str  # MEDIUM, HIGH or CRITICAL
    required_fields: list[str]
    time_window: str
    check: Callable[[RuleContext], RuleMatch | None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt(value: float) -> str:
    """Numbers in explanations: at most one decimal place (3.091 -> 3.1, 15.0 -> 15)."""
    return f"{round(value, 1):g}"


def baseline_threshold(baseline: Baseline, feature: str, std_multiplier: float, minimum: float) -> float:
    """max(minimum, mean + k * std) - see rule_config.py for why."""
    personal_limit = baseline.means[feature] + std_multiplier * baseline.stds[feature]
    return round(max(minimum, personal_limit), 2)


def describe_baseline(baseline: Baseline, feature: str) -> str:
    return f"{baseline.baseline_type.lower().replace('_', '-')} baseline average {fmt(baseline.means[feature])}"


def event_ids(events: list[dict]) -> list[int]:
    return [event["id"] for event in events if event.get("id") is not None]


def count_above_baseline(ctx: RuleContext, feature: str, event_type: str | None, minimum_key: str, label: str):
    """Shared logic for the 'more X than usual' rules."""
    observed = ctx.features[feature]
    threshold = baseline_threshold(ctx.baseline, feature, ctx.parameters["std_multiplier"], ctx.parameters[minimum_key])
    if observed <= threshold:
        return None
    matched = [event for event in ctx.events if event["event_type"] == event_type] if event_type else ctx.events
    return RuleMatch(
        reason=f"{fmt(observed)} {label} today, above the threshold of {fmt(threshold)} ({describe_baseline(ctx.baseline, feature)})",
        evidence={"observed": observed, "threshold": threshold, "baseline_type": ctx.baseline.baseline_type,
                  "baseline_mean": ctx.baseline.means[feature], "baseline_std": ctx.baseline.stds[feature]},
        matched_event_ids=event_ids(matched),
    )


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

def check_unusual_login_time(ctx: RuleContext) -> RuleMatch | None:
    night_logins = [e for e in ctx.events if e["event_type"] == "LOGIN" and is_night_hour(e["timestamp"].hour)]
    if not night_logins:
        return None
    usual_rate = ctx.baseline.means["night_login_count"]
    if usual_rate > ctx.parameters["max_usual_night_logins_per_day"]:
        return None  # this person normally works at night (e.g. a night-shift technician)
    times = ", ".join(e["timestamp"].strftime("%H:%M") for e in night_logins)
    return RuleMatch(
        reason=f"{len(night_logins)} login(s) between 22:00 and 06:00 (at {times}); "
               f"usual night logins per day: {fmt(usual_rate)} ({ctx.baseline.baseline_type.lower().replace('_', '-')} baseline)",
        evidence={"night_logins": len(night_logins), "usual_night_logins_per_day": usual_rate},
        matched_event_ids=event_ids(night_logins),
    )


def check_excessive_downloads(ctx: RuleContext) -> RuleMatch | None:
    return count_above_baseline(ctx, "download_count", "FILE_DOWNLOAD", "minimum_count", "file downloads")


def check_excessive_download_volume(ctx: RuleContext) -> RuleMatch | None:
    return count_above_baseline(ctx, "download_mb", "FILE_DOWNLOAD", "minimum_mb", "MB downloaded")


def check_sensitive_resource_access(ctx: RuleContext) -> RuleMatch | None:
    clearance = ctx.parameters["role_clearance"].get(ctx.job_role, ctx.parameters["default_clearance"])
    allowed_rank = SENSITIVITY_LEVELS.index(clearance)
    above = [
        e for e in ctx.events
        if e["event_type"] in RESOURCE_EVENT_TYPES
        and e.get("sensitivity") in SENSITIVITY_LEVELS
        and SENSITIVITY_LEVELS.index(e["sensitivity"]) > allowed_rank
    ]
    if not above:
        return None
    resources = sorted({e["resource"] for e in above if e.get("resource")})
    return RuleMatch(
        reason=f"{len(above)} access(es) to resources above the '{ctx.job_role}' clearance ({clearance}), "
               f"e.g. {', '.join(resources[:3])}",
        evidence={"clearance": clearance, "events_above_clearance": len(above), "resources": resources[:10]},
        matched_event_ids=event_ids(above),
    )


def check_mass_file_deletion(ctx: RuleContext) -> RuleMatch | None:
    return count_above_baseline(ctx, "delete_count", "FILE_DELETE", "minimum_count", "file deletions")


def check_usb_sensitive_transfer(ctx: RuleContext) -> RuleMatch | None:
    transfers = [e for e in ctx.events
                 if e["event_type"] == "USB_TRANSFER" and e.get("sensitivity") in ("CONFIDENTIAL", "RESTRICTED")]
    if len(transfers) < ctx.parameters["minimum_transfers"]:
        return None
    total_mb = sum((e.get("file_size_bytes") or 0) for e in transfers) / (1024 * 1024)
    return RuleMatch(
        reason=f"{len(transfers)} CONFIDENTIAL/RESTRICTED file(s) copied to a USB device ({total_mb:.1f} MB)",
        evidence={"sensitive_usb_transfers": len(transfers), "total_mb": round(total_mb, 2)},
        matched_event_ids=event_ids(transfers),
    )


def check_unusual_resource_access(ctx: RuleContext) -> RuleMatch | None:
    if not ctx.baseline.is_individual:
        return None  # without the user's own history we cannot know what is "new" for them
    touched = [e for e in ctx.events if e["event_type"] in RESOURCE_EVENT_TYPES and e.get("resource")]
    new_events = [e for e in touched if e["resource"] not in ctx.baseline.known_resources]
    new_resources = sorted({e["resource"] for e in new_events})
    if len(new_resources) < ctx.parameters["minimum_new_resources"]:
        return None
    return RuleMatch(
        reason=f"{len(new_resources)} resources never used by this user in the previous "
               f"{ctx.baseline.observation_days} active days, e.g. {', '.join(new_resources[:3])}",
        evidence={"new_resources": len(new_resources), "examples": new_resources[:10]},
        matched_event_ids=event_ids(new_events),
    )


def check_high_activity_volume(ctx: RuleContext) -> RuleMatch | None:
    match = count_above_baseline(ctx, "total_events", None, "minimum_events", "events")
    if match:
        match.matched_event_ids = []  # every event would match; linking all of them adds no information
    return match


RULES: list[RuleDefinition] = [
    RuleDefinition("UNUSUAL_LOGIN_TIME", "Unusual login time",
                   "Login between 22:00 and 06:00 by a user who rarely logs in at night.",
                   "MEDIUM", ["event_type", "timestamp"], "1 day", check_unusual_login_time),
    RuleDefinition("EXCESSIVE_DOWNLOADS", "Excessive downloads",
                   "More file downloads than the user's baseline allows.",
                   "HIGH", ["event_type"], "1 day", check_excessive_downloads),
    RuleDefinition("EXCESSIVE_DOWNLOAD_VOLUME", "Excessive download volume",
                   "Total downloaded megabytes far above the user's baseline.",
                   "HIGH", ["event_type", "file_size_bytes"], "1 day", check_excessive_download_volume),
    RuleDefinition("SENSITIVE_RESOURCE_ACCESS", "Access above role clearance",
                   "Access to resources more sensitive than the user's job role is allowed to use.",
                   "CRITICAL", ["event_type", "resource", "sensitivity"], "1 day", check_sensitive_resource_access),
    RuleDefinition("MASS_FILE_DELETION", "Unusual file deletion volume",
                   "Many more file deletions than the user's baseline allows.",
                   "HIGH", ["event_type"], "1 day", check_mass_file_deletion),
    RuleDefinition("USB_SENSITIVE_TRANSFER", "USB transfer of sensitive files",
                   "CONFIDENTIAL or RESTRICTED files copied to removable USB storage.",
                   "CRITICAL", ["event_type", "sensitivity"], "1 day", check_usb_sensitive_transfer),
    RuleDefinition("UNUSUAL_RESOURCE_ACCESS", "Unusual resource access",
                   "Several resources the user has never used before (needs individual history).",
                   "MEDIUM", ["event_type", "resource"], "1 day vs. previous 30 days", check_unusual_resource_access),
    RuleDefinition("HIGH_ACTIVITY_VOLUME", "Abnormally high activity volume",
                   "Far more events of any type than the user's baseline allows.",
                   "MEDIUM", ["event_type"], "1 day", check_high_activity_volume),
]
RULES_BY_ID = {rule.rule_id: rule for rule in RULES}


def evaluate_rules(features: dict, events: list[dict], baseline: Baseline, job_role: str,
                   settings: dict[str, dict]) -> dict:
    """
    Run every enabled rule.

    settings: {rule_id: {"enabled": bool, "weight": number, "parameters": {...}}}
    Returns {"rule_score": 0-100, "triggered_rules": [...], "matched_event_ids": [...]}
    """
    triggered = []
    matched_ids: set[int] = set()
    for rule in RULES:
        rule_settings = settings.get(rule.rule_id)
        if not rule_settings or not rule_settings["enabled"]:
            continue
        context = RuleContext(features, events, baseline, job_role, rule_settings["parameters"])
        match = rule.check(context)
        if match is None:
            continue
        triggered.append({
            "rule_id": rule.rule_id,
            "name": rule.name,
            "severity": rule.severity,
            "contribution": rule_settings["weight"],
            "reason": match.reason,
            "evidence": match.evidence,
        })
        matched_ids.update(match.matched_event_ids)

    rule_score = min(MAX_RULE_SCORE, sum(finding["contribution"] for finding in triggered))
    return {"rule_score": float(rule_score), "triggered_rules": triggered, "matched_event_ids": sorted(matched_ids)}
