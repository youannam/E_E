"""View and configure the cybersecurity rules."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ai.features import SENSITIVITY_LEVELS
from backend.audit import record_audit
from backend.database import get_db
from backend.detection.pipeline import load_rule_settings
from backend.detection.rules import RULES, RULES_BY_ID
from backend.models import Account, RuleSetting
from backend.schemas import RuleOut, RuleUpdate
from backend.security import require_admin

router = APIRouter(prefix="/rules", tags=["Cybersecurity rules"])


def rule_out(rule_id: str, settings: dict) -> RuleOut:
    rule = RULES_BY_ID[rule_id]
    values = settings[rule_id]
    return RuleOut(rule_id=rule.rule_id, name=rule.name, description=rule.description, severity=rule.severity,
                   required_fields=rule.required_fields, time_window=rule.time_window, enabled=values["enabled"],
                   weight=values["weight"], parameters=values["parameters"])


@router.get("", response_model=list[RuleOut], summary="All rules with their current settings")
def list_rules(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    settings = load_rule_settings(db)
    return [rule_out(rule.rule_id, settings) for rule in RULES]


def validate_parameters(current: dict, new: dict) -> None:
    """Only existing parameters may be changed, numbers must stay non-negative numbers."""
    for key, value in new.items():
        if key not in current:
            raise HTTPException(status_code=422, detail=f"Unknown parameter '{key}'")
        old = current[key]
        if isinstance(old, (int, float)) and not isinstance(old, bool):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise HTTPException(status_code=422, detail=f"Parameter '{key}' must be a non-negative number")
        elif key == "default_clearance" and value not in SENSITIVITY_LEVELS:
            raise HTTPException(status_code=422, detail=f"default_clearance must be one of {SENSITIVITY_LEVELS}")
        elif key == "role_clearance":
            if not isinstance(value, dict) or any(level not in SENSITIVITY_LEVELS for level in value.values()):
                raise HTTPException(status_code=422, detail="role_clearance must map job roles to sensitivity levels")


@router.patch("/{rule_id}", response_model=RuleOut, summary="Enable/disable a rule or change its weight and thresholds (admin)")
def update_rule(rule_id: str, body: RuleUpdate, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    if rule_id not in RULES_BY_ID:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    current = load_rule_settings(db)[rule_id]
    if body.parameters:
        validate_parameters(current["parameters"], body.parameters)

    row = db.get(RuleSetting, rule_id)
    if row is None:
        row = RuleSetting(rule_id=rule_id, enabled=current["enabled"], weight=current["weight"],
                          parameters=current["parameters"])
        db.add(row)
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.weight is not None:
        row.weight = body.weight
    if body.parameters:
        row.parameters = {**current["parameters"], **body.parameters}

    record_audit(db, admin.username, "RULE_UPDATED", "rule", rule_id, body.model_dump(exclude_none=True))
    db.commit()
    return rule_out(rule_id, load_rule_settings(db))
