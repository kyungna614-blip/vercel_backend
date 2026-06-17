from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import AuditLog, Review

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def list_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if action:
        q = q.filter(AuditLog.action == action)
    logs = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": l.id, "entity_type": l.entity_type, "entity_id": l.entity_id,
            "action": l.action, "actor": l.actor, "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/reviews")
def list_reviews(
    entity_type: Optional[str] = None,
    decision: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Review)
    if entity_type:
        q = q.filter(Review.entity_type == entity_type)
    if decision:
        q = q.filter(Review.decision == decision)
    reviews = q.order_by(Review.reviewed_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id,
            "reviewer": r.reviewer, "decision": r.decision, "notes": r.notes,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        }
        for r in reviews
    ]
