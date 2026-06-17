import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class OutreachMessage(Base):
    __tablename__ = "outreach_logs"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    campaign_id = Column(String, ForeignKey("campaigns.id"), index=True)
    contact_id = Column(String, ForeignKey("contacts.id"), index=True)
    deck_id = Column(String, ForeignKey("decks.id"))
    subject = Column(String)
    body = Column(Text, nullable=False)
    send_method = Column(
        SAEnum("email", "dm", "contact_form", name="send_method_enum"),
        default="email",
    )
    status = Column(
        SAEnum(
            "draft", "review_pending", "approved", "rejected",
            "queued", "sent", "bounced", "failed",
            name="message_status_enum",
        ),
        default="draft",
        index=True,
    )
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    queued_at = Column(DateTime)
    sent_at = Column(DateTime)
    send_error = Column(Text)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("Creator", back_populates="outreach_messages")
    contact = relationship("Contact", back_populates="outreach_messages")
    deck = relationship("Deck", back_populates="outreach_messages")
    thread = relationship("Thread", back_populates="outreach_message", uselist=False)


class Thread(Base):
    __tablename__ = "threads"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    outreach_message_id = Column(String, ForeignKey("outreach_logs.id"))
    status = Column(
        SAEnum("open", "replied", "closed", "converted", "lost", name="thread_status_enum"),
        default="open",
        index=True,
    )
    last_activity = Column(DateTime, default=_now)
    created_at = Column(DateTime, default=_now)

    creator = relationship("Creator", back_populates="threads")
    outreach_message = relationship("OutreachMessage", back_populates="thread")
    replies = relationship("Reply", back_populates="thread", cascade="all, delete-orphan")
    follow_ups = relationship("FollowUp", back_populates="thread", cascade="all, delete-orphan")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id = Column(String, primary_key=True, default=_uuid)
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    draft = Column(Text, nullable=False)
    status = Column(
        SAEnum("draft", "review_pending", "approved", "sent", "skipped", name="followup_status_enum"),
        default="draft",
        index=True,
    )
    scheduled_for = Column(DateTime)
    sent_at = Column(DateTime)
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    created_at = Column(DateTime, default=_now)

    thread = relationship("Thread", back_populates="follow_ups")


class Reply(Base):
    __tablename__ = "replies"

    id = Column(String, primary_key=True, default=_uuid)
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    from_address = Column(String)
    subject = Column(String)
    body = Column(Text)
    received_at = Column(DateTime, default=_now)
    classification = Column(
        SAEnum(
            "interested", "not_interested", "more_info",
            "out_of_office", "bounced", "spam", "other",
            name="reply_classification_enum",
        ),
        default="other",
    )
    sentiment = Column(String)                  # positive / neutral / negative
    ai_summary = Column(Text)
    crm_stage = Column(
        SAEnum(
            "new", "contacted", "qualified", "negotiating",
            "closed_won", "closed_lost",
            name="crm_stage_enum",
        ),
        default="new",
    )
    processed_at = Column(DateTime)

    thread = relationship("Thread", back_populates="replies")


class SuppressionList(Base):
    __tablename__ = "suppression_list"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), index=True)
    email = Column(String, index=True)
    domain = Column(String, index=True)
    reason = Column(
        SAEnum("opt_out", "bounce", "invalid", "do_not_contact", "complaint", name="suppression_reason_enum"),
        nullable=False,
    )
    suppressed_at = Column(DateTime, default=_now)
    suppressed_by = Column(String)
    notes = Column(Text)

    creator = relationship("Creator", back_populates="suppression_entries")
