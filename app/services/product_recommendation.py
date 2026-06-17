"""
Module 3 — Product/Business Recommendation.

Generates tailored product/business recommendations for a creator
based on their niche, audience pain points, and demand signals.
"""
import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import Analysis, Creator, ProductRecommendation
from app.services import audit as audit_svc


def _build_product_prompt(creator: Creator, analysis: Optional[Analysis]) -> str:
    demand_signals = ""
    pain_points = ""
    if analysis:
        demand_signals = json.dumps(analysis.audience_demand_signals or {}, indent=2)
        pain_points = "\n".join(f"  - {p}" for p in (analysis.audience_pain_points or []))

    return f"""You are a product strategist helping identify the BEST business/product to build for a creator.

Creator Profile:
- Name: {creator.display_name} (@{creator.handle}) on {creator.platform}
- Followers: {creator.follower_count:,}
- Niche: {', '.join(creator.niche or []) or 'unknown'}
- Bio: {creator.bio or 'N/A'}

Audience Demand Signals:
{demand_signals or "No analysis available — use niche knowledge."}

Audience Pain Points:
{pain_points or "Unknown"}

Generate the TOP 3 product/business recommendations for this creator.
Return a JSON array with exactly 3 items, each with:
{{
  "product_name": "<name>",
  "product_category": "<category: course|community|app|physical_product|saas|coaching|newsletter|other>",
  "tagline": "<one-line tagline>",
  "description": "<2-3 sentence description>",
  "target_audience": "<who this serves>",
  "revenue_model": "<how it makes money>",
  "revenue_potential": "<estimated ARR range like $200k-$1M>",
  "rationale": "<why this fits this creator specifically>",
  "confidence_score": <float 0-1>
}}

Return ONLY valid JSON array. Rank by confidence_score descending."""


def generate_recommendations(
    db: Session,
    creator_id: str,
    actor: str = "system",
) -> list[ProductRecommendation]:
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    analysis = (
        db.query(Analysis)
        .filter(Analysis.creator_id == creator_id)
        .order_by(Analysis.analyzed_at.desc())
        .first()
    )

    if not settings.ANTHROPIC_API_KEY:
        # Fallback stub
        rec = ProductRecommendation(
            creator_id=creator_id,
            product_name="[Placeholder] Creator's Signature Course",
            product_category="course",
            tagline="Learn directly from the expert",
            description="A course built around this creator's core expertise.",
            target_audience="The creator's existing audience",
            revenue_model="One-time purchase + upsells",
            revenue_potential="$100k-$500k ARR",
            rationale="AI key not configured — generic placeholder.",
            confidence_score=0.5,
            status="draft",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return [rec]

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_product_prompt(creator, analysis)

    message = client.messages.create(
        model=settings.AI_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        items = json.loads(match.group()) if match else []

    recs = []
    for item in items:
        rec = ProductRecommendation(
            creator_id=creator_id,
            product_name=item.get("product_name", "Unnamed Product"),
            product_category=item.get("product_category", "other"),
            tagline=item.get("tagline", ""),
            description=item.get("description", ""),
            target_audience=item.get("target_audience", ""),
            revenue_model=item.get("revenue_model", ""),
            revenue_potential=item.get("revenue_potential", ""),
            rationale=item.get("rationale", ""),
            confidence_score=float(item.get("confidence_score", 0.5)),
            status="draft",
        )
        db.add(rec)
        recs.append(rec)

    db.commit()
    for r in recs:
        db.refresh(r)

    audit_svc.log(
        db, action="product_recommendations_generated", entity_type="creator",
        entity_id=creator_id, actor=actor,
        details={"count": len(recs)},
    )
    return recs


def approve_recommendation(
    db: Session, rec_id: str, reviewer: str, notes: str = None
) -> ProductRecommendation:
    rec = db.get(ProductRecommendation, rec_id)
    if not rec:
        raise ValueError("Recommendation not found")
    rec.status = "approved"
    rec.reviewed_by = reviewer
    rec.reviewed_at = datetime.utcnow()
    db.commit()
    from app.models.audit import Review
    review = Review(
        entity_type="product_recommendation",
        entity_id=rec_id,
        reviewer=reviewer,
        decision="approved",
        notes=notes,
    )
    db.add(review)
    db.commit()
    return rec
