"""
Module 4 — Pitch Deck Generation.

Generates a structured pitch deck (slide data) for a creator + product.
Stored as JSON slide objects — renderable in browser or exportable.
"""
import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import Creator, Deck, ProductRecommendation
from app.services import audit as audit_svc


SLIDE_SCHEMA = """
Each slide must be a JSON object:
{
  "slide_number": <int>,
  "type": "<cover|problem|solution|market|traction|product|partnership|team|ask|close>",
  "title": "<slide title>",
  "headline": "<main headline text>",
  "body": "<supporting copy (can use \\n for line breaks)>",
  "bullets": [<optional list of bullet strings>],
  "data_points": [<optional list of {label, value} objects>],
  "notes": "<speaker notes>"
}
"""


def _build_deck_prompt(creator: Creator, rec: ProductRecommendation) -> str:
    return f"""You are creating a personalized pitch deck for a creator partnership opportunity.

Creator: {creator.display_name} (@{creator.handle}) on {creator.platform}
Followers: {creator.follower_count:,}
Niche: {', '.join(creator.niche or []) or 'unknown'}
Bio: {creator.bio or 'N/A'}

Product Recommendation:
- Name: {rec.product_name}
- Category: {rec.product_category}
- Tagline: {rec.tagline}
- Description: {rec.description}
- Target Audience: {rec.target_audience}
- Revenue Model: {rec.revenue_model}
- Revenue Potential: {rec.revenue_potential}
- Rationale: {rec.rationale}

Generate a 10-slide pitch deck as a JSON array of slides.
Required slide types (in order): cover, problem, solution, market, traction, product, partnership, team, ask, close

{SLIDE_SCHEMA}

The deck should:
1. Be personalized — reference the creator by name and their specific audience
2. Lead with audience pain points as the problem
3. Position the product as purpose-built for this creator's audience
4. The "partnership" slide explains what we bring + what creator brings
5. The "ask" slide should be a clear call to schedule a discovery call
6. Be professional but conversational — not corporate jargon

Return ONLY a valid JSON array of 10 slide objects."""


def generate_deck(
    db: Session,
    creator_id: str,
    product_recommendation_id: str,
    actor: str = "system",
) -> Deck:
    creator = db.get(Creator, creator_id)
    rec = db.get(ProductRecommendation, product_recommendation_id)
    if not creator or not rec:
        raise ValueError("Creator or ProductRecommendation not found")

    if not settings.ANTHROPIC_API_KEY:
        slides = _fallback_slides(creator, rec)
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = _build_deck_prompt(creator, rec)
        message = client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        try:
            slides = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            slides = json.loads(match.group()) if match else _fallback_slides(creator, rec)

    # Check for existing deck version
    existing = (
        db.query(Deck)
        .filter(
            Deck.creator_id == creator_id,
            Deck.product_recommendation_id == product_recommendation_id,
        )
        .order_by(Deck.version.desc())
        .first()
    )
    version = (existing.version + 1) if existing else 1

    deck = Deck(
        creator_id=creator_id,
        product_recommendation_id=product_recommendation_id,
        title=f"{creator.display_name} × {rec.product_name}",
        slides=slides,
        version=version,
        status="draft",
    )
    db.add(deck)
    db.commit()
    db.refresh(deck)

    audit_svc.log(
        db, action="deck_generated", entity_type="deck",
        entity_id=deck.id, actor=actor,
        details={"creator_id": creator_id, "product": rec.product_name, "version": version},
    )
    return deck


def _fallback_slides(creator: Creator, rec: ProductRecommendation) -> list[dict]:
    return [
        {"slide_number": 1, "type": "cover", "title": "Cover",
         "headline": f"{creator.display_name} × {rec.product_name}",
         "body": rec.tagline, "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 2, "type": "problem", "title": "The Problem",
         "headline": "Your audience has a problem we can solve together",
         "body": f"Audiences in the {', '.join(creator.niche or ['your'])} space are underserved.",
         "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 3, "type": "solution", "title": "The Solution",
         "headline": rec.product_name,
         "body": rec.description, "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 4, "type": "market", "title": "Market Opportunity",
         "headline": f"A massive opportunity in {rec.product_category}",
         "body": f"Revenue potential: {rec.revenue_potential}",
         "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 5, "type": "traction", "title": "Your Traction",
         "headline": f"{creator.follower_count:,} engaged followers",
         "body": "Your audience is already telling you what they need.",
         "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 6, "type": "product", "title": "The Product",
         "headline": f"What {rec.product_name} looks like",
         "body": rec.description, "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 7, "type": "partnership", "title": "The Partnership",
         "headline": "Better together",
         "body": "You bring the audience and trust. We bring the infrastructure and team.",
         "bullets": ["You: Content, credibility, distribution", "Us: Product, operations, growth"],
         "data_points": [], "notes": ""},
        {"slide_number": 8, "type": "team", "title": "Our Team",
         "headline": "Experienced operators behind you",
         "body": "We've built and scaled creator businesses before.",
         "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 9, "type": "ask", "title": "The Ask",
         "headline": "Let's explore this together",
         "body": "We'd love to schedule a 30-minute discovery call.",
         "bullets": [], "data_points": [], "notes": ""},
        {"slide_number": 10, "type": "close", "title": "Next Steps",
         "headline": "Ready to build something great?",
         "body": "Reply to this email or book a call directly.",
         "bullets": [], "data_points": [], "notes": ""},
    ]


def finalize_deck(db: Session, deck_id: str, actor: str = "system") -> Deck:
    deck = db.get(Deck, deck_id)
    if not deck:
        raise ValueError("Deck not found")
    deck.status = "finalized"
    deck.updated_at = datetime.utcnow()
    db.commit()
    audit_svc.log(db, action="deck_finalized", entity_type="deck", entity_id=deck_id, actor=actor)
    return deck
