"""
Full Discovery Pipeline with A-to-Z tracking.
Every step is recorded in pipeline_runs, pipeline_steps, scrape_logs, email_tracker.
"""
import re
import time
import httpx
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from app.config import settings
from app.models.creator import Creator, YoutubeLead, Contact
from app.models.pipeline import PipelineRun, PipelineStep, EmailTracker, ScrapeLog


def discover_creators_by_niche(
    db: Session,
    keyword: str,
    max_results: int = 10,
) -> dict:
    """
    Full tracked pipeline. Returns dict with run_id + results.
    """
    t0 = time.time()

    # Create pipeline run record
    run = PipelineRun(keyword=keyword, max_results=max_results, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    results = {"run_id": run.id, "creators": [], "errors": []}

    # ── STEP 1: YouTube Search ───────────────────────────────────────────
    step1 = PipelineStep(run_id=run.id, step_name="youtube_search", status="running")
    db.add(step1)
    db.commit()

    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        step1.status = "failed"
        step1.detail = {"error": "YOUTUBE_API_KEY not set"}
        step1.completed_at = datetime.utcnow()
        db.commit()
        run.status = "failed"
        run.errors = ["YOUTUBE_API_KEY not configured"]
        run.completed_at = datetime.utcnow()
        db.commit()
        raise RuntimeError("YOUTUBE_API_KEY not configured")

    headers = {"Accept": "application/json"}
    channel_ids = []
    channels = []

    try:
        st = time.time()
        search_url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&type=channel&q={keyword}"
            f"&maxResults={max_results}&key={api_key}"
        )
        r = httpx.get(search_url, headers=headers, timeout=15)
        items = r.json().get("items", []) if r.status_code == 200 else []
        channel_ids = [item["snippet"]["channelId"] for item in items]

        # Log scrape
        db.add(ScrapeLog(
            run_id=run.id, source="youtube_api", keyword=keyword,
            results_count=len(channel_ids), status="completed",
            duration_ms=int((time.time() - st) * 1000),
        ))

        # Fetch full details
        if channel_ids:
            ch_url = (
                f"https://www.googleapis.com/youtube/v3/channels"
                f"?part=snippet,statistics,contentDetails"
                f"&id={','.join(channel_ids)}&key={api_key}"
            )
            r2 = httpx.get(ch_url, headers=headers, timeout=15)
            channels = r2.json().get("items", []) if r2.status_code == 200 else []

        step1.status = "completed"
        step1.detail = {"channels_found": len(channels)}
        step1.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        step1.status = "failed"
        step1.detail = {"error": str(e)}
        step1.completed_at = datetime.utcnow()
        results["errors"].append(f"YouTube search: {e}")
        db.commit()

    # ── STEP 2: Apify Email Scrape ───────────────────────────────────────
    step2 = PipelineStep(run_id=run.id, step_name="apify_email", status="running")
    db.add(step2)
    db.commit()

    email_map = {}
    apify_key = settings.APIFY_API_KEY
    if apify_key and channel_ids:
        try:
            st = time.time()
            email_map = _scrape_emails_apify(channel_ids, keyword, apify_key)
            db.add(ScrapeLog(
                run_id=run.id, source="apify_email", keyword=keyword,
                results_count=len(email_map), status="completed",
                duration_ms=int((time.time() - st) * 1000),
            ))
            step2.status = "completed"
            step2.detail = {"emails_found": len(email_map)}
        except Exception as e:
            step2.status = "failed"
            step2.detail = {"error": str(e)}
            results["errors"].append(f"Apify email: {e}")
            db.add(ScrapeLog(
                run_id=run.id, source="apify_email", keyword=keyword,
                results_count=0, status="failed", error=str(e),
            ))
    else:
        step2.status = "skipped"
        step2.detail = {"reason": "No APIFY_API_KEY or no channels"}

    step2.completed_at = datetime.utcnow()
    db.commit()

    # ── STEP 3: Save to DB ───────────────────────────────────────────────
    step3 = PipelineStep(run_id=run.id, step_name="save_creators", status="running")
    db.add(step3)
    db.commit()

    saved_creators = []
    for ch in channels:
        try:
            ch_id = ch["id"]
            snippet = ch["snippet"]
            stats = ch.get("statistics", {})
            subs = int(stats.get("subscriberCount", 0))
            handle = snippet.get("customUrl", "").lstrip("@") or ch_id
            display_name = snippet.get("title", handle)
            bio = snippet.get("description", "")
            avatar = (
                snippet.get("thumbnails", {}).get("high", {}).get("url")
                or snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
            )

            existing = db.query(Creator).filter(
                Creator.handle == handle, Creator.platform == "youtube"
            ).first()

            if existing:
                creator = existing
                creator.display_name = display_name
                creator.bio = bio
                creator.avatar_url = avatar
                creator.follower_count = subs
            else:
                creator = Creator(
                    handle=handle, platform="youtube", display_name=display_name,
                    bio=bio, profile_url=f"https://www.youtube.com/channel/{ch_id}",
                    avatar_url=avatar, follower_count=subs,
                    niche=_guess_niche(bio, keyword), status="discovered",
                    discovery_source=f"pipeline:{keyword}",
                )
                db.add(creator)
            db.flush()

            # Email
            email = email_map.get(ch_id, "")
            if not email:
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", bio)
                email = emails[0] if emails else ""

            if email:
                creator.email_public = email
                if not db.query(Contact).filter(Contact.creator_id == creator.id, Contact.value == email).first():
                    db.add(Contact(creator_id=creator.id, contact_type="email", value=email, source="pipeline_apify", is_verified=True))

            # YouTube lead
            yt = db.query(YoutubeLead).filter(YoutubeLead.id == creator.id).first()
            if not yt:
                yt = YoutubeLead(id=creator.id)
                db.add(yt)
            yt.channel_id = ch_id
            yt.subscriber_count = subs
            yt.video_count = int(stats.get("videoCount", 0))
            yt.total_views = int(stats.get("viewCount", 0))
            db.flush()

            saved_creators.append({
                "id": creator.id, "handle": creator.handle,
                "display_name": display_name, "followers": subs,
                "email": email or None, "channel_id": ch_id,
                "avatar_url": avatar, "niche": creator.niche,
            })
        except Exception as e:
            results["errors"].append(f"Save {ch.get('id','?')}: {e}")

    db.commit()
    step3.status = "completed"
    step3.detail = {"creators_saved": len(saved_creators)}
    step3.completed_at = datetime.utcnow()
    db.commit()

    # ── Finalize run ─────────────────────────────────────────────────────
    run.creators_found = len(saved_creators)
    run.emails_found = len([c for c in saved_creators if c.get("email")])
    run.status = "completed"
    run.duration_ms = int((time.time() - t0) * 1000)
    run.completed_at = datetime.utcnow()
    run.errors = results["errors"] if results["errors"] else []
    db.commit()

    results["creators"] = saved_creators
    return results


