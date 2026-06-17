"""
Module 6 — Outreach Draft Generation.

Generates personalized outreach email/message drafts.
All drafts start in "draft" status — never auto-sent.
Human review is always required before messages can be queued.
"""
import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import Analysis, Creator, Deck, ProductRecommendation
from app.models.outreach import OutreachMessage
from app.services import audit as audit_svc


def _build_outreach_prompt(
    creator: Creator,
    rec: ProductRecommendation,
    analysis: Optional[Analysis],
    include_deck: bool,
    tone: str,
) -> str:
    pain_points = ""
    if analysis and analysis.audience_pain_points:
        pain_points = "\n".join(f"  - {p}" for p in analysis.audience_pain_points)

    return f"""You are writing a personalized cold outreach email for a creator partnership.

Creator: {creator.display_name} (@{creator.handle}) on {creator.platform}
Followers: {creator.follower_count:,}
Niche: {', '.join(creator.niche or []) or 'unknown'}

Product Pitch: {rec.product_name} — {rec.tagline}
Description: {rec.description}
Revenue Potential: {rec.revenue_potential}

Audience Pain Points:
{pain_points or "Unknown — keep email general"}

Tone: {tone}
Include deck reference: {"Yes — mention we're attaching a deck" if include_deck else "No"}

Write a cold outreach email with:
- Subject line (concise, personalized, NOT clickbaity)
- Email body (3-4 short paragraphs max)

Rules:
- Address the creator by name
- Reference something SPECIFIC about their content/audience (not generic flattery)
- Lead with value, not a pitch
- One clear call to action: schedule a 30-min call
- Include a natural opt-out line ("reply STOP if you'd prefer not to hear from us")
- Professional but not corporate — conversational and human
- Under 250 words total

Return JSON:
{{
  "subject": "<subject line>",
  "body": "<full email body with \\n for line breaks>"
}}

Return ONLY valid JSON."""


def generate_outreach_draft(
    db: Session,
    creator_id: str,
    campaign_id: str,
    contact_id: str,
    product_recommendation_id: str,
    deck_id: str = None,
    send_method: str = "email",
    tone: str = "professional_friendly",
    actor: str = "system",
) -> OutreachMessage:
    creator = db.get(Creator, creator_id)
    rec = db.get(ProductRecommendation, product_recommendation_id)
    if not creator or not rec:
        raise ValueError("Creator or ProductRecommendation not found")

    analysis = (
        db.query(Analysis)
        .filter(Analysis.creator_id == creator_id)
        .order_by(Analysis.analyzed_at.desc())
        .first()
    )

    if not settings.ANTHROPIC_API_KEY:
        subject = f"Opportunity for {creator.display_name}: {rec.product_name}"
        body = (
            f"Hi {creator.display_name},\n\n"
            f"I came across your {creator.platform} and was impressed by your work in "
            f"{', '.join(creator.niche or ['your space'])}.\n\n"
            f"We've been thinking about building {rec.product_name} — {rec.tagline} — "
            f"and your audience seems like a perfect fit.\n\n"
            f"Would you be open to a quick 30-minute call to explore this?\n\n"
            f"Best,\n[Your Name]\n\n"
            f"P.S. Reply STOP if you'd prefer not to hear from us."
        )
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = _build_outreach_prompt(creator, rec, analysis, bool(deck_id), tone)
        message = client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {"subject": "Partnership Opportunity", "body": raw}

        subject = data.get("subject", f"Partnership: {rec.product_name}")
        body = data.get("body", "")

    msg = OutreachMessage(
        creator_id=creator_id,
        campaign_id=campaign_id,
        contact_id=contact_id,
        deck_id=deck_id,
        subject=subject,
        body=body,
        send_method=send_method,
        status="draft",   # always starts as draft — never auto-queued
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    audit_svc.log(
        db, action="outreach_draft_created", entity_type="outreach_message",
        entity_id=msg.id, actor=actor,
        details={"creator_id": creator_id, "campaign_id": campaign_id},
    )
    return msg


def submit_for_review(db: Session, message_id: str, actor: str = "system") -> OutreachMessage:
    msg = db.get(OutreachMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.status != "draft":
        raise ValueError(f"Message is {msg.status}, cannot submit for review")
    msg.status = "review_pending"
    msg.updated_at = datetime.utcnow()
    db.commit()
    audit_svc.log(
        db, action="outreach_submitted_for_review", entity_type="outreach_message",
        entity_id=message_id, actor=actor,
    )
    return msg


def update_draft(
    db: Session,
    message_id: str,
    subject: str = None,
    body: str = None,
    actor: str = "system",
) -> OutreachMessage:
    msg = db.get(OutreachMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.status not in ("draft", "review_pending"):
        raise ValueError(f"Cannot edit message in status: {msg.status}")
    if subject:
        msg.subject = subject
    if body:
        msg.body = body
    msg.status = "draft"  # editing resets to draft
    msg.updated_at = datetime.utcnow()
    db.commit()
    audit_svc.log(
        db, action="outreach_draft_edited", entity_type="outreach_message",
        entity_id=message_id, actor=actor,
    )
    return msg
