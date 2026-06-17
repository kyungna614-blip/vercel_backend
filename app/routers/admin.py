"""
Admin dashboard API — aggregated stats, pipeline run history, email tracking.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models.creator import Creator, Contact, ProductRecommendation
from app.models.outreach import OutreachMessage
from app.models.pipeline import PipelineRun, PipelineStep, EmailTracker, ScrapeLog

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    """Aggregated stats for the admin dashboard."""
    total_creators = db.query(func.count(Creator.id)).scalar() or 0
    total_with_email = db.query(func.count(Creator.id)).filter(Creator.email_public.isnot(None), Creator.email_public != "").scalar() or 0
    total_ideas = db.query(func.count(ProductRecommendation.id)).scalar() or 0
    total_pipeline_runs = db.query(func.count(PipelineRun.id)).scalar() or 0
    total_emails_sent = db.query(func.count(EmailTracker.id)).filter(EmailTracker.status == "sent").scalar() or 0
    total_emails_failed = db.query(func.count(EmailTracker.id)).filter(EmailTracker.status == "failed").scalar() or 0
    total_scrapes = db.query(func.count(ScrapeLog.id)).scalar() or 0
    total_outreach = db.query(func.count(OutreachMessage.id)).scalar() or 0

    return {
        "total_creators": total_creators,
        "total_with_email": total_with_email,
        "total_ideas": total_ideas,
        "total_pipeline_runs": total_pipeline_runs,
        "total_emails_sent": total_emails_sent,
        "total_emails_failed": total_emails_failed,
        "total_scrapes": total_scrapes,
        "total_outreach": total_outreach,
    }


@router.get("/pipeline-runs")
def get_pipeline_runs(limit: int = 20, db: Session = Depends(get_db)):
    """List recent pipeline runs with step details."""
    runs = db.query(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(limit).all()
    result = []
    for run in runs:
        steps = db.query(PipelineStep).filter(PipelineStep.run_id == run.id).order_by(PipelineStep.started_at).all()
        result.append({
            "id": run.id,
            "keyword": run.keyword,
            "max_results": run.max_results,
            "status": run.status,
            "creators_found": run.creators_found,
            "emails_found": run.emails_found,
            "ideas_generated": run.ideas_generated,
            "emails_sent": run.emails_sent,
            "duration_ms": run.duration_ms,
            "errors": run.errors,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "steps": [
                {
                    "step_name": s.step_name,
                    "status": s.status,
                    "detail": s.detail,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in steps
            ],
        })
    return result


@router.get("/email-tracker")
def get_email_tracker(limit: int = 50, db: Session = Depends(get_db)):
    """List all tracked emails with delivery status."""
    emails = db.query(EmailTracker).order_by(desc(EmailTracker.created_at)).limit(limit).all()
    return [
        {
            "id": e.id,
            "run_id": e.run_id,
            "creator_id": e.creator_id,
            "creator_name": e.creator_name,
            "to_email": e.to_email,
            "subject": e.subject,
            "status": e.status,
            "resend_id": e.resend_id,
            "error_message": e.error_message,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            "opened_at": e.opened_at.isoformat() if e.opened_at else None,
            "clicked_at": e.clicked_at.isoformat() if e.clicked_at else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in emails
    ]


@router.get("/scrape-logs")
def get_scrape_logs(limit: int = 50, db: Session = Depends(get_db)):
    """List all scrape operations."""
    logs = db.query(ScrapeLog).order_by(desc(ScrapeLog.created_at)).limit(limit).all()
    return [
        {
            "id": l.id,
            "run_id": l.run_id,
            "source": l.source,
            "keyword": l.keyword,
            "results_count": l.results_count,
            "status": l.status,
            "error": l.error,
            "duration_ms": l.duration_ms,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/creators")
def get_all_creators(limit: int = 100, db: Session = Depends(get_db)):
    """List all creators with their status and email."""
    creators = db.query(Creator).order_by(desc(Creator.created_at)).limit(limit).all()
    return [
        {
            "id": c.id,
            "handle": c.handle,
            "display_name": c.display_name,
            "platform": c.platform,
            "follower_count": c.follower_count,
            "email": c.email_public,
            "niche": c.niche,
            "status": c.status,
            "discovery_source": c.discovery_source,
            "outreach_status": c.discovery_notes or "pending",
            "avatar_url": c.avatar_url,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in creators
    ]
