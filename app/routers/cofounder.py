from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.creator import Creator, YoutubeLead, InstagramLead, TiktokLead, TwitterLead
from app.models.outreach import OutreachMessage, Thread
from app.services.scraper import scrape_profile
from app.services.outreach import generate_outreach_email, send_outreach_email, process_drip_sequences
from app.services.ideas import get_creator_ideas, generate_landing_page_outline_and_scaffold
from app.services.dashboard import get_dashboard_data
from app.services.pipeline import discover_creators_by_niche, track_email_sent
from app.models.pipeline import PipelineRun, PipelineStep

router = APIRouter(prefix="/api/cofounder", tags=["cofounder"])

class ScrapeRequest(BaseModel):
    handle: str
    platform: str = "youtube"

class NicheDiscoveryRequest(BaseModel):
    keyword: str
    max_results: int = 10
    auto_generate_ideas: bool = True
    auto_send_outreach: bool = False

class SelectIdeaRequest(BaseModel):
    idea_id: str

class SendEmailRequest(BaseModel):
    subject: str
    body: str


@router.post("/scrape")
def scrape_creator_profile(payload: ScrapeRequest, db: Session = Depends(get_db)):
    """
    Scrape creator public details and public email.
    Save or update the creator profile in Supabase.
    """
    handle = payload.handle.strip()
    platform = payload.platform.strip().lower()

    if not handle:
        raise HTTPException(400, "Handle is required")

    # Check if creator already exists in db
    existing = db.query(Creator).filter(
        Creator.handle == handle,
        Creator.platform == platform
    ).first()

    try:
        scraped_data = scrape_profile(platform, handle)
    except Exception as e:
        raise HTTPException(502, f"Failed to scrape profile: {e}")

    if "error" in scraped_data:
        raise HTTPException(400, scraped_data["error"])

    # Map status: default is 'discovered' (we'll represent 'pending' on the UI using 'discovered')
    # If the creator exists, update their profile details
    if existing:
        creator = existing
        creator.display_name = scraped_data.get("display_name", creator.display_name)
        creator.bio = scraped_data.get("bio", creator.bio)
        creator.avatar_url = scraped_data.get("avatar_url", creator.avatar_url)
        creator.profile_url = scraped_data.get("profile_url", creator.profile_url)
        creator.follower_count = scraped_data.get("follower_count", creator.follower_count)
        creator.niche = scraped_data.get("niche", creator.niche)
        creator.email_public = scraped_data.get("email_public", creator.email_public)
        creator.website = scraped_data.get("website", creator.website)
    else:
        creator = Creator(
            handle=scraped_data.get("handle", handle),
            platform=platform,
            display_name=scraped_data.get("display_name", handle),
            bio=scraped_data.get("bio"),
            profile_url=scraped_data.get("profile_url"),
            avatar_url=scraped_data.get("avatar_url"),
            follower_count=scraped_data.get("follower_count", 0),
            niche=scraped_data.get("niche", []),
            website=scraped_data.get("website"),
            email_public=scraped_data.get("email_public"),
            status="discovered" # maps to pending
        )
        db.add(creator)

    db.commit()
    db.refresh(creator)

    # Save/update platform-specific extension tables
    if platform == "youtube":
        yt = db.query(YoutubeLead).filter(YoutubeLead.id == creator.id).first()
        if not yt:
            yt = YoutubeLead(id=creator.id)
            db.add(yt)
        yt.channel_id = scraped_data.get("channel_id")
        yt.video_count = scraped_data.get("video_count", 0)
        yt.total_views = scraped_data.get("total_views", 0)
        yt.subscriber_count = scraped_data.get("follower_count", 0)
        yt.engagement_rate = scraped_data.get("engagement_rate", 0.0)

    elif platform == "instagram":
        ig = db.query(InstagramLead).filter(InstagramLead.id == creator.id).first()
        if not ig:
            ig = InstagramLead(id=creator.id)
            db.add(ig)
        ig.username = creator.handle.replace("@", "")
        ig.biography = scraped_data.get("bio")
        ig.follower_count = scraped_data.get("follower_count", 0)
        ig.engagement_rate = scraped_data.get("engagement_rate", 0.0)

    elif platform == "tiktok":
        tt = db.query(TiktokLead).filter(TiktokLead.id == creator.id).first()
        if not tt:
            tt = TiktokLead(id=creator.id)
            db.add(tt)
        tt.follower_count = scraped_data.get("follower_count", 0)
        tt.video_count = scraped_data.get("video_count", 0)

    elif platform == "twitter":
        tw = db.query(TwitterLead).filter(TwitterLead.id == creator.id).first()
        if not tw:
            tw = TwitterLead(id=creator.id)
            db.add(tw)
        tw.follower_count = scraped_data.get("follower_count", 0)
        tw.tweet_count = scraped_data.get("tweet_count", 0)

    db.commit()

    # Return structured creator details
    return {
        "id": creator.id,
        "handle": creator.handle,
        "platform": creator.platform,
        "display_name": creator.display_name,
        "bio": creator.bio,
        "avatar_url": creator.avatar_url,
        "follower_count": creator.follower_count,
        "niche": creator.niche,
        "email": creator.email_public,
        "status": creator.status
    }


