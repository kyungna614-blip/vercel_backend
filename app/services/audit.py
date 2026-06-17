"""
Central audit logging service — called by every action that modifies state.
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log(
    db: Session,
    action: str,
    entity_type: str = None,
    entity_id: str = None,
    actor: str = "system",
    details: dict = None,
    ip_address: str = None,
) -> AuditLog:
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        details=details or {},
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    return entry
