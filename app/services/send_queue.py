"""
Module 8 — Sending Queue.

Safety controls:
1. Message MUST be status="approved" before it can be queued
2. Suppression check runs immediately before send
3. Daily send limit enforced per campaign
4. Every send attempt logged in audit trail
5. Bounced emails auto-added to suppression list
6. AUTO_SEND_ENABLED=False — "send" button always requires human click
"""
from datetime import datetime, date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.campaign import Campaign
from app.models.creator import Contact
from app.models.outreach import OutreachMessage, Thread, SuppressionList
from app.services import audit as audit_svc
from app.services.suppression import is_suppressed, add_suppression


def queue_message(
    db: Session,
    message_id: str,
    actor: str = "system",
) -> OutreachMessage:
    """
    Moves an approved message into the send queue.
    Validates: approved status, not suppressed, campaign limit.
    """
    msg = db.get(OutreachMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.status != "approved":
        raise ValueError(f"Message must be approved before queuing (current: {msg.status})")

    # Suppression check
    contact = db.get(Contact, msg.contact_id) if msg.contact_id else None
    email = contact.value if contact and "@" in contact.value else None
    if is_suppressed(db, creator_id=msg.creator_id, email=email):
        msg.status = "failed"
        msg.send_error = "Creator or contact is suppressed"
        db.commit()
        raise ValueError("Creator/contact is suppressed — message cancelled")

    # Daily send limit check
    if msg.campaign_id:
        campaign = db.get(Campaign, msg.campaign_id)
        if campaign:
            today_sent = (
                db.query(func.count(OutreachMessage.id))
                .filter(
                    OutreachMessage.campaign_id == msg.campaign_id,
                    OutreachMessage.status == "sent",
                    func.date(OutreachMessage.sent_at) == date.today(),
                )
                .scalar()
            )
            if today_sent >= campaign.daily_send_limit:
                raise ValueError(
                    f"Daily send limit ({campaign.daily_send_limit}) reached for campaign '{campaign.name}'"
                )

    msg.status = "queued"
    msg.queued_at = datetime.utcnow()
    msg.updated_at = datetime.utcnow()
    db.commit()

    audit_svc.log(
        db, action="message_queued", entity_type="outreach_message",
        entity_id=message_id, actor=actor,
        details={"campaign_id": msg.campaign_id},
    )
    return msg


def send_message(
    db: Session,
    message_id: str,
    actor: str = "system",
) -> OutreachMessage:
    """
    Sends a queued message via the configured email provider.
    This is the only place where actual sending happens.
    """
    msg = db.get(OutreachMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.status != "queued":
        raise ValueError(f"Message must be queued to send (current: {msg.status})")

    # Final suppression check
    contact = db.get(Contact, msg.contact_id) if msg.contact_id else None
    email = contact.value if contact and "@" in contact.value else None
    if is_suppressed(db, creator_id=msg.creator_id, email=email):
        msg.status = "failed"
        msg.send_error = "Suppressed at send time"
        db.commit()
        raise ValueError("Suppressed at send time")

    try:
        if msg.send_method == "email" and email:
            from app.integrations.email_provider import email_provider
            result = email_provider.send(
                to_email=email,
                subject=msg.subject,
                body_html=msg.body.replace("\n", "<br>"),
                body_text=msg.body,
            )
        else:
            # DM / contact form — manual send path
            # Log that it needs manual action
            result = {"message_id": "manual", "status": "manual_send_required"}

        msg.status = "sent"
        msg.sent_at = datetime.utcnow()
        msg.updated_at = datetime.utcnow()
        db.commit()

        # Update campaign total
        if msg.campaign_id:
            campaign = db.get(Campaign, msg.campaign_id)
            if campaign:
                campaign.total_sent = (campaign.total_sent or 0) + 1
                db.commit()

        # Create thread if doesn't exist
        if not msg.thread:
            thread = Thread(
                creator_id=msg.creator_id,
                outreach_message_id=msg.id,
                status="open",
            )
            db.add(thread)
            db.commit()

        audit_svc.log(
            db, action="message_sent", entity_type="outreach_message",
            entity_id=message_id, actor=actor,
            details={"to": email, "method": msg.send_method, "send_result": result},
        )

    except Exception as e:
        msg.status = "failed"
        msg.send_error = str(e)
        msg.updated_at = datetime.utcnow()
        db.commit()
        audit_svc.log(
            db, action="message_send_failed", entity_type="outreach_message",
            entity_id=message_id, actor=actor,
            details={"error": str(e)},
        )
        raise

    return msg


def handle_bounce(db: Session, message_id: str, actor: str = "system") -> OutreachMessage:
    """Records a bounce and adds contact to suppression list."""
    msg = db.get(OutreachMessage, message_id)
    if not msg:
        raise ValueError("Message not found")

    msg.status = "bounced"
    db.commit()

    contact = db.get(Contact, msg.contact_id) if msg.contact_id else None
    if contact and "@" in contact.value:
        add_suppression(
            db, reason="bounce", email=contact.value,
            creator_id=msg.creator_id,
            suppressed_by=actor, actor=actor,
            notes=f"Bounced from message {message_id}",
        )

    audit_svc.log(
        db, action="message_bounced", entity_type="outreach_message",
        entity_id=message_id, actor=actor,
    )
    return msg


def list_send_queue(db: Session, skip: int = 0, limit: int = 50) -> list[OutreachMessage]:
    return (
        db.query(OutreachMessage)
        .filter(OutreachMessage.status == "queued")
        .order_by(OutreachMessage.queued_at.asc())
        .offset(skip).limit(limit).all()
    )
