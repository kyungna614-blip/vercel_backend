"""
Module 7 — Review Queue.

Human approval gate for:
- Creators (approve/reject for outreach)
- Outreach messages (approve/reject before queuing)
- Follow-ups (approve/reject before sending)
- Contacts (validate before use)

All approvals are logged in the audit trail + reviews table.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.audit import Review
from app.models.creator import Creator
from app.models.outreach import FollowUp, OutreachMessage
from app.services import audit as audit_svc


def _create_review(
    db: Session,
    entity_type: str,
    entity_id: str,
    reviewer: str,
    decision: str,
    notes: str = None,
) -> Review:
    review = Review(
        entity_type=entity_type,
        entity_id=entity_id,
        reviewer=reviewer,
        decision=decision,
        notes=notes,
    )
    db.add(review)
    db.commit()
    audit_svc.log(
        db, action=f"{entity_type}_reviewed", entity_type=entity_type,
        entity_id=entity_id, actor=reviewer,
        details={"decision": decision, "notes": notes},
    )
    return review


# ── Creator Reviews ──────────────────────────────────────────────────────────

def review_creator(
    db: Session,
    creator_id: str,
    decision: str,         # "approved" | "rejected" | "needs_changes"
    reviewer: str,
    notes: str = None,
) -> Creator:
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    status_map = {"approved": "approved", "rejected": "rejected", "needs_changes": "in_review"}
    new_status = status_map.get(decision)
    if not new_status:
        raise ValueError(f"Invalid decision: {decision}")

    creator.status = new_status
    creator.updated_at = datetime.utcnow()
    db.commit()
    _create_review(db, "creator", creator_id, reviewer, decision, notes)
    return creator


def list_creator_review_queue(db: Session, skip: int = 0, limit: int = 50) -> list[Creator]:
    return (
        db.query(Creator)
        .filter(Creator.status.in_(["qualified", "in_review"]))
        .order_by(Creator.follower_count.desc())
        .offset(skip).limit(limit).all()
    )


# ── Outreach Message Reviews ─────────────────────────────────────────────────

def review_outreach_message(
    db: Session,
    message_id: str,
    decision: str,
    reviewer: str,
    notes: str = None,
) -> OutreachMessage:
    msg = db.get(OutreachMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.status != "review_pending":
        raise ValueError(f"Message is not pending review (status: {msg.status})")

    status_map = {"approved": "approved", "rejected": "rejected", "needs_changes": "draft"}
    msg.status = status_map.get(decision, "draft")
    msg.reviewed_by = reviewer
    msg.reviewed_at = datetime.utcnow()
    msg.review_notes = notes
    msg.updated_at = datetime.utcnow()
    db.commit()
    _create_review(db, "outreach_message", message_id, reviewer, decision, notes)
    return msg


def list_message_review_queue(db: Session, skip: int = 0, limit: int = 50) -> list[OutreachMessage]:
    return (
        db.query(OutreachMessage)
        .filter(OutreachMessage.status == "review_pending")
        .order_by(OutreachMessage.created_at.asc())
        .offset(skip).limit(limit).all()
    )


# ── Follow-up Reviews ────────────────────────────────────────────────────────

def review_follow_up(
    db: Session,
    follow_up_id: str,
    decision: str,
    reviewer: str,
    notes: str = None,
) -> FollowUp:
    fu = db.get(FollowUp, follow_up_id)
    if not fu:
        raise ValueError("FollowUp not found")

    status_map = {"approved": "approved", "rejected": "skipped", "needs_changes": "draft"}
    fu.status = status_map.get(decision, "draft")
    fu.reviewed_by = reviewer
    fu.reviewed_at = datetime.utcnow()
    fu.review_notes = notes
    db.commit()
    _create_review(db, "follow_up", follow_up_id, reviewer, decision, notes)
    return fu


def list_followup_review_queue(db: Session, skip: int = 0, limit: int = 50) -> list[FollowUp]:
    return (
        db.query(FollowUp)
        .filter(FollowUp.status == "review_pending")
        .order_by(FollowUp.scheduled_for.asc())
        .offset(skip).limit(limit).all()
    )
