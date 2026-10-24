"""
Risk scoring: combine the rule score and the AI anomaly score into one number (0-100).

    final = RULE_WEIGHT x rule_score + AI_WEIGHT x ai_score        (defaults 0.4 and 0.6)

Two documented adjustments:
  1. If the AI model is unavailable, final = rule_score (rules only). The result clearly
     says so; we never invent an AI score.
  2. Severity floor: if a CRITICAL-severity rule fired (e.g. sensitive files copied to USB,
     or access above the role's clearance), the final score is at least the HIGH boundary.
     Otherwise a clear policy violation could be hidden by a low AI score on an
     otherwise ordinary day.

Overlapping signals: a burst of downloads may trigger both EXCESSIVE_DOWNLOADS and
EXCESSIVE_DOWNLOAD_VOLUME and also raise the AI score. We accept this on purpose - several
independent views agreeing makes the day more suspicious - but the rule score is capped at
100 so overlaps cannot push it beyond the scale.
"""

from backend.config import Settings


def risk_level(score: float, settings: Settings) -> str:
    if score >= settings.risk_critical_min:
        return "CRITICAL"
    if score >= settings.risk_high_min:
        return "HIGH"
    if score >= settings.risk_medium_min:
        return "MEDIUM"
    return "LOW"


def calculate_risk(rule_score: float, ai_score: float | None, triggered_rules: list[dict], settings: Settings) -> dict:
    """Returns the final score, its level and a breakdown that the UI shows to the analyst."""
    if ai_score is None:
        weighted = rule_score
        formula = f"AI unavailable, so final = rule score = {rule_score:g}"
    else:
        weighted = settings.risk_rule_weight * rule_score + settings.risk_ai_weight * ai_score
        formula = (f"{settings.risk_rule_weight:g} x {rule_score:g} (rules) + "
                   f"{settings.risk_ai_weight:g} x {ai_score:g} (AI) = {weighted:.1f}")

    final = weighted
    floor_applied = False
    if any(rule["severity"] == "CRITICAL" for rule in triggered_rules) and final < settings.risk_high_min:
        final = settings.risk_high_min
        floor_applied = True
        formula += f"; raised to {settings.risk_high_min:g} because a CRITICAL rule fired"

    final = round(min(100.0, max(0.0, final)), 1)
    return {
        "risk_score": final,
        "risk_level": risk_level(final, settings),
        "breakdown": {
            "rule_score": rule_score,
            "ai_score": ai_score,
            "rule_weight": settings.risk_rule_weight if ai_score is not None else 1.0,
            "ai_weight": settings.risk_ai_weight if ai_score is not None else 0.0,
            "weighted_score": round(weighted, 1),
            "critical_floor_applied": floor_applied,
            "formula": formula,
        },
    }
