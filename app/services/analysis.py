"""
Module 2 — Engagement & Demand Analysis.

Computes:
- Engagement quality score (adjusted for follower count, comment quality)
- Audience demand signals from content topics + comments
- Brand safety score
- Overall creator score
"""
import json
import math
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import (
    Analysis, ContentSample, Creator, MetricsSnapshot
)
from app.services import audit as audit_svc


# ── Engagement Quality Scoring ──────────────────────────────────────────────

def compute_engagement_quality(
    followers: int,
    avg_likes: float,
    avg_comments: float,
    avg_views: float = 0,
) -> float:
    """
    Returns 0-10 quality-adjusted engagement score.

    Raw ER = (likes + comments) / followers.
    Adjusted for:
    - Follower tier (micro vs mega creators have different norms)
    - Comment weight (comments > likes for quality signal)
    """
    if followers <= 0:
        return 0.0

    raw_er = (avg_likes + avg_comments * 3) / followers  # weight comments 3x
    if avg_views > 0:
        view_er = (avg_likes + avg_comments) / avg_views
        raw_er = (raw_er + view_er) / 2

    # Tier benchmarks (industry approximation)
    if followers < 50_000:
        benchmark = 0.06
    elif followers < 200_000:
        benchmark = 0.04
    elif followers < 1_000_000:
        benchmark = 0.025
    else:
        benchmark = 0.015

    ratio = raw_er / benchmark if benchmark > 0 else 0
    score = min(10.0, ratio * 5)  # 2x benchmark → score of 10
    return round(score, 2)


def create_metrics_snapshot(
    db: Session,
    creator_id: str,
    followers: int,
    following: int = 0,
    posts_count: int = 0,
    avg_likes: float = 0,
    avg_comments: float = 0,
    avg_shares: float = 0,
    avg_views: float = 0,
    growth_rate_30d: float = 0,
) -> MetricsSnapshot:
    engagement_rate = (avg_likes + avg_comments) / followers if followers > 0 else 0
    quality_score = compute_engagement_quality(followers, avg_likes, avg_comments, avg_views)

    snap = MetricsSnapshot(
        creator_id=creator_id,
        followers=followers,
        following=following,
        posts_count=posts_count,
        avg_likes=avg_likes,
        avg_comments=avg_comments,
        avg_shares=avg_shares,
        avg_views=avg_views,
        engagement_rate=round(engagement_rate, 4),
        engagement_quality_score=quality_score,
        growth_rate_30d=growth_rate_30d,
    )
    db.add(snap)

    # Update creator's cached engagement score
    creator = db.get(Creator, creator_id)
    if creator:
        creator.engagement_score = quality_score
        creator.follower_count = followers

    db.commit()
    db.refresh(snap)
    return snap


# ── AI-Powered Demand Analysis ───────────────────────────────────────────────

def _build_analysis_prompt(creator: Creator, samples: list[ContentSample]) -> str:
    sample_text = ""
    for s in samples[:10]:
        sample_text += f"\n---\nCaption: {s.caption or '(none)'}\nLikes: {s.likes} | Comments: {s.comments}\n"
        if s.top_comments:
            sample_text += "Top comments:\n" + "\n".join(f"  - {c}" for c in s.top_comments[:5])

    return f"""You are analyzing a content creator for potential business/product partnership.

Creator: {creator.display_name} (@{creator.handle}) on {creator.platform}
Followers: {creator.follower_count:,}
Bio: {creator.bio or 'N/A'}
Niche tags: {', '.join(creator.niche or []) or 'unknown'}

Recent content samples:{sample_text}

Analyze this creator and return a JSON object with EXACTLY these keys:
{{
  "engagement_quality_score": <float 0-10>,
  "brand_safety_score": <float 0-10>,
  "content_themes": [<list of 3-8 main themes/topics>],
  "audience_demand_signals": {{
    "top_pain_points": [<list of problems audience faces>],
    "desire_signals": [<things audience wants/asks for>],
    "buying_intent_indicators": [<commercial intent phrases or patterns>],
    "community_strength": "<weak|moderate|strong|very_strong>"
  }},
  "recommended_niches": [<3-5 product/business niches that fit>],
  "audience_pain_points": [<list of 3-5 specific pain points>],
  "summary": "<2-3 sentence summary of why this creator is/isn't a strong partner opportunity>"
}}

Return ONLY valid JSON. No markdown, no explanation."""


def run_ai_analysis(
    db: Session,
    creator_id: str,
    analysis_type: str = "overall",
    actor: str = "system",
) -> Analysis:
    """
    Runs AI analysis on a creator using their profile + content samples.
    Requires ANTHROPIC_API_KEY to be set.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    samples = (
        db.query(ContentSample)
        .filter(ContentSample.creator_id == creator_id)
        .order_by(ContentSample.likes.desc())
        .limit(15)
        .all()
    )

    if not settings.ANTHROPIC_API_KEY:
        # Return a placeholder analysis when no API key
        analysis = Analysis(
            creator_id=creator_id,
            analysis_type=analysis_type,
            engagement_quality_score=creator.engagement_score or 0,
            brand_safety_score=7.0,
            content_themes=creator.niche or [],
            audience_demand_signals={"note": "AI key not configured — manual analysis required"},
            recommended_niches=creator.niche or [],
            audience_pain_points=[],
            summary="AI analysis not available. Configure ANTHROPIC_API_KEY.",
            raw_output="",
            model_used="none",
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_analysis_prompt(creator, samples)

    message = client.messages.create(
        model=settings.AI_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    analysis = Analysis(
        creator_id=creator_id,
        analysis_type=analysis_type,
        engagement_quality_score=data.get("engagement_quality_score", 0),
        brand_safety_score=data.get("brand_safety_score", 0),
        content_themes=data.get("content_themes", []),
        audience_demand_signals=data.get("audience_demand_signals", {}),
        recommended_niches=data.get("recommended_niches", []),
        audience_pain_points=data.get("audience_pain_points", []),
        summary=data.get("summary", ""),
        raw_output=raw,
        model_used=settings.AI_MODEL,
    )
    db.add(analysis)

    # Update creator score
    if analysis.engagement_quality_score:
        creator.engagement_score = analysis.engagement_quality_score

    db.commit()
    db.refresh(analysis)

    audit_svc.log(
        db, action="analysis_run", entity_type="analysis",
        entity_id=analysis.id, actor=actor,
        details={"analysis_type": analysis_type, "creator_id": creator_id},
    )
    return analysis


def get_latest_analysis(db: Session, creator_id: str) -> Optional[Analysis]:
    return (
        db.query(Analysis)
        .filter(Analysis.creator_id == creator_id)
        .order_by(Analysis.analyzed_at.desc())
        .first()
    )
