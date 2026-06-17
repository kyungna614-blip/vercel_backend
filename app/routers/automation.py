from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import urllib.parse
import httpx
import json
import re

from app.database import get_db
from app.config import settings
from app.models.creator import Creator, ProductRecommendation
from app.models.outreach import OutreachMessage
from app.services.ideas import get_creator_ideas, generate_landing_page_outline_and_scaffold
from app.services.outreach import send_outreach_email
from app.services.llm import llm_generate_json

router = APIRouter(prefix="/api/automation", tags=["automation"])

class TriggerRequest(BaseModel):
    keyword: str
    max_results: int = 3

class SelectProductRequest(BaseModel):
    idea_id: str

@router.post("/trigger")
def trigger_pipeline(request: TriggerRequest, db: Session = Depends(get_db)):
    """
    Step 1: Admin trigger that accepts a specific niche keyword.
    Uses YouTube API to find channels, then Apify to scrape emails.
    Step 2: AI Product Generation Engine (Claude).
    Step 3: Automated Cold Outreach.
    """
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="YOUTUBE_API_KEY not set in .env")

    # Step 1: YouTube Data API search
    search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={urllib.parse.quote(request.keyword)}&key={api_key}&maxResults={request.max_results}"
    
    r = httpx.get(search_url, timeout=15)
    items = r.json().get("items", [])
    
    channels_found = []
    for item in items:
        channel_id = item["snippet"]["channelId"]
        ch_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={channel_id}&key={api_key}"
        r2 = httpx.get(ch_url, timeout=15)
        ch_items = r2.json().get("items", [])
        if ch_items:
            ch_data = ch_items[0]
            channels_found.append({
                "channel_id": channel_id,
                "title": ch_data["snippet"]["title"],
                "description": ch_data["snippet"]["description"],
                "url": f"https://www.youtube.com/channel/{channel_id}",
                "custom_url": ch_data["snippet"].get("customUrl", ""),
                "subscriber_count": int(ch_data["statistics"].get("subscriberCount", 0))
            })

    # ── Apify: scrape business emails (dataovercoffee actor + v3 API) ──
    apify_token = settings.APIFY_API_KEY
    if apify_token and channels_found:
        from apify_client import ApifyClient  # type: ignore[import-untyped]
        client = ApifyClient(apify_token)
        try:
            channel_urls = [ch["url"] for ch in channels_found]
            print(f"[Apify] Scraping emails for {len(channel_urls)} channels...")
            run = client.actor("dataovercoffee/youtube-channel-business-email-scraper").call(
                run_input={"channels": channel_urls},
            )
            # apify_client v3: Run object, not dict
            dataset_id = getattr(run, "default_dataset_id", None)
            if dataset_id is None and isinstance(run, dict):
                dataset_id = run.get("defaultDatasetId")
            if dataset_id:
                apify_items = list(client.dataset(dataset_id).iterate_items())
                print(f"[Apify] Got {len(apify_items)} results")
                for item in apify_items:
                    found_email = item.get("Email") or item.get("email") or item.get("businessEmail") or ""
                    item_cid = item.get("ChannelId") or ""
                    if found_email and "@" in found_email:
                        for ch in channels_found:
                            if ch["channel_id"] == item_cid and not ch.get("email"):
                                ch["email"] = found_email.strip()
                                print(f"[Apify] Email for {ch['title']}: {found_email.strip()}")
                                break
        except Exception as e:
            print(f"[Apify] Batch email scrape error: {e}")

    # ── Fallback: extract emails from channel description (bio) ──
    for ch in channels_found:
        if not ch.get("email"):
            bio_emails = re.findall(
                r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
                ch.get("description", ""),
            )
            ch["email"] = bio_emails[0] if bio_emails else None

    processed = []
    for ch in channels_found:
        handle = ch["custom_url"].replace("@", "") if ch["custom_url"] else ch["channel_id"]
        
        # Save to DB
        creator = db.query(Creator).filter(Creator.platform == "youtube", Creator.handle == handle).first()
        if not creator:
            creator = Creator(
                handle=handle,
                platform="youtube",
                display_name=ch["title"],
                bio=ch["description"],
                follower_count=ch["subscriber_count"],
                email_public=ch.get("email") or f"{handle}@example.com",
                niche=[request.keyword],
                profile_url=ch["url"],
                status="discovered"
            )
            db.add(creator)
            db.commit()
            db.refresh(creator)
            
        # Step 2: AI Product Generation Engine
        ideas = get_creator_ideas(db, creator.id)
        
        # Step 3: Automated Cold Outreach
        if ideas:
            idea = ideas[0]
            app_url = getattr(settings, "FRONTEND_URL", "https://creatorforge.app")
            onboard_link = f"{app_url}/onboard/{creator.id}"
            
            subject = f"Custom product for {creator.display_name}'s audience"
            body = (
                f"Hi {creator.display_name},\n\n"
                f"We built a custom product specifically for your audience called {idea.product_name}. "
                f"Review and launch your landing page here: {onboard_link}\n\n"
                f"Best,\nCreator Forge Team\n\nReply STOP to unsubscribe."
            )
            
            try:
                send_outreach_email(db, creator.id, subject, body)
            except Exception as e:
                print(f"Failed to send outreach: {e}")

        processed.append({
            "creator_id": creator.id,
            "handle": creator.handle,
            "email": creator.email_public,
            "ideas_generated": len(ideas) if ideas else 0
        })

    return {"status": "success", "processed_creators": processed}