@router.get("/creators")
def list_creators_by_platform(platform: Optional[str] = None, db: Session = Depends(get_db)):
    """
    List all scraped creator leads for a given platform.
    If platform is None, return all creators.
    """
    query = db.query(Creator)
    if platform:
        query = query.filter(Creator.platform == platform.lower())
    
    creators = query.order_by(Creator.created_at.desc()).all()
    results = []
    
    for creator in creators:
        # Get outreach status
        outreach_messages = db.query(OutreachMessage).filter(OutreachMessage.creator_id == creator.id).all()
        if creator.discovery_notes:
            outreach_status = creator.discovery_notes
        else:
            outreach_status = "pending" if not outreach_messages else "emailed"

        creator_dict = {
            "id": creator.id,
            "handle": creator.handle,
            "platform": creator.platform,
            "display_name": creator.display_name,
            "bio": creator.bio,
            "avatar_url": creator.avatar_url,
            "follower_count": creator.follower_count,
            "niche": creator.niche,
            "email": creator.email_public,
            "status": creator.status,
            "outreach_status": outreach_status
        }
        
        # Add platform-specific details if loaded
        if creator.platform == "youtube" and creator.youtube_lead:
            creator_dict["platform_details"] = {
                "video_count": creator.youtube_lead.video_count,
                "total_views": creator.youtube_lead.total_views,
                "engagement_rate": creator.youtube_lead.engagement_rate
            }
        elif creator.platform == "instagram" and creator.instagram_lead:
            creator_dict["platform_details"] = {
                "biography": creator.instagram_lead.biography,
                "engagement_rate": creator.instagram_lead.engagement_rate
            }
        elif creator.platform == "tiktok" and creator.tiktok_lead:
            creator_dict["platform_details"] = {
                "video_count": creator.tiktok_lead.video_count
            }
        elif creator.platform == "twitter" and creator.twitter_lead:
            creator_dict["platform_details"] = {
                "tweet_count": creator.twitter_lead.tweet_count
            }
            
        results.append(creator_dict)
        
    return results


