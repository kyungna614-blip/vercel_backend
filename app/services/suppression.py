"""
Suppression list service.
All outreach paths MUST call is_suppressed() before sending.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.outreach import SuppressionList
from app.services import audit as audit_svc


def is_suppressed(db: Session, *, creator_id: str = None, email: str = None) -> bool:
    """Returns True if the creator or email is suppressed."""
    q = db.query(SuppressionList)
    if creator_id:
        if q.filter(SuppressionList.creator_id == creator_id).first():
            return True
    if email:
        domain = email.split("@")[-1] if "@" in email else None
        if q.filter(
            (SuppressionList.email == email) |
            (SuppressionList.domain == domain)
        ).first():
            return True
    return False


def add_suppression(
    db: Session,
    reason: str,
    creator_id: str = None,
    email: str = None,
    domain: str = None,
    suppressed_by: str = "system",
    notes: str = None,
    actor: str = "system",
) -> SuppressionList:
    entry = SuppressionList(
        creator_id=creator_id,
        email=email,
        domain=domain,
        reason=reason,
        suppressed_at=datetime.utcnow(),
        suppressed_by=suppressed_by,
        notes=notes,
    )
    db.add(entry)

    # Mark creator suppressed if creator_id given
    if creator_id:
        from app.models.creator import Creator
        creator = db.get(Creator, creator_id)
        if creator:
            creator.status = "suppressed"

    db.commit()
    audit_svc.log(
        db, action="suppression_added", entity_type="suppression_list",
        entity_id=entry.id, actor=actor,
        details={"reason": reason, "email": email, "creator_id": creator_id},
    )
    return entry


def list_suppressions(db: Session, skip: int = 0, limit: int = 100):
    return db.query(SuppressionList).order_by(SuppressionList.suppressed_at.desc()).offset(skip).limit(limit).all()
