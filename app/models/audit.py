import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text, Enum as SAEnum, JSON

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class Review(Base):
    __tablename__ = "reviews"

    id = Column(String, primary_key=True, default=_uuid)
    entity_type = Column(String, nullable=False, index=True)   # creator, outreach_message, follow_up, etc.
    entity_id = Column(String, nullable=False, index=True)
    reviewer = Column(String, nullable=False)
    decision = Column(
        SAEnum("approved", "rejected", "needs_changes", name="review_decision_enum"),
        nullable=False,
    )
    notes = Column(Text)
    reviewed_at = Column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=_uuid)
    entity_type = Column(String, index=True)
    entity_id = Column(String, index=True)
    action = Column(String, nullable=False)     # e.g. "message_sent", "creator_approved", "opt_out_recorded"
    actor = Column(String)                      # user/system that performed the action
    details = Column(JSON)                      # arbitrary detail payload
    ip_address = Column(String)
    created_at = Column(DateTime, default=_now, index=True)