def track_email_sent(db: Session, run_id: str, creator_id: str, creator_name: str,
                     to_email: str, subject: str, status: str, resend_id: str = None,
                     error: str = None):
    """Record an email send in the tracker."""
    tracker = EmailTracker(
        run_id=run_id, creator_id=creator_id, creator_name=creator_name,
        to_email=to_email, subject=subject, status=status,
        resend_id=resend_id, error_message=error,
        sent_at=datetime.utcnow() if status == "sent" else None,
    )
    db.add(tracker)
    db.commit()
    return tracker


def _scrape_emails_apify(channel_ids, keyword, apify_key):
    """
    Uses dataovercoffee/youtube-channel-business-email-scraper via direct HTTP API.
    No apify_client SDK needed — avoids import errors on Vercel.
    """
    channel_urls = [f"https://www.youtube.com/channel/{cid}" for cid in channel_ids]
    run_input = {"channels": channel_urls}

    print(f"[Apify] Scraping emails for {len(channel_urls)} channels via HTTP API...")

    # Start run synchronously and get dataset items in one call
    api_url = (
        f"https://api.apify.com/v2/acts/dataovercoffee~youtube-channel-business-email-scraper"
        f"/run-sync-get-dataset-items?token={apify_key}&timeout=90"
    )
    r = httpx.post(
        api_url,
        json=run_input,
        headers={"Content-Type": "application/json"},
        timeout=120,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Apify HTTP {r.status_code}: {r.text[:300]}")

    dataset_items = r.json() if isinstance(r.json(), list) else []
    print(f"[Apify] Got {len(dataset_items)} results")

    email_map = {}
    for item in dataset_items:
        email = (
            item.get("Email")
            or item.get("email")
            or item.get("businessEmail")
            or ""
        )
        item_channel_id = item.get("ChannelId") or ""
        if not email or "@" not in email:
            continue
        if item_channel_id in channel_ids:
            email_map[item_channel_id] = email.strip()
            print(f"[Apify] Found email for {item_channel_id}: {email.strip()}")
        else:
            for cid in channel_ids:
                if cid not in email_map:
                    email_map[cid] = email.strip()
                    print(f"[Apify] Mapped email {email.strip()} to {cid}")
                    break
    return email_map


def _guess_niche(bio, keyword):
    bio_lower = (bio or "").lower()
    kw_lower = keyword.lower()
    niche_map = {
        "Tech & Gadgets": ["tech", "technology", "gadget", "software", "coding", "ai"],
        "Finance & Investing": ["finance", "invest", "money", "crypto", "stock"],
        "Fitness & Gym": ["fitness", "workout", "gym", "health"],
        "Cooking & Food": ["cook", "recipe", "food", "kitchen"],
        "Gaming": ["gaming", "gamer", "esport"],
        "Education": ["learn", "teach", "tutorial", "course"],
        "Business & Marketing": ["entrepreneur", "business", "startup", "marketing"],
    }
    tags = []
    for tag, kws in niche_map.items():
        if any(k in bio_lower or k in kw_lower for k in kws):
            tags.append(tag)
    return tags or ["Lifestyle & Creativity"]
