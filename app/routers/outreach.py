from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.outreach import OutreachMessage, Thread, FollowUp, Reply
from app.services.outreach_generator import (
    generate_outreach_draft, submit_for_review, update_draft
)
from app.services.review_queue import (
    review_outreach_message, list_message_review_queue,
    review_follow_up, list_followup_review_queue,
)
from app.services.send_queue import queue_message, send_message, handle_bounce, list_send_queue
from app.services.followup import generate_followup, send_approved_followup, can_follow_up
from app.services.reply_classifier import record_reply, classify_reply

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


class DraftCreate(BaseModel):
    creator_id: str
    campaign_id: str
    contact_id: str
    product_recommendation_id: str
    deck_id: Optional[str] = None
    send_method: str = "email"
    tone: str = "professional_friendly"


class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


class ReviewDecision(BaseModel):
    decision: str          # approved | rejected | needs_changes
    reviewer: str
    notes: Optional[str] = None


class ReplyRecord(BaseModel):
    thread_id: str
    from_address: str
    subject: Optional[str] = ""
    body: str


# ── Draft Management ─────────────────────────────────────────────────────────

@router.post("/drafts")
def create_draft(body: DraftCreate, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        msg = generate_outreach_draft(db, actor=actor, **body.model_dump())
        return _msg_dict(msg)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/drafts/{message_id}")
def edit_draft(message_id: str, body: DraftUpdate, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        msg = update_draft(db, message_id, body.subject, body.body, actor)
        return _msg_dict(msg)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/drafts/{message_id}/submit")
def submit_draft(message_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        msg = submit_for_review(db, message_id, actor)
        return _msg_dict(msg)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Review Queue ─────────────────────────────────────────────────────────────

@router.get("/review-queue")
def message_review_queue(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    msgs = list_message_review_queue(db, skip, limit)
    return [_msg_dict(m) for m in msgs]


@router.post("/review-queue/{message_id}/review")
def review_message(message_id: str, body: ReviewDecision, db: Session = Depends(get_db)):
    try:
        msg = review_outreach_message(db, message_id, body.decision, body.reviewer, body.notes)
        return _msg_dict(msg)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Send Queue ───────────────────────────────────────────────────────────────

@router.get("/send-queue")
def send_queue(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    msgs = list_send_queue(db, skip, limit)
    return [_msg_dict(m) for m in msgs]


@router.post("/{message_id}/queue")
def queue_for_send(message_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        msg = queue_message(db, message_id, actor)
        return _msg_dict(msg)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{message_id}/send")
def send(message_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        msg = send_message(db, message_id, actor)
        return _msg_dict(msg)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{message_id}/bounce")
def mark_bounce(message_id: str, actor: str = "system", db: Session = Depends(get_db)):
    try:
        msg = handle_bounce(db, message_id, actor)
        return _msg_dict(msg)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Follow-ups ───────────────────────────────────────────────────────────────

@router.get("/threads/{thread_id}/followup-eligibility")
def check_followup(thread_id: str, db: Session = Depends(get_db)):
    can, reason = can_follow_up(db, thread_id)
    return {"can_follow_up": can, "reason": reason}


@router.post("/threads/{thread_id}/followup")
def create_followup(thread_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        fu = generate_followup(db, thread_id, actor)
        return _followup_dict(fu)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/followup-review-queue")
def followup_review_queue(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    fus = list_followup_review_queue(db, skip, limit)
    return [_followup_dict(f) for f in fus]


@router.post("/followups/{follow_up_id}/review")
def review_fu(follow_up_id: str, body: ReviewDecision, db: Session = Depends(get_db)):
    try:
        fu = review_follow_up(db, follow_up_id, body.decision, body.reviewer, body.notes)
        return _followup_dict(fu)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/followups/{follow_up_id}/send")
def send_followup(follow_up_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        fu = send_approved_followup(db, follow_up_id, actor)
        return _followup_dict(fu)
    except (ValueError, Exception) as e:
        raise HTTPException(400, str(e))


# ── Reply Inbox ──────────────────────────────────────────────────────────────

@router.post("/replies")
def record_incoming_reply(body: ReplyRecord, actor: str = "system", db: Session = Depends(get_db)):
    try:
        reply = record_reply(db, body.thread_id, body.from_address, body.subject, body.body, actor=actor)
        return _reply_dict(reply)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/replies")
def list_replies(classification: Optional[str] = None, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(Reply)
    if classification:
        q = q.filter(Reply.classification == classification)
    replies = q.order_by(Reply.received_at.desc()).offset(skip).limit(limit).all()
    return [_reply_dict(r) for r in replies]


@router.post("/replies/{reply_id}/classify")
def reclassify(reply_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        reply = classify_reply(db, reply_id, actor)
        return _reply_dict(reply)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── General message list ─────────────────────────────────────────────────────

@router.get("/messages")
def list_messages(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(OutreachMessage)
    if status:
        q = q.filter(OutreachMessage.status == status)
    msgs = q.order_by(OutreachMessage.created_at.desc()).offset(skip).limit(limit).all()
    return [_msg_dict(m) for m in msgs]


# ── Threads ──────────────────────────────────────────────────────────────────

@router.get("/threads")
def list_threads(status: Optional[str] = None, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(Thread)
    if status:
        q = q.filter(Thread.status == status)
    threads = q.order_by(Thread.last_activity.desc()).offset(skip).limit(limit).all()
    return [_thread_dict(t) for t in threads]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _msg_dict(m: OutreachMessage) -> dict:
    return {
        "id": m.id, "creator_id": m.creator_id, "campaign_id": m.campaign_id,
        "contact_id": m.contact_id, "deck_id": m.deck_id,
        "subject": m.subject, "body": m.body, "send_method": m.send_method,
        "status": m.status, "reviewed_by": m.reviewed_by,
        "review_notes": m.review_notes,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _followup_dict(f: FollowUp) -> dict:
    return {
        "id": f.id, "thread_id": f.thread_id, "draft": f.draft,
        "status": f.status,
        "scheduled_for": f.scheduled_for.isoformat() if f.scheduled_for else None,
        "sent_at": f.sent_at.isoformat() if f.sent_at else None,
        "reviewed_by": f.reviewed_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _reply_dict(r: Reply) -> dict:
    return {
        "id": r.id, "thread_id": r.thread_id, "from_address": r.from_address,
        "subject": r.subject, "body": r.body,
        "classification": r.classification, "sentiment": r.sentiment,
        "ai_summary": r.ai_summary, "crm_stage": r.crm_stage,
        "received_at": r.received_at.isoformat() if r.received_at else None,
    }


def _thread_dict(t: Thread) -> dict:
    return {
        "id": t.id, "creator_id": t.creator_id,
        "outreach_message_id": t.outreach_message_id,
        "status": t.status,
        "last_activity": t.last_activity.isoformat() if t.last_activity else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
