"""
Module 10 — Reply Classification + CRM Pipeline.

Classifies incoming replies and updates CRM stage.
Handles opt-outs immediately (STOP keyword → suppression).
"""
import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.outreach import Reply, Thread
from app.services import audit as audit_svc
from app.services.suppression import add_suppression


OPT_OUT_KEYWORDS = {"stop", "unsubscribe", "remove", "opt out", "opt-out", "no thanks", "not interested please remove"}


def _detect_opt_out(body: str) -> bool:
    lower = body.lower().strip()
    return any(kw in lower for kw in OPT_OUT_KEYWORDS)


def _build_classify_prompt(subject: str, body: str) -> str:
    return f"""Classify this email reply from a creator to a partnership outreach.

Subject: {subject}
Body: {body[:1000]}

Return JSON:
{{
  "classification": "<interested|not_interested|more_info|out_of_office|bounced|spam|other>",
  "sentiment": "<positive|neutral|negative>",
  "crm_stage": "<new|contacted|qualified|negotiating|closed_won|closed_lost>",
  "summary": "<1-2 sentence summary of what they said>",
  "next_action": "<recommended next step>"
}}

Classification guide:
- interested: enthusiastic, wants to move forward, asks questions about the deal
- more_info: asks for more details, deck, or clarification before deciding
- not_interested: clear no or decline
- out_of_office: auto-reply or vacation response
- bounced: delivery failure notification
- spam: clearly unrelated or malicious

Return ONLY valid JSON."""


def record_reply(
    db: Session,
    thread_id: str,
    from_address: str,
    subject: str,
    body: str,
    received_at: datetime = None,
    actor: str = "system",
) -> Reply:
    thread = db.get(Thread, thread_id)
    if not thread:
        raise ValueError("Thread not found")

    # Immediate opt-out handling — no delay, no AI needed
    if _detect_opt_out(body):
        _handle_opt_out(db, thread, from_address, body, actor)

    reply = Reply(
        thread_id=thread_id,
        from_address=from_address,
        subject=subject,
        body=body,
        received_at=received_at or datetime.utcnow(),
    )
    db.add(reply)

    # Update thread status
    thread.status = "replied"
    thread.last_activity = datetime.utcnow()

    db.commit()
    db.refresh(reply)

    # Run AI classification
    try:
        classify_reply(db, reply.id, actor=actor)
    except Exception:
        pass  # Classification failure shouldn't block reply recording

    audit_svc.log(
        db, action="reply_recorded", entity_type="reply",
        entity_id=reply.id, actor=actor,
        details={"thread_id": thread_id, "from": from_address},
    )
    return reply


def classify_reply(
    db: Session,
    reply_id: str,
    actor: str = "system",
) -> Reply:
    reply = db.get(Reply, reply_id)
    if not reply:
        raise ValueError("Reply not found")

    if not settings.ANTHROPIC_API_KEY:
        # Rule-based fallback
        lower = reply.body.lower()
        if any(w in lower for w in ["yes", "interested", "love to", "sounds great", "let's talk"]):
            reply.classification = "interested"
            reply.sentiment = "positive"
            reply.crm_stage = "qualified"
            reply.ai_summary = "Creator expressed interest."
        elif any(w in lower for w in ["no thanks", "not interested", "pass", "decline"]):
            reply.classification = "not_interested"
            reply.sentiment = "negative"
            reply.crm_stage = "closed_lost"
            reply.ai_summary = "Creator declined."
        elif any(w in lower for w in ["can you tell me more", "more info", "details", "deck"]):
            reply.classification = "more_info"
            reply.sentiment = "positive"
            reply.crm_stage = "contacted"
            reply.ai_summary = "Creator asking for more information."
        else:
            reply.classification = "other"
            reply.sentiment = "neutral"
            reply.crm_stage = "contacted"
            reply.ai_summary = "Reply received — manual review needed."
        reply.processed_at = datetime.utcnow()
        db.commit()
        return reply

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_classify_prompt(reply.subject or "", reply.body)
    message = client.messages.create(
        model=settings.AI_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    reply.classification = data.get("classification", "other")
    reply.sentiment = data.get("sentiment", "neutral")
    reply.crm_stage = data.get("crm_stage", "contacted")
    reply.ai_summary = data.get("summary", "")
    reply.processed_at = datetime.utcnow()

    # Update thread CRM stage
    thread = db.get(Thread, reply.thread_id)
    if thread:
        if reply.classification == "interested":
            thread.status = "replied"
        elif reply.classification == "not_interested":
            thread.status = "closed"

    db.commit()
    return reply


def _handle_opt_out(db: Session, thread: Thread, from_address: str, body: str, actor: str):
    """Immediately suppresses contact on opt-out reply."""
    add_suppression(
        db, reason="opt_out",
        email=from_address,
        creator_id=thread.creator_id,
        suppressed_by="auto_opt_out",
        notes=f"Opt-out detected in reply body: {body[:100]}",
        actor=actor,
    )
    thread.status = "closed"
    db.commit()
    audit_svc.log(
        db, action="opt_out_processed", entity_type="thread",
        entity_id=thread.id, actor=actor,
        details={"from": from_address},
    )


def get_crm_pipeline(db: Session) -> dict:
    """Returns counts by CRM stage for pipeline view."""
    from sqlalchemy import func
    rows = (
        db.query(Reply.crm_stage, func.count(Reply.id))
        .group_by(Reply.crm_stage)
        .all()
    )
    return {stage: count for stage, count in rows}
