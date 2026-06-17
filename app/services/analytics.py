"""
Module 11 — Analytics & Learning Loop.

Provides:
- Funnel metrics (discovery → sent → replied → converted)
- Campaign performance
- Engagement score distributions
- Reply classification breakdown
- Top performing outreach patterns (for learning loop)
"""
from datetime import datetime, timedelta

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.creator import Creator
from app.models.outreach import OutreachMessage, Reply, Thread


def get_funnel_metrics(db: Session) -> dict:
    total_discovered = db.query(func.count(Creator.id)).scalar()
    total_qualified = db.query(func.count(Creator.id)).filter(
        Creator.status.in_(["qualified", "approved", "in_review"])
    ).scalar()
    total_approved = db.query(func.count(Creator.id)).filter(
        Creator.status == "approved"
    ).scalar()
    total_outreach_sent = db.query(func.count(OutreachMessage.id)).filter(
        OutreachMessage.status == "sent"
    ).scalar()
    total_replied = db.query(func.count(Reply.id)).scalar()
    total_interested = db.query(func.count(Reply.id)).filter(
        Reply.classification == "interested"
    ).scalar()
    total_converted = db.query(func.count(Thread.id)).filter(
        Thread.status == "converted"
    ).scalar()

    return {
        "discovered": total_discovered,
        "qualified": total_qualified,
        "approved_for_outreach": total_approved,
        "outreach_sent": total_outreach_sent,
        "replied": total_replied,
        "interested": total_interested,
        "converted": total_converted,
        "reply_rate": round(total_replied / total_outreach_sent, 4) if total_outreach_sent else 0,
        "interest_rate": round(total_interested / total_replied, 4) if total_replied else 0,
        "conversion_rate": round(total_converted / total_interested, 4) if total_interested else 0,
    }


def get_campaign_stats(db: Session, campaign_id: str = None) -> list[dict]:
    q = db.query(Campaign)
    if campaign_id:
        q = q.filter(Campaign.id == campaign_id)
    campaigns = q.all()

    results = []
    for c in campaigns:
        sent = db.query(func.count(OutreachMessage.id)).filter(
            OutreachMessage.campaign_id == c.id,
            OutreachMessage.status == "sent",
        ).scalar()
        replied = (
            db.query(func.count(Reply.id))
            .join(Thread, Thread.id == Reply.thread_id)
            .join(OutreachMessage, OutreachMessage.id == Thread.outreach_message_id)
            .filter(OutreachMessage.campaign_id == c.id)
            .scalar()
        )
        results.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "sent": sent,
            "replied": replied,
            "reply_rate": round(replied / sent, 4) if sent else 0,
            "daily_limit": c.daily_send_limit,
        })
    return results


def get_engagement_distribution(db: Session) -> dict:
    """Distribution of creators by engagement score bands."""
    creators = db.query(Creator.engagement_score).filter(
        Creator.engagement_score.isnot(None)
    ).all()
    scores = [c.engagement_score for c in creators]

    if not scores:
        return {"bands": {}}

    bands = {"0-2": 0, "2-4": 0, "4-6": 0, "6-8": 0, "8-10": 0}
    for s in scores:
        if s < 2:
            bands["0-2"] += 1
        elif s < 4:
            bands["2-4"] += 1
        elif s < 6:
            bands["4-6"] += 1
        elif s < 8:
            bands["6-8"] += 1
        else:
            bands["8-10"] += 1

    return {
        "bands": bands,
        "avg": round(sum(scores) / len(scores), 2),
        "min": round(min(scores), 2),
        "max": round(max(scores), 2),
        "count": len(scores),
    }


def get_reply_classification_breakdown(db: Session) -> dict:
    rows = (
        db.query(Reply.classification, func.count(Reply.id))
        .group_by(Reply.classification)
        .all()
    )
    return {cls: cnt for cls, cnt in rows}


def get_platform_breakdown(db: Session) -> dict:
    rows = (
        db.query(Creator.platform, func.count(Creator.id))
        .group_by(Creator.platform)
        .all()
    )
    return {p: c for p, c in rows}


def get_top_performing_messages(db: Session, limit: int = 10) -> list[dict]:
    """
    Learning loop: find messages that got interested/positive replies.
    Used to identify patterns in high-performing outreach.
    """
    top_threads = (
        db.query(Thread)
        .join(Reply, Reply.thread_id == Thread.id)
        .filter(Reply.classification == "interested")
        .limit(limit)
        .all()
    )
    results = []
    for t in top_threads:
        msg = db.get(OutreachMessage, t.outreach_message_id)
        if msg:
            results.append({
                "thread_id": t.id,
                "creator_id": t.creator_id,
                "subject": msg.subject,
                "body_preview": msg.body[:200] if msg.body else "",
                "send_method": msg.send_method,
            })
    return results


def get_dashboard_summary(db: Session) -> dict:
    return {
        "funnel": get_funnel_metrics(db),
        "platform_breakdown": get_platform_breakdown(db),
        "engagement_distribution": get_engagement_distribution(db),
        "reply_classification": get_reply_classification_breakdown(db),
        "campaigns": get_campaign_stats(db),
    }
