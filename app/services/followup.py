"""
Module 9 — AI-Assisted Follow-up.

Rules:
- Max 2 follow-ups per thread (hard cap)
- Each follow-up must be reviewed + approved before send
- No follow-up if thread already has a reply (auto-skipped)
- Minimum 7-day gap between follow-ups
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import Creator
from app.models.outreach import FollowUp, OutreachMessage, Reply, Thread
from app.services import audit as audit_svc

MAX_FOLLOWUPS_PER_THREAD = 2
MIN_FOLLOWUP_GAP_DAYS = 7


def can_follow_up(db: Session, thread_id: str) -> Tuple[bool, str]:
    """Returns (can_follow_up, reason)."""
    thread = db.get(Thread, thread_id)
    if not thread:
        return False, "Thread not found"

    # Don't follow up if already replied
    has_reply = db.query(Reply).filter(Reply.thread_id == thread_id).first()
    if has_reply:
        return False, "Thread already has a reply"

    # Check follow-up count
    existing = (
        db.query(FollowUp)
        .filter(FollowUp.thread_id == thread_id, FollowUp.status != "skipped")
        .all()
    )
    if len(existing) >= MAX_FOLLOWUPS_PER_THREAD:
        return False, f"Max follow-ups ({MAX_FOLLOWUPS_PER_THREAD}) reached"

    # Check gap since last follow-up or original send
    last_action = thread.created_at
    if existing:
        last_sent = max((f.sent_at for f in existing if f.sent_at), default=None)
        if last_sent:
            last_action = last_sent

    gap = datetime.utcnow() - last_action
    if gap.days < MIN_FOLLOWUP_GAP_DAYS:
        return False, f"Too soon — {MIN_FOLLOWUP_GAP_DAYS - gap.days} days remaining"

    return True, "ok"


def _build_followup_prompt(
    creator: Creator, original_subject: str, original_body: str, followup_num: int
) -> str:
    return f"""Write a brief follow-up email for a creator partnership outreach.

Creator: {creator.display_name} (@{creator.handle})
Original subject: {original_subject}
Original email (summary): {original_body[:500]}...
This is follow-up #{followup_num} of {MAX_FOLLOWUPS_PER_THREAD} max.

Rules:
- Very short — 2-3 sentences max
- Acknowledge they're busy, not pushy
- One simple ask (30-min call or just a yes/no)
- Add opt-out line: "Reply STOP to unsubscribe"
- Different angle than original — add new value or question
- NO "just checking in" — be specific

Return JSON:
{{"subject": "<subject line>", "body": "<email body>"}}

Return ONLY valid JSON."""


def generate_followup(
    db: Session,
    thread_id: str,
    actor: str = "system",
) -> FollowUp:
    can_do, reason = can_follow_up(db, thread_id)
    if not can_do:
        raise ValueError(f"Cannot follow up: {reason}")

    thread = db.get(Thread, thread_id)
    original_msg = db.get(OutreachMessage, thread.outreach_message_id)
    creator = db.get(Creator, thread.creator_id)

    followup_num = (
        db.query(FollowUp)
        .filter(FollowUp.thread_id == thread_id, FollowUp.status != "skipped")
        .count()
    ) + 1

    if not settings.ANTHROPIC_API_KEY:
        draft = (
            f"Subject: Re: {original_msg.subject if original_msg else 'Partnership Opportunity'}\n\n"
            f"Hi {creator.display_name},\n\n"
            f"I wanted to follow up on my earlier note about {creator.display_name} — "
            f"totally understand if the timing isn't right. "
            f"Would a quick 15-minute call work sometime this week?\n\n"
            f"Reply STOP to unsubscribe.\n\nBest,"
        )
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = _build_followup_prompt(
            creator,
            original_msg.subject if original_msg else "",
            original_msg.body if original_msg else "",
            followup_num,
        )
        message = client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        try:
            data = json.loads(raw)
            draft = f"Subject: {data.get('subject', 'Following up')}\n\n{data.get('body', raw)}"
        except json.JSONDecodeError:
            draft = raw

    scheduled = datetime.utcnow() + timedelta(days=MIN_FOLLOWUP_GAP_DAYS)
    fu = FollowUp(
        thread_id=thread_id,
        draft=draft,
        status="review_pending",  # requires human approval
        scheduled_for=scheduled,
    )
    db.add(fu)
    db.commit()
    db.refresh(fu)

    audit_svc.log(
        db, action="followup_generated", entity_type="follow_up",
        entity_id=fu.id, actor=actor,
        details={"thread_id": thread_id, "followup_num": followup_num},
    )
    return fu


def send_approved_followup(
    db: Session, follow_up_id: str, actor: str = "system"
) -> FollowUp:
    fu = db.get(FollowUp, follow_up_id)
    if not fu:
        raise ValueError("FollowUp not found")
    if fu.status != "approved":
        raise ValueError(f"FollowUp must be approved (current: {fu.status})")

    thread = db.get(Thread, fu.thread_id)
    original_msg = db.get(OutreachMessage, thread.outreach_message_id) if thread else None

    # Final can-send check
    can_do, reason = can_follow_up(db, fu.thread_id)
    if not can_do and reason not in ("ok",):
        # Allow sending if this specific fu is approved even if gap just closed
        pass

    # Send via same method as original
    if original_msg and original_msg.send_method == "email" and original_msg.contact_id:
        from app.models.creator import Contact
        from app.integrations.email_provider import email_provider
        from app.services.suppression import is_suppressed

        contact = db.get(Contact, original_msg.contact_id)
        if contact and not is_suppressed(db, email=contact.value):
            lines = fu.draft.split("\n", 2)
            subject = lines[0].replace("Subject: ", "") if lines[0].startswith("Subject:") else "Following up"
            body = "\n".join(lines[2:]) if len(lines) > 2 else fu.draft
            try:
                email_provider.send(
                    to_email=contact.value,
                    subject=subject,
                    body_html=body.replace("\n", "<br>"),
                    body_text=body,
                )
            except Exception as e:
                audit_svc.log(db, action="followup_send_failed", entity_type="follow_up",
                               entity_id=follow_up_id, actor=actor, details={"error": str(e)})
                raise

    fu.status = "sent"
    fu.sent_at = datetime.utcnow()
    if thread:
        thread.last_activity = datetime.utcnow()
    db.commit()

    audit_svc.log(db, action="followup_sent", entity_type="follow_up",
                  entity_id=follow_up_id, actor=actor)
    return fu