@router.get("/onboard/{creator_id}")
def get_onboarding_page(creator_id: str, db: Session = Depends(get_db)):
    """
    Step 4: Route them to a dynamic onboard page displaying their 3 customized product ideas.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")
        
    ideas = db.query(ProductRecommendation).filter(ProductRecommendation.creator_id == creator_id).all()
    
    return {
        "creator": {
            "name": creator.display_name,
            "handle": creator.handle,
            "platform": creator.platform,
            "avatar": creator.avatar_url,
            "bio": creator.bio,
            "follower_count": creator.follower_count,
            "niche": creator.niche,
            "profile_url": creator.profile_url,
        },
        "ideas": [
            {
                "id": idea.id,
                "product_name": idea.product_name,
                "product_description": idea.description,
                "business_model": idea.revenue_model,
                "ai_reasoning": idea.rationale,
            } for idea in ideas
        ]
    }

@router.post("/onboard/{creator_id}/select")
def select_product(creator_id: str, request: SelectProductRequest, db: Session = Depends(get_db)):
    """
    Step 4 continued: Creator selects their preferred idea. Deploy and activate Landing Page.
    """
    try:
        updated_idea = generate_landing_page_outline_and_scaffold(db, creator_id, request.idea_id)
        app_url = getattr(settings, "FRONTEND_URL", "https://creatorforge.app")
        return {
            "status": "success",
            "message": "Dynamic template Landing Page activated!",
            "landing_page_url": f"{app_url}/launch/{creator_id}",
            "landing_page_data": updated_idea.landing_page_outline
        }
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.get("/dashboard/{creator_id}")
def get_post_launch_dashboard(creator_id: str, db: Session = Depends(get_db)):
    """
    Step 5: Route the onboarded creator to a dashboard portal.
    Generate 3 weekly video promotional scripts using Claude and display simulated analytics.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    selected_idea = db.query(ProductRecommendation).filter(
        ProductRecommendation.creator_id == creator_id,
        ProductRecommendation.status == "approved"
    ).first()

    if not selected_idea:
        raise HTTPException(400, "No product idea selected yet.")

    scripts = []
    try:
        prompt = f"""You are a top-tier YouTube growth strategist.
Generate 3 weekly video promotional scripts, hooks, and content suggestions for this creator to pitch their new product.

Creator: {creator.display_name}
Niche: {', '.join(creator.niche or [])}
Product: {selected_idea.product_name}
Tagline: {selected_idea.tagline}

Format strictly as a JSON array of 3 objects:
[
  {{
    "week": 1,
    "video_title_idea": "...",
    "hook": "...",
    "script_outline": "...",
    "call_to_action": "..."
  }}
]
"""
        result = llm_generate_json(prompt, max_tokens=1500)
        if isinstance(result, list):
            scripts = result
        elif isinstance(result, dict):
            scripts = result.get("scripts", result.get("promotional_scripts", []))
    except Exception as e:
        print(f"LLM error generating scripts: {e}")

    if not scripts:
        scripts = [
            {
                "week": 1,
                "video_title_idea": f"The BIG Secret I've Been Working On... ({selected_idea.product_name})",
                "hook": f"You guys have been asking me for months how to {selected_idea.tagline.lower()}, and today I'm finally revealing the answer.",
                "script_outline": "1. Acknowledge the common problem. 2. Share your personal journey. 3. Introduce the product.",
                "call_to_action": "Click the link in the pinned comment to join the waitlist!"
            },
            {
                "week": 2,
                "video_title_idea": "How I Built My Custom Routine (Behind the Scenes)",
                "hook": "Here is exactly how I use the tools I just launched.",
                "script_outline": "1. Fast-paced montage. 2. Break down the features. 3. Show live proof.",
                "call_to_action": "Get access to the exact system I use right now by clicking the link below."
            },
            {
                "week": 3,
                "video_title_idea": "Answering YOUR Questions About The Launch!",
                "hook": "The response to the launch has been insane! Today I'm answering all your questions.",
                "script_outline": "1. Highlight 3-4 questions from comments. 2. Provide clear answers. 3. Emphasize limited-time discount.",
                "call_to_action": "The launch discount ends in 48 hours, so secure your spot now."
            }
        ]

        # Real creator profile data (no fake analytics)
    niche_list = creator.niche or []
    outreach_msgs = db.query(OutreachMessage).filter(OutreachMessage.creator_id == creator_id).all()
    outreach_count = len(outreach_msgs)
    sent_count = sum(1 for m in outreach_msgs if m.status == "sent")

    return {
        "creator_id": creator.id,
        "creator": {
            "name": creator.display_name,
            "handle": creator.handle,
            "platform": creator.platform,
            "avatar_url": creator.avatar_url,
            "bio": creator.bio,
            "follower_count": creator.follower_count,
            "niche": niche_list,
            "email": creator.email_public,
            "profile_url": creator.profile_url,
        },
        "product": {
            "name": selected_idea.product_name,
            "tagline": selected_idea.tagline,
            "description": selected_idea.description,
            "category": selected_idea.product_category,
            "revenue_model": selected_idea.revenue_model,
            "target_audience": selected_idea.target_audience,
            "status": "LIVE",
            "landing_page_outline": selected_idea.landing_page_outline,
        },
        "promotional_scripts": scripts,
        "outreach": {
            "total": outreach_count,
            "sent": sent_count,
        },
    }