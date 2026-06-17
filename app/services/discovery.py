"""
Module 1 — Creator Discovery.

Supports:
- Manual import (CSV or form)
- Platform search via integration adapters (when keys configured)
- Deduplication on (handle, platform)
- Auto-qualification gate: follower_count >= threshold
"""
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import Creator
from app.services import audit as audit_svc
from app.services.suppression import is_suppressed


def create_or_get_creator(
    db: Session,
    handle: str,
    platform: str,
    display_name: str = None,
    bio: str = None,
    profile_url: str = None,
    avatar_url: str = None,
    follower_count: int = 0,
    niche: list = None,
    location: str = None,
    website: str = None,
    email_public: str = None,
    discovery_source: str = "manual",
    notes: str = None,
    actor: str = "system",
) -> Tuple[Creator, bool]:
    """
    Creates a creator or returns existing.
    Returns (creator, created: bool).
    Runs dedup by (handle, platform).
    """
    existing = (
        db.query(Creator)
        .filter(Creator.handle == handle, Creator.platform == platform)
        .first()
    )
    if existing:
        return existing, False

    # Check suppression before adding
    if is_suppressed(db, creator_id=None, email=email_public):
        raise ValueError(f"Contact {email_public} is on suppression list")

    status = "discovered"
    if follower_count >= settings.MIN_FOLLOWERS_THRESHOLD:
        status = "qualified"

    creator = Creator(
        handle=handle,
        platform=platform,
        display_name=display_name or handle,
        bio=bio,
        profile_url=profile_url,
        avatar_url=avatar_url,
        follower_count=follower_count,
        niche=niche or [],
        location=location,
        website=website,
        email_public=email_public,
        status=status,
        discovery_source=discovery_source,
        discovery_notes=notes,
    )
    db.add(creator)
    db.commit()
    db.refresh(creator)

    audit_svc.log(
        db, action="creator_discovered", entity_type="creator",
        entity_id=creator.id, actor=actor,
        details={"platform": platform, "handle": handle, "follower_count": follower_count, "source": discovery_source},
    )
    return creator, True


def import_from_csv_rows(db: Session, rows: list[dict], actor: str = "system") -> dict:
    """
    Bulk import from parsed CSV rows.
    Expected columns: handle, platform, display_name, follower_count, niche, website, email_public
    Returns {"created": int, "skipped": int, "errors": list}
    """
    created = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            handle = row.get("handle", "").strip()
            platform = row.get("platform", "").strip().lower()
            if not handle or not platform:
                errors.append(f"Row {i}: missing handle or platform")
                continue
            follower_count = int(row.get("follower_count", 0) or 0)
            _, was_created = create_or_get_creator(
                db=db,
                handle=handle,
                platform=platform,
                display_name=row.get("display_name", "").strip() or None,
                follower_count=follower_count,
                niche=[t.strip() for t in str(row.get("niche", "")).split(",") if t.strip()],
                website=row.get("website", "").strip() or None,
                email_public=row.get("email_public", "").strip() or None,
                discovery_source="csv_import",
                actor=actor,
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")
    return {"created": created, "skipped": skipped, "errors": errors}


def discover_via_platform(
    db: Session, platform: str, query: str, actor: str = "system"
) -> dict:
    """
    Runs a platform integration search and imports discovered creators.
    """
    from app.integrations.youtube import youtube
    from app.integrations.instagram import instagram
    from app.integrations.tiktok import tiktok

    adapter_map = {"youtube": youtube, "instagram": instagram, "tiktok": tiktok}
    adapter = adapter_map.get(platform)
    if not adapter:
        raise ValueError(f"No integration for platform: {platform}")

    results = adapter.search_creators(
        query=query, min_followers=settings.MIN_FOLLOWERS_THRESHOLD
    )

    created = 0
    skipped = 0
    for r in results:
        try:
            _, was_created = create_or_get_creator(
                db=db,
                handle=r["handle"],
                platform=platform,
                display_name=r.get("display_name"),
                bio=r.get("bio"),
                profile_url=r.get("profile_url"),
                avatar_url=r.get("avatar_url"),
                follower_count=r.get("follower_count", 0),
                niche=r.get("niche_tags", []),
                website=r.get("website"),
                discovery_source=f"platform_search:{platform}",
                actor=actor,
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    return {"created": created, "skipped": skipped, "total_found": len(results)}


def list_discovery_queue(db: Session, skip: int = 0, limit: int = 50) -> list[Creator]:
    return (
        db.query(Creator)
        .filter(Creator.status == "discovered")
        .order_by(Creator.created_at.desc())
        .offset(skip).limit(limit).all()
    )


def list_qualified(db: Session, skip: int = 0, limit: int = 50) -> list[Creator]:
    return (
        db.query(Creator)
        .filter(Creator.status == "qualified")
        .order_by(Creator.follower_count.desc())
        .offset(skip).limit(limit).all()
    )


def update_creator_status(
    db: Session, creator_id: str, status: str, actor: str = "system", notes: str = None
) -> Creator:
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")
    old_status = creator.status
    creator.status = status
    creator.updated_at = datetime.utcnow()
    db.commit()
    audit_svc.log(
        db, action="creator_status_changed", entity_type="creator",
        entity_id=creator_id, actor=actor,
        details={"old_status": old_status, "new_status": status, "notes": notes},
    )
    return creator
