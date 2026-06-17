"""
Dashboard service implementation.
Aggregates creator profile, selected product idea, landing page outline,
web app scaffold, outreach logs, and generates AI marketing/social campaign posts.
"""
from typing import Dict, Any
import json
import re

from sqlalchemy.orm import Session
from app.config import settings
from app.models.creator import Creator, ProductRecommendation
from app.models.outreach import OutreachMessage, Thread
from app.services.llm import llm_generate_json


def get_dashboard_data(db: Session, creator_id: str) -> Dict[str, Any]:
    """
    Aggregate and return all data required for the creator's co-founder dashboard.
    Generates AI marketing suggestions for the selected product.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    # Fetch product ideas
    ideas = db.query(ProductRecommendation).filter(ProductRecommendation.creator_id == creator_id).all()
    selected_idea = next((i for i in ideas if i.status == "approved"), None)

    # Fetch outreach messages
    outreach_messages = db.query(OutreachMessage).filter(OutreachMessage.creator_id == creator_id).order_by(OutreachMessage.created_at.desc()).all()
    
    # Check thread status
    thread = db.query(Thread).filter(Thread.creator_id == creator_id).first()
    thread_status = thread.status if thread else "pending"
    if creator.discovery_notes:
        outreach_status = creator.discovery_notes # 'emailed', 'followed-up', 'replied' etc.
    else:
        outreach_status = "pending" if not outreach_messages else "emailed"

    # Compile list of messages for dashboard UI
    messages_list = []
    for msg in outreach_messages:
        messages_list.append({
            "id": msg.id,
            "subject": msg.subject,
            "body": msg.body,
            "status": msg.status,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
            "error": msg.send_error
        })

    # Prepare marketing suggestions
    marketing_suggestions = None
    if selected_idea:
        marketing_suggestions = generate_marketing_suggestions(creator, selected_idea)

    # Compile the final aggregated payload
    ideas_list = []
    for idea in ideas:
        ideas_list.append({
            "id": idea.id,
            "product_name": idea.product_name,
            "product_category": idea.product_category,
            "tagline": idea.tagline,
            "description": idea.description,
            "target_audience": idea.target_audience,
            "revenue_model": idea.revenue_model,
            "revenue_potential": idea.revenue_potential,
            "rationale": idea.rationale,
            "status": idea.status
        })

    return {
        "creator": {
            "id": creator.id,
            "handle": creator.handle,
            "display_name": creator.display_name,
            "bio": creator.bio,
            "avatar_url": creator.avatar_url,
            "follower_count": creator.follower_count,
            "niche": creator.niche,
            "email": creator.email_public,
            "status": creator.status,
            "outreach_status": outreach_status,
            "thread_status": thread_status
        },
        "ideas": ideas_list,
        "selected_idea": {
            "id": selected_idea.id,
            "product_name": selected_idea.product_name,
            "product_category": selected_idea.product_category,
            "tagline": selected_idea.tagline,
            "description": selected_idea.description,
            "landing_page_outline": selected_idea.landing_page_outline,
            "web_app_scaffold": selected_idea.web_app_scaffold
        } if selected_idea else None,
        "outreach_messages": messages_list,
        "marketing_suggestions": marketing_suggestions
    }


def generate_marketing_suggestions(creator: Creator, idea: ProductRecommendation) -> Dict[str, Any]:
    """
    Generate marketing assets (launch email, teaser post, BTS post, 7-day calendar)
    using Claude, falling back to a structured template generator if no API key is present.
    """
    prompt = f"""You are a product marketing manager.
Generate social media posts and launch materials for:

Product: {idea.product_name}
Tagline: {idea.tagline}
Creator: {creator.display_name} (@{creator.handle})