@router.delete("/creators/{creator_id}")
def delete_creator(creator_id: str, db: Session = Depends(get_db)):
    """
    Delete a creator lead and all its cascaded relations.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    # In PostgreSQL we must clean up associated threads, outreach_logs first to prevent constraint violations
    # Check if there is a thread
    thread = db.query(Thread).filter(Thread.creator_id == creator_id).first()
    if thread:
        db.delete(thread)
    
    # Delete outreach logs
    db.query(OutreachMessage).filter(OutreachMessage.creator_id == creator_id).delete()
    
    db.delete(creator)
    db.commit()
    return {"success": True, "message": "Creator deleted successfully"}


@router.get("/creators/{creator_id}/ideas")
def get_or_generate_ideas(creator_id: str, db: Session = Depends(get_db)):
    """
    Get existing product ideas or generate 3-5 new ones.
    """
    try:
        ideas = get_creator_ideas(db, creator_id)
        return [
            {
                "id": idea.id,
                "product_name": idea.product_name,
                "product_category": idea.product_category,
                "tagline": idea.tagline,
                "description": idea.description,
                "target_audience": idea.target_audience,
                "revenue_model": idea.revenue_model,
                "revenue_potential": idea.revenue_potential,
                "rationale": idea.rationale,
                "confidence_score": idea.confidence_score,
                "status": idea.status
            }
            for idea in ideas
        ]
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error retrieving ideas: {e}")


@router.post("/creators/{creator_id}/select-idea")
def select_product_idea(creator_id: str, payload: SelectIdeaRequest, db: Session = Depends(get_db)):
    """
    Select an idea, approve it, and generate the landing page outline + scaffold.
    """
    try:
        updated_idea = generate_landing_page_outline_and_scaffold(db, creator_id, payload.idea_id)
        return {
            "id": updated_idea.id,
            "product_name": updated_idea.product_name,
            "product_category": updated_idea.product_category,
            "tagline": updated_idea.tagline,
            "description": updated_idea.description,
            "landing_page_outline": updated_idea.landing_page_outline,
            "web_app_scaffold": updated_idea.web_app_scaffold,
            "status": updated_idea.status
        }
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generating landing page and scaffold: {e}")


@router.get("/creators/{creator_id}/dashboard")
def get_creator_dashboard(creator_id: str, db: Session = Depends(get_db)):
    """
    Get aggregated dashboard information for a creator.
    """
    try:
        return get_dashboard_data(db, creator_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error loading dashboard: {e}")


@router.post("/creators/{creator_id}/outreach/generate")
def get_outreach_email_draft(creator_id: str, tone: str = "friendly", db: Session = Depends(get_db)):
    """
    Generate outreach email subject and body draft.
    """
    try:
        return generate_outreach_email(db, creator_id, tone)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generating email: {e}")


@router.post("/creators/{creator_id}/outreach/send")
def trigger_outreach_email(creator_id: str, payload: SendEmailRequest, db: Session = Depends(get_db)):
    """
    Send outreach email via Resend and update outreach thread & logs.
    """
    try:
        msg = send_outreach_email(db, creator_id, payload.subject, payload.body)
        return {
            "message_id": msg.id,
            "status": msg.status,
            "error": msg.send_error
        }
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error sending outreach: {e}")


# ── STEP 1: Niche Discovery Pipeline ─────────────────────────────────────────

@router.post("/pipeline/discover")
def run_niche_discovery_pipeline(
    payload: NicheDiscoveryRequest,
    db: Session = Depends(get_db),
):
    """
    FULL PIPELINE: keyword → YouTube search → Apify email scrape → AI ideas → outreach.
    This is the admin trigger for the entire automated workflow.
    """
    results = {"run_id": None, "step1_discovered": [], "step2_ideas": [], "step3_outreach": [], "errors": []}

    # Step 1: Discover (tracked)
    try:
        pipe_result = discover_creators_by_niche(db, payload.keyword, payload.max_results)
        results["run_id"] = pipe_result.get("run_id")
        results["step1_discovered"] = pipe_result.get("creators", [])
        results["errors"].extend(pipe_result.get("errors", []))
    except Exception as e:
        results["errors"].append(f"Step 1 (discovery): {e}")
        return results

    creators = results["step1_discovered"]
    if not creators:
        results["errors"].append("No creators found")
        return results

    run_id = results["run_id"]

    # Step 2: AI ideas (tracked)
    if payload.auto_generate_ideas:
        step = PipelineStep(run_id=run_id, step_name="ai_ideas", status="running")
        db.add(step)
        db.commit()
        ideas_count = 0
        for c in creators:
            try:
                ideas = get_creator_ideas(db, c["id"])
                results["step2_ideas"].append({"creator": c["display_name"], "ideas": [i.product_name for i in ideas]})
                ideas_count += len(ideas)
            except Exception as e:
                results["errors"].append(f"Ideas for {c['display_name']}: {e}")
        step.status = "completed"
        step.detail = {"total_ideas": ideas_count}
        from datetime import datetime
        step.completed_at = datetime.utcnow()
        # Update run
        run = db.get(PipelineRun, run_id)
        if run:
            run.ideas_generated = ideas_count
        db.commit()

    # Step 3: Outreach (tracked)
    if payload.auto_send_outreach:
        step = PipelineStep(run_id=run_id, step_name="outreach_send", status="running")
        db.add(step)
        db.commit()
        sent_count = 0
        for c in creators:
            if not c.get("email"):
                continue
            try:
                draft = generate_outreach_email(db, c["id"], "friendly")
                msg = send_outreach_email(db, c["id"], draft["subject"], draft["body"])
                track_email_sent(db, run_id, c["id"], c["display_name"], c["email"], draft["subject"], msg.status, error=msg.send_error)
                results["step3_outreach"].append({"creator": c["display_name"], "email": c["email"], "status": msg.status})
                if msg.status == "sent":
                    sent_count += 1
            except Exception as e:
                results["errors"].append(f"Outreach {c['display_name']}: {e}")
        step.status = "completed"
        step.detail = {"emails_sent": sent_count}
        from datetime import datetime
        step.completed_at = datetime.utcnow()
        run = db.get(PipelineRun, run_id)
        if run:
            run.emails_sent = sent_count
        db.commit()

    return results


@router.post("/outreach/drip")
def trigger_drip_sequences(db: Session = Depends(get_db)):
    """
    Run drip processor to advance outreach follow-ups for open threads.
    """
    try:
        sent_count = process_drip_sequences(db)
        return {"success": True, "sent_count": sent_count}
    except Exception as e:
        raise HTTPException(500, f"Drip processor failed: {e}")
