"""
Module 5 — Contact Discovery & Validation.

POLICY:
- Only public business contact paths are stored.
- No private email scraping, no data brokers, no hidden contact info.
- Sources: bio links, linktree, website contact pages, management agencies listed publicly.

Validates contacts and checks suppression list before storing.
"""
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.creator import Contact, Creator
from app.models.outreach import SuppressionList
from app.services import audit as audit_svc
from app.services.suppression import is_suppressed

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def extract_emails_from_text(text: str) -> list[str]:
    """Extract email addresses from free text (bio, website copy, etc.)."""
    return list(set(EMAIL_REGEX.findall(text or "")))


def add_contact(
    db: Session,
    creator_id: str,
    contact_type: str,
    value: str,
    source: str,
    notes: str = None,
    actor: str = "system",
) -> Contact:
    """
    Add a public contact for a creator.
    Checks suppression list and deduplicates before adding.
    """
    # Suppression check
    email = value if "@" in value else None
    if is_suppressed(db, creator_id=creator_id, email=email):
        raise ValueError(f"Contact {value} is suppressed — cannot add")

    # Dedup check
    existing = (
        db.query(Contact)
        .filter(Contact.creator_id == creator_id, Contact.value == value)
        .first()
    )
    if existing:
        return existing

    contact = Contact(
        creator_id=creator_id,
        contact_type=contact_type,
        value=value,
        source=source,
        is_public=True,  # always True — policy enforced here
        notes=notes,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    audit_svc.log(
        db, action="contact_added", entity_type="contact",
        entity_id=contact.id, actor=actor,
        details={"contact_type": contact_type, "source": source, "creator_id": creator_id},
    )
    return contact


def validate_contact(
    db: Session,
    contact_id: str,
    is_valid: bool,
    notes: str = None,
    reviewer: str = "system",
) -> Contact:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise ValueError("Contact not found")
    contact.is_verified = True
    contact.is_valid = is_valid
    contact.validation_notes = notes
    contact.last_verified_at = datetime.utcnow()
    db.commit()
    audit_svc.log(
        db, action="contact_validated", entity_type="contact",
        entity_id=contact_id, actor=reviewer,
        details={"is_valid": is_valid, "notes": notes},
    )
    return contact


def discover_contacts_from_profile(
    db: Session,
    creator_id: str,
    platform: str,
    actor: str = "system",
) -> list[Contact]:
    """
    Pulls public profile data from platform integration and extracts contacts.
    Only harvests from publicly visible profile fields.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    from app.integrations.youtube import youtube
    from app.integrations.instagram import instagram
    from app.integrations.tiktok import tiktok

    adapter_map = {"youtube": youtube, "instagram": instagram, "tiktok": tiktok}
    adapter = adapter_map.get(platform)
    if not adapter or not adapter.is_configured():
        return []

    try:
        info = adapter.get_public_contact_info(creator.handle)
    except Exception:
        return []

    contacts = []
    # Email from bio
    for email in extract_emails_from_text(info.get("bio", "")):
        try:
            c = add_contact(db, creator_id, "email", email, "platform_bio", actor=actor)
            contacts.append(c)
        except ValueError:
            pass

    # Website
    if info.get("website"):
        try:
            c = add_contact(db, creator_id, "business_inquiry_form", info["website"], "platform_profile", actor=actor)
            contacts.append(c)
        except ValueError:
            pass

    return contacts


def get_contacts_for_creator(db: Session, creator_id: str) -> list[Contact]:
    return (
        db.query(Contact)
        .filter(
            Contact.creator_id == creator_id,
            Contact.is_suppressed.is_(False),
            Contact.is_valid.isnot(False),
        )
        .all()
    )


def suppress_contact(db: Session, contact_id: str, reason: str, actor: str = "system") -> Contact:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise ValueError("Contact not found")
    contact.is_suppressed = True
    db.commit()
    from app.services.suppression import add_suppression
    if "@" in contact.value:
        add_suppression(
            db, reason=reason, email=contact.value,
            creator_id=contact.creator_id,
            suppressed_by=actor, actor=actor,
        )
    return contact