Format the output strictly as a single JSON object with these fields:
{{
  "launch_email": {{
    "subject": "Headline",
    "body": "Email body copy"
  }},
  "teaser_post": "Teaser post copy for Twitter/Instagram",
  "bts_post": "Behind-the-scenes building post copy",
  "launch_calendar": [
    {{"day": "Day 1", "action": "Tease product idea on stories", "copy": "Post caption copy"}},
    {{"day": "Day 2", "action": "Ask audience for feature feedback", "copy": "Feedback post copy"}},
    {{"day": "Day 3", "action": "Share design draft / behind the scenes", "copy": "BTS post copy"}},
    {{"day": "Day 4", "action": "Open waitlist registrations", "copy": "Waitlist copy"}},
    {{"day": "Day 5", "action": "Share waitlist milestones (e.g. 500 members)", "copy": "Milestone copy"}},
    {{"day": "Day 6", "action": "Final countdown - 24 hours to go", "copy": "Countdown copy"}},
    {{"day": "Day 7", "action": "Launch day announcement", "copy": "Launch announcement copy"}}
  ]
}}

Return ONLY valid JSON.
"""

    try:
        result = llm_generate_json(prompt, max_tokens=2500)
        if isinstance(result, dict):
            return result
    except Exception as e:
        print(f"LLM marketing suggestion generation failed, using fallback: {e}")

    # Fallback/mock marketing suggestions
    return {
        "launch_email": {
            "subject": f"I'm co-founding something new: {idea.product_name}! 🚀",
            "body": (
                f"Hey guys,\n\n"
                f"For the past few months, I've been working on a secret project to solve "
                f"one of the biggest pain points I hear from you every single day.\n\n"
                f"I'm super excited to announce that we are launching {idea.product_name}! "
                f"This is a {idea.product_category} specifically designed to {idea.tagline.lower()}.\n\n"
                f"We are opening exclusive early-access waitlist spots today. Members get a permanent "
                f"50% discount and direct access to shape the beta version.\n\n"
                f"Check it out and grab your spot here: [Link]\n\n"
                f"Can't wait to build this with you!\n\n"
                f"Best,\n"
                f"{creator.display_name}"
            )
        },
        "teaser_post": (
            f"Big news coming soon... 🤫 I've been building a custom solution to help you "
            f"{idea.tagline.lower() or 'reach your goals'}. "
            f"If you've been struggling with generic options, this is for you. "
            f"Drop a Comment and I'll DM you the early waitlist link! 👇 #launch #creatorco"
        ),
        "bts_post": (
            f"Behind the scenes of building {idea.product_name}! 🛠️ "
            f"We wanted to make sure every single feature directly addresses what you've been asking for. "
            f"Here's a sneak peek at our database schema and custom API endpoints. "
            f"What feature are you most excited to see? Let me know! 👇 #buildinpublic"
        ),
        "launch_calendar": [
            {
                "day": "Day 1",
                "action": "Tease the secret project",
                "copy": "Cooking up something secret in the lab. Can anyone guess what it is? Hint: it will help you solve your daily routine struggle. 👀"
            },
            {
                "day": "Day 2",
                "action": "Reveal the name & logo",
                "copy": "Meet FitForge/GourmetAtHome! 🚀 The logo represents strength and consistency. Building this with you, for you."
            },
            {
                "day": "Day 3",
                "action": "Share behind-the-scenes",
                "copy": "We're coding the backend dashboard today. Take a look at these endpoints! Custom-built to be lightning fast."
            },
            {
                "day": "Day 4",
                "action": "Open early waitlist registration",
                "copy": "Waitlist is OFFICIALLY OPEN! The first 100 members get a free lifetime upgrade. Link in bio! 🏃💨"
            },
            {
                "day": "Day 5",
                "action": "Celebrate waitlist milestone",
                "copy": "Over 500 signups in 24 hours?! You guys are unreal. Thank you so much for the trust. Let's make this launch legendary!"
            },
            {
                "day": "Day 6",
                "action": "Final 24 hours countdown",
                "copy": "Only 24 hours left before we go live! Early bird pricing ends tomorrow. Don't miss out on your launch discount."
            },
            {
                "day": "Day 7",
                "action": "Launch day announcement",
                "copy": "WE ARE LIVE! 🎉 {rec_name if 'rec_name' in locals() else 'The platform'} is officially open for registrations. Click the link in my bio to start your journey today!"
            }
        ]
    }
