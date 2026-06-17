from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.analytics import (
    get_dashboard_summary, get_funnel_metrics, get_campaign_stats,
    get_engagement_distribution, get_reply_classification_breakdown,
    get_top_performing_messages,
)
from app.services.reply_classifier import get_crm_pipeline

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return get_dashboard_summary(db)


@router.get("/funnel")
def funnel(db: Session = Depends(get_db)):
    return get_funnel_metrics(db)


@router.get("/campaigns")
def campaign_stats(campaign_id: str = None, db: Session = Depends(get_db)):
    return get_campaign_stats(db, campaign_id)


@router.get("/engagement")
def engagement_dist(db: Session = Depends(get_db)):
    return get_engagement_distribution(db)


@router.get("/replies")
def reply_breakdown(db: Session = Depends(get_db)):
    return get_reply_classification_breakdown(db)


@router.get("/crm-pipeline")
def crm(db: Session = Depends(get_db)):
    return get_crm_pipeline(db)


@router.get("/top-messages")
def top_messages(limit: int = 10, db: Session = Depends(get_db)):
    return get_top_performing_messages(db, limit)
