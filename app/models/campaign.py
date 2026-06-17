import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Enum as SAEnum

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text)
    product_category = Column(String)
    status = Column(
        SAEnum("draft", "active", "paused", "completed", name="campaign_status_enum"),
        default="draft",
        index=True,
    )
    daily_send_limit = Column(Integer, default=10)      # hard cap — safety control
    total_sent = Column(Integer, default=0)
    total_replied = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)
    require_human_approval = Column(Boolean, default=True)  # always on by default
    created_by = Column(String)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
