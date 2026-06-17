from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.creator import Creator
from app.services import discovery, analysis as analysis_svc, product_recommendation, deck_generator
from app.services.contact_discovery import add_contact, get_contacts_for_creator, validate_contact
from app.services.scraper import scrape_profile

router = APIRouter(prefix="/api/creators", tags=["creators"])


class CreatorCreate(BaseModel):
    handle: str
    platform: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    follower_count: int = 0
    niche: list[str] = []
    location: Optional[str] = None
    website: Optional[str] = None
    email_public: Optional[str] = None
    discovery_source: str = "manual"
    notes: Optional[str] = None


class ContactCreate(BaseModel):
    contact_type: str
    value: str
    source: str
    notes: Optional[str] = None


class ScrapeRequest(BaseModel):
    platform: str
    handle: str  # @handle, channel URL, or full URL
    save: bool = True  # auto-save to DB after scraping


@router.post("/scrape")
def scrape_creator(body: ScrapeRequest, actor: str = "internal", db: Session = Depends(get_db)):
    """
    Scrape a public profile and optionally save it.
    Parses handle from full URLs automatically.
    """
    import re
    handle = body.handle.strip()

    # Parse handle from URL
    yt_patterns = [
        r"youtube\.com/@([^/?&\s]+)",
        r"youtube\.com/channel/([^/?&\s]+)",
        r"youtube\.com/c/([^/?&\s]+)",
        r"youtube\.com/user/([^/?&\s]+)",
    ]
    ig_patterns = [r"instagram\.com/([^/?&\s]+)"]
    tt_patterns = [r"tiktok\.com/@([^/?&\s]+)"]

    if body.platform == "youtube":
        for pat in yt_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break
    elif body.platform == "instagram":
        for pat in ig_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break
    elif body.platform == "tiktok":
        for pat in tt_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break

    handle = handle.lstrip("@").strip("/")

    scraped = scrape_profile(body.platform, handle)
    if "error" in scraped and not scraped.get("display_name"):
        raise HTTPException(400, f"Scrape failed: {scraped['error']}")

    creator = None
    if body.save:
        try:
            creator, created = discovery.create_or_get_creator(
                db=db,
                handle=scraped["handle"],
                platform=scraped["platform"],
                display_name=scraped.get("display_name"),
                bio=scraped.get("bio"),
                profile_url=scraped.get("profile_url"),
                avatar_url=scraped.get("avatar_url"),
                follower_count=scraped.get("follower_count", 0),
                niche=scraped.get("niche", []),
                website=scraped.get("website"),
                email_public=scraped.get("email_public"),
                discovery_source="scrape",
                actor=actor,
            )
            # Auto-save any found email as a contact
            if scraped.get("email_public") and creator:
                try:
                    add_contact(
                        db, creator.id, "email",
                        scraped["email_public"], "scraped_bio", actor=actor,
                    )
                except Exception:
                    pass
            for link in scraped.get("social_links", [])[:3]:
                try:
                    add_contact(
                        db, creator.id, "business_inquiry_form",
                        link, "scraped_profile", actor=actor,
                    )
                except Exception:
                    pass
        except ValueError as e:
            raise HTTPException(400, str(e))

    return {
        "scraped": scraped,
        "creator": _creator_dict(creator) if creator else None,
        "created": creator is not None,
    }


