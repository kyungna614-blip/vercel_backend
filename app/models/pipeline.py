"""
Pipeline run tracking — every pipeline execution, step, email send, and scrape
is recorded here for full A-to-Z audit trail in Supabase.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean
from app.database import Base


def _uuid():
    return str(uuid.uuid4())

def _now():
    return datetime.utcnow()


class PipelineRun(Base):
    """One row per pipeline execution (admin clicks 'Run Discovery')."""
    __tablename__ = "pipeline_runs"

    id              = Column(String, primary_key=True, default=_uuid)
    keyword         = Column(String, nullable=False, index=True)
    max_results     = Column(Integer, default=10)
    status          = Column(String, default="running", index=True)  # running | completed | failed
    creators_found  = Column(Integer, default=0)
    emails_found    = Column(Integer, default=0)
    ideas_generated = Column(Integer, default=0)
    emails_sent     = Column(Integer, default=0)
    errors          = Column(JSON, default=list)
    duration_ms     = Column(Integer, default=0)
    started_at      = Column(DateTime, default=_now)
    completed_at    = Column(DateTime, nullable=True)


class PipelineStep(Base):
    """One row per step within a pipeline run (search, scrape, ideas, outreach)."""
    __tablename__ = "pipeline_steps"

    id          = Column(String, primary_key=True, default=_uuid)
    run_id      = Column(String, nullable=False, index=True)
    step_name   = Column(String, nullable=False)  # youtube_search | apify_email | ai_ideas | outreach_send
    status      = Column(String, default="running")  # running | completed | failed | skipped
    detail      = Column(JSON, default=dict)
    started_at  = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)


class EmailTracker(Base):
    """One row per outreach email — tracks delivery, opens, clicks."""
    __tablename__ = "email_tracker"

    id              = Column(String, primary_key=True, default=_uuid)
    run_id          = Column(String, nullable=True, index=True)
    creator_id      = Column(String, nullable=False, index=True)
    creator_name    = Column(String)
    to_email        = Column(String, nullable=False)
    subject         = Column(String)
    status          = Column(String, default="queued")  # queued | sent | delivered | opened | clicked | bounced | failed
    resend_id       = Column(String, nullable=True)
    error_message   = Column(Text, nullable=True)
    sent_at         = Column(DateTime, nullable=True)
    opened_at       = Column(DateTime, nullable=True)
    clicked_at      = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=_now)


class ScrapeLog(Base):
    """One row per scrape operation (YouTube API call or Apify run)."""
    __tablename__ = "scrape_logs"

    id          = Column(String, primary_key=True, default=_uuid)
    run_id      = Column(String, nullable=True, index=True)
    source      = Column(String, nullable=False)  # youtube_api | apify_email | apify_profile
    keyword     = Column(String)
    results_count = Column(Integer, default=0)
    raw_response  = Column(JSON, nullable=True)
    status      = Column(String, default="completed")  # completed | failed
    error       = Column(Text, nullable=True)
    duration_ms = Column(Integer, default=0)
    created_at  = Column(DateTime, default=_now)
