"""Audit trail helper: records who did what. Never pass passwords, tokens or other secrets as details."""

from sqlalchemy.orm import Session

from backend.models import AuditLog


def record_audit(db: Session, actor: str, action: str, entity_type: str | None = None,
                 entity_id: str | int | None = None, details: dict | None = None) -> None:
    """Adds an audit row to the session; the caller commits it together with the change itself."""
    db.add(AuditLog(actor=actor, action=action, entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None, details=details or {}))