@router.post("")
def create_creator(body: CreatorCreate, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        creator, created = discovery.create_or_get_creator(
            db=db, actor=actor, **body.model_dump()
        )
        return {"created": created, "creator": _creator_dict(creator)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_creators(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Creator)
    if status:
        q = q.filter(Creator.status == status)
    if platform:
        q = q.filter(Creator.platform == platform)
    creators = q.order_by(Creator.follower_count.desc()).offset(skip).limit(limit).all()
    return [_creator_dict(c) for c in creators]


@router.get("/{creator_id}")
def get_creator(creator_id: str, db: Session = Depends(get_db)):
    c = db.get(Creator, creator_id)
    if not c:
        raise HTTPException(404, "Creator not found")
    return _creator_dict(c)


@router.patch("/{creator_id}/status")
def update_status(
    creator_id: str, status: str, notes: Optional[str] = None,
    actor: str = "internal", db: Session = Depends(get_db)
):
    try:
        c = discovery.update_creator_status(db, creator_id, status, actor, notes)
        return _creator_dict(c)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{creator_id}/analyze")
def run_analysis(creator_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        result = analysis_svc.run_ai_analysis(db, creator_id, actor=actor)
        return {"analysis_id": result.id, "summary": result.summary, "score": result.engagement_quality_score}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{creator_id}/recommend")
def generate_products(creator_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        recs = product_recommendation.generate_recommendations(db, creator_id, actor=actor)
        return [_rec_dict(r) for r in recs]
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{creator_id}/pitch-package")
def generate_pitch_package(creator_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    """
    One-click: generates product recommendation + pitch deck + outreach email.
    Returns everything needed to pitch this creator.
    """
    from app.models.creator import ProductRecommendation, Deck
    from app.services.outreach_generator import generate_outreach_draft
    from app.models.outreach import OutreachMessage

    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    # 1. Get or generate product recommendation
    rec = (
        db.query(ProductRecommendation)
        .filter(ProductRecommendation.creator_id == creator_id)
        .order_by(ProductRecommendation.created_at.desc())
        .first()
    )
    if not rec:
        recs = product_recommendation.generate_recommendations(db, creator_id, actor=actor)
        rec = recs[0] if recs else None
    if not rec:
        raise HTTPException(500, "Could not generate product recommendation")

    # 2. Get or generate deck
    existing_deck = (
        db.query(Deck)
        .filter(Deck.creator_id == creator_id, Deck.product_recommendation_id == rec.id)
        .order_by(Deck.version.desc())
        .first()
    )
    deck = existing_deck or deck_generator.generate_deck(db, creator_id, rec.id, actor=actor)

    # 3. Generate outreach email (no campaign/contact required — draft only)
    # Build a temp structure
    from app.config import settings
    import json, re

    email_draft = _generate_email_draft(creator, rec, settings)

    # 4. Gather contacts
    contacts = get_contacts_for_creator(db, creator_id)

    return {
        "creator": _creator_dict(creator),
        "recommendation": _rec_dict(rec),
        "deck": {"id": deck.id, "title": deck.title, "slides": deck.slides, "version": deck.version},
        "email_draft": email_draft,
        "contacts": [_contact_dict(c) for c in contacts],
    }


def _generate_email_draft(creator, rec, settings) -> dict:
    """Generate email subject + body for pitch. Uses AI when configured, else rich template."""
    name       = creator.display_name or f"@{creator.handle}"
    handle     = creator.handle
    platform   = creator.platform.capitalize()
    niche_str  = ', '.join(creator.niche or [])
    followers  = creator.follower_count or 0
    bio        = (creator.bio or '').strip()

    def _fmt(n):
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M".replace('.0M', 'M')
        if n >= 1_000: return f"{n//1_000}K"
        return str(n)

    if not settings.ANTHROPIC_API_KEY:
        # Rich template that uses all scraped data
        bio_line = f"Your channel — \"{bio[:120]}{'...' if len(bio)>120 else ''}\" — " if bio else f"Your {platform} channel "
        niche_line = f"in the {niche_str} space" if niche_str else "in your space"
        subject = f"Partnership idea for {name}"
        body = (
            f"Hi {name},\n\n"
            f"{bio_line}caught my attention. {_fmt(followers)} followers {niche_line} — "
            f"and I think your audience is exactly who we've been trying to reach.\n\n"
            f"We're looking to build **{rec.product_name}** with the right creator — {rec.tagline}\n\n"
            f"{rec.description}\n\n"
            f"Revenue potential: {rec.revenue_potential}. "
            f"You'd bring the audience and trust; we handle the product and operations.\n\n"
            f"Would you be open to a quick 20-minute call this week to explore it?\n\n"
            f"Best,\n[Your Name]\n\n"
            f"P.S. Reply STOP anytime and I won't reach out again."
        )
        return {"subject": subject, "body": body}

    import anthropic, json, re
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = (
        f"Write a short, highly personalized cold outreach email for a creator partnership.\n\n"
        f"Creator: {name} (@{handle}) on {platform}\n"
        f"Followers: {_fmt(followers)}\n"
        f"Niche: {niche_str or 'general'}\n"
        f"Bio: {bio or 'N/A'}\n\n"
        f"Product pitch: {rec.product_name} — {rec.tagline}\n"
        f"Description: {rec.description}\n"
        f"Revenue potential: {rec.revenue_potential}\n\n"
        f"Rules:\n"
        f"- Max 200 words total\n"
        f"- Open with something SPECIFIC from their bio or content (not generic)\n"
        f"- Conversational, human tone — not corporate\n"
        f"- Lead with value to them, not what we want\n"
        f"- One CTA: 20-min call\n"
        f"- End with: 'Reply STOP anytime to opt out.'\n\n"
        f'Return JSON only: {{"subject": "...", "body": "..."}}'
    )
    msg = client.messages.create(
        model=settings.AI_MODEL, max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(m.group()) if m else {"subject": f"Partnership idea for {name}", "body": raw}
    return data


class SendRequest(BaseModel):
    subject: str
    body: str


@router.post("/{creator_id}/send")
def send_outreach(
    creator_id: str, body: SendRequest,
    actor: str = "internal", db: Session = Depends(get_db)
):
    """
    Human-approved send: user has reviewed and edited the email, now queues it.
    Creates the outreach message already marked approved so it goes straight to queue.
    """
    from app.models.outreach import OutreachMessage
    import uuid as _uuid_mod
    from datetime import datetime

    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    # Safety: check suppression
    if creator.status == "suppressed":
        raise HTTPException(400, "Creator is on suppression list")

    # Find best contact (email preferred)
    contacts = get_contacts_for_creator(db, creator_id)
    email_contacts = [c for c in contacts if c.contact_type == "email" and not c.is_suppressed]
    target_contact_id = email_contacts[0].id if email_contacts else None

    msg = OutreachMessage(
        id=str(_uuid_mod.uuid4()),
        creator_id=creator_id,
        contact_id=target_contact_id,
        subject=body.subject,
        body=body.body,
        status="approved",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(msg)

    # Mark creator as approved (outreach sent)
    if creator.status in ("discovered", "qualified", "in_review"):
        creator.status = "approved"
    creator.updated_at = datetime.utcnow()

    # Audit log
    from app.models.audit import AuditLog
    db.add(AuditLog(
        id=str(_uuid_mod.uuid4()),
        entity_type="outreach_message", entity_id=msg.id,
        action="human_approved_send", actor=actor,
        details={"subject": body.subject, "creator_id": creator_id},
        created_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "message_id": msg.id,
        "status": "approved",
        "contact_id": target_contact_id,
        "note": "Queued for send. Review in Dashboard → Outreach Queue.",
    }


@router.post("/{creator_id}/contacts")
def add_creator_contact(
    creator_id: str, body: ContactCreate,
    actor: str = "internal", db: Session = Depends(get_db)
):
    try:
        contact = add_contact(db, creator_id, body.contact_type, body.value, body.source, body.notes, actor)
        return _contact_dict(contact)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{creator_id}/contacts")
def list_contacts(creator_id: str, db: Session = Depends(get_db)):
    return [_contact_dict(c) for c in get_contacts_for_creator(db, creator_id)]


@router.patch("/contacts/{contact_id}/validate")
def validate(
    contact_id: str, is_valid: bool, notes: Optional[str] = None,
    reviewer: str = "internal", db: Session = Depends(get_db)
):
    try:
        c = validate_contact(db, contact_id, is_valid, notes, reviewer)
        return _contact_dict(c)
    except ValueError as e:
        raise HTTPException(404, str(e))


def _creator_dict(c: Creator) -> dict:
    return {
        "id": c.id, "handle": c.handle, "platform": c.platform,
        "display_name": c.display_name, "bio": c.bio,
        "profile_url": c.profile_url, "avatar_url": c.avatar_url,
        "follower_count": c.follower_count, "niche": c.niche or [],
        "location": c.location, "website": c.website,
        "email_public": c.email_public, "status": c.status,
        "discovery_source": c.discovery_source,
        "engagement_score": c.engagement_score,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _rec_dict(r) -> dict:
    return {
        "id": r.id, "product_name": r.product_name, "product_category": r.product_category,
        "tagline": r.tagline, "description": r.description,
        "revenue_potential": r.revenue_potential, "confidence_score": r.confidence_score,
        "status": r.status,
    }


def _contact_dict(c) -> dict:
    return {
        "id": c.id, "contact_type": c.contact_type, "value": c.value,
        "source": c.source, "is_verified": c.is_verified, "is_valid": c.is_valid,
        "is_suppressed": c.is_suppressed, "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
