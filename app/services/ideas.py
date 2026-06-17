"""
Ideas service implementation.
Handles scanning a creator's profile, generating 3-5 tailored product ideas,
and drafting a full landing page outline + web app scaffold when an idea is selected.
"""
from typing import List, Dict, Any
import json
import re

from sqlalchemy.orm import Session
from app.config import settings
from app.models.creator import Creator, ProductRecommendation
from app.services.llm import llm_generate_json


def get_creator_ideas(db: Session, creator_id: str) -> List[ProductRecommendation]:
    """
    Fetch existing product ideas for a creator.
    If none exist, generate 3-5 new product ideas and save them.
    """
    ideas = db.query(ProductRecommendation).filter(ProductRecommendation.creator_id == creator_id).all()
    if ideas:
        return ideas

    # If no ideas, generate them
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    niche_str = ", ".join(creator.niche or ["Content Creation"])
    niche_lower = niche_str.lower()

    # Define prompts for Claude
    prompt = f"""You are a startup incubator director and product strategist.
Generate 4 tailored digital/physical product ideas for the following creator.

Creator:
- Name: {creator.display_name}
- Handle: {creator.handle}
- Niche: {niche_str}
- Bio: {creator.bio or 'N/A'}
- Audience Count: {creator.follower_count:,}

Requirements:
- Recommendations should be highly relevant to their niche.
- Categories can be: 'course', 'community', 'app', 'physical_product', 'saas', 'coaching', 'newsletter', 'other'.
- Generate realistic revenue potential and a solid, evidence-based rationale.

Return ONLY a JSON array of exactly 4 elements:
[
  {{
    "product_name": "Product Name",
    "product_category": "app|saas|course|...",
    "tagline": "A hooky tagline",
    "description": "2-3 sentences explaining the product.",
    "target_audience": "Who in their audience buys this.",
    "revenue_model": "Subscription / One-time / etc.",
    "revenue_potential": "$100k-$300k ARR",
    "rationale": "Why this creator fits this product.",
    "confidence_score": 0.95
  }}
]
"""

    items = []
    try:
        items = llm_generate_json(prompt, max_tokens=2500)
        if isinstance(items, dict):
            items = items.get("ideas", items.get("products", [items]))
        print(f"LLM generated {len(items)} product ideas for {creator.display_name}")
    except Exception as e:
        print(f"LLM idea generation failed, using fallback: {e}")

    # Fallback/mock ideas generator if LLM fails
    if not items:
        if "fit" in niche_lower or "gym" in niche_lower or "health" in niche_lower:
            items = [
                {
                    "product_name": "FitForge Custom Coaching",
                    "product_category": "coaching",
                    "tagline": "Personalized 1-on-1 fitness & nutrition templates tailored to your busy schedule.",
                    "description": "A high-ticket coaching program delivering customized nutrition plans and workout schedules tailored specifically to each user's biometrics.",
                    "target_audience": "Followers looking to get in shape with structured professional guidance.",
                    "revenue_model": "Monthly subscription ($149/mo)",
                    "revenue_potential": "$250k - $500k ARR",
                    "rationale": "High trust from video comments; followers frequently ask what routine the creator follows.",
                    "confidence_score": 0.92
                },
                {
                    "product_name": "SlayTheRep Fitness Tracker",
                    "product_category": "app",
                    "tagline": "Track your sets, rep ranges, and macros with community-driven gym challenges.",
                    "description": "A mobile app built for tracking strength progression and macro intake, featuring built-in community workout challenges led by the creator.",
                    "target_audience": "Gym enthusiasts who want a simple tracker and community accountability.",
                    "revenue_model": "Freemium ($9.99/mo premium tier)",
                    "revenue_potential": "$400k - $800k ARR",
                    "rationale": "Perfect fit for a tech-savvy fitness crowd. Fits the creator's emphasis on tracking metrics.",
                    "confidence_score": 0.88
                },
                {
                    "product_name": "ForgeSupps Clean Pre-Workout",
                    "product_category": "physical_product",
                    "tagline": "Organic, clean energy blend without the crash or artificial sweeteners.",
                    "description": "A premium, clean pre-workout supplement formulated using high-quality organic ingredients to enhance mental focus and physical endurance.",
                    "target_audience": "Health-conscious gym-goers seeking clean energy supplements.",
                    "revenue_model": "Direct-to-consumer e-commerce (one-time or monthly subscription)",
                    "revenue_potential": "$800k - $1.5M ARR",
                    "rationale": "Physical supplements have high margins and convert incredibly well with passionate fitness audiences.",
                    "confidence_score": 0.85
                },
                {
                    "product_name": "The Ultimate 12-Week Transformation Guide",
                    "product_category": "course",
                    "tagline": "Complete body transformation playbook with workout videos and recipe books.",
                    "description": "An interactive digital course featuring detailed video tutorials, workout databases, and a comprehensive high-protein recipe guidebook.",
                    "target_audience": "Beginners looking for an all-in-one transformation plan.",
                    "revenue_model": "One-time digital purchase ($49)",
                    "revenue_potential": "$150k - $300k ARR",
                    "rationale": "Low barrier to entry, highly scalable with zero marginal cost of delivery.",
                    "confidence_score": 0.90
                }
            ]
        elif "cook" in niche_lower or "food" in niche_lower or "kitchen" in niche_lower:
            items = [
                {
                    "product_name": "GourmetAtHome Cooking Academy",
                    "product_category": "course",
                    "tagline": "Master restaurant-quality cooking techniques from your home kitchen.",
                    "description": "Step-by-step masterclass teaching knife skills, plating aesthetics, and custom sauces to elevate everyday meals.",
                    "target_audience": "Food lovers wanting to upgrade their culinary capabilities.",
                    "revenue_model": "One-time course purchase ($99)",
                    "revenue_potential": "$200k - $400k ARR",
                    "rationale": "Leverages the creator's expert cooking tutorials and chef-level credibility.",
                    "confidence_score": 0.94
                },
                {
                    "product_name": "MealPrep PrepClub Hub",
                    "product_category": "community",
                    "tagline": "Weekly healthy meal plans, grocery shopping lists, and live cook-alongs.",
                    "description": "A premium community platform offering automated weekly shopping lists, macro breakdowns, and interactive live weekend cooking sessions.",
                    "target_audience": "Busy professionals wanting to eat healthy and cook efficiently.",
                    "revenue_model": "Monthly community access ($19/mo)",
                    "revenue_potential": "$300k - $600k ARR",
                    "rationale": "Solves the daily 'what should I eat?' pain point highlighted in community comments.",
                    "confidence_score": 0.91
                },
                {
                    "product_name": "Signature Damascus Chef Knife",
                    "product_category": "physical_product",
                    "tagline": "Handcrafted, ultra-sharp steel knife designed for precision and durability.",
                    "description": "A high-end, custom-forged Damascus steel chef knife crafted to handle all cutting, chopping, and slicing tasks.",
                    "target_audience": "Dedicated home chefs looking for premium kitchen tools.",
                    "revenue_model": "E-commerce sales ($179 per knife)",
                    "revenue_potential": "$500k - $1M ARR",
                    "rationale": "A staple tool that the creator uses in every video. Strong branding opportunity.",
                    "confidence_score": 0.87
                },
                {
                    "product_name": "SauceSecret: Organic Infused Oils",
                    "product_category": "physical_product",
                    "tagline": "A trio of handcrafted chili, garlic, and herb infused oils.",
                    "description": "Small-batch, artisanal infused oils designed to give any home-cooked meal a rich, premium flavor finish.",
                    "target_audience": "Foodies and fans looking to add quick premium flavor to dishes.",
                    "revenue_model": "DTC subscription box or single purchases",
                    "revenue_potential": "$400k - $750k ARR",
                    "rationale": "Consumables lead to high repeat purchase rates and are easy to market through cooking videos.",
                    "confidence_score": 0.83
                }
            ]
        elif "tech" in niche_lower or "dev" in niche_lower or "ai" in niche_lower or "code" in niche_lower:
            items = [
                {
                    "product_name": "CodePrompt AI Tool",
                    "product_category": "saas",
                    "tagline": "Context-aware AI prompt builder for software engineers.",
                    "description": "A desktop app that connects to your local codebase and generates optimal, contextual prompts for LLMs to write code quickly.",
                    "target_audience": "Software engineers and tech enthusiasts in the creator's audience.",
                    "revenue_model": "SaaS subscription ($12/mo)",
                    "revenue_potential": "$350k - $700k ARR",
                    "rationale": "Aligns perfectly with tech-savvy software developer followers.",
                    "confidence_score": 0.93
                },
                {
                    "product_name": "NextGen Web Academy",
                    "product_category": "course",
                    "tagline": "Master modern full-stack web development and AI API integration.",
                    "description": "A hands-on, project-based engineering program covering Next.js, FastAPI, Supabase, and LangChain.",
                    "target_audience": "Aspiring developers and career changers.",
                    "revenue_model": "One-time tuition ($199)",
                    "revenue_potential": "$400k - $800k ARR",
                    "rationale": "Fills the demand for structured learning paths that free YouTube videos don't provide.",
                    "confidence_score": 0.90
                },
                {
                    "product_name": "API-Status: Microservice Monitor",
                    "product_category": "app",
                    "tagline": "Beautiful, instant status pages and API latency alerts for indie hackers.",
                    "description": "A lightweight monitoring utility that pings developer microservices and auto-generates slick public status pages.",
                    "target_audience": "Indie developers, startup founders, and software engineers.",
                    "revenue_model": "Freemium ($19/mo standard tier)",
                    "revenue_potential": "$150k - $350k ARR",
                    "rationale": "Highly requested utility in coding and startup communities.",
                    "confidence_score": 0.85
                },
                {
                    "product_name": "The Developer's Productivity Desk Mat",
                    "product_category": "physical_product",
                    "tagline": "Premium merino wool desk mat with keyboard shortcut references.",
                    "description": "A minimalist, premium desk mat featuring customized grid lines and laser-engraved key command guides.",
                    "target_audience": "Developers and tech workers seeking desk setup aesthetics.",
                    "revenue_model": "DTC retail ($59)",
                    "revenue_potential": "$200k - $450k ARR",
                    "rationale": "Aesthetic setups are extremely popular on Instagram/YouTube; high conversion rate.",
                    "confidence_score": 0.80
                }
            ]
        else:
            items = [
                {
                    "product_name": "The Creator's Productivity Planner",
                    "product_category": "physical_product",
                    "tagline": "A paper planner designed for organizing creative workflows, goals, and habits.",
                    "description": "A beautifully bound physical planner engineered to structure creative brainstorming, track key milestones, and review daily priorities.",
                    "target_audience": "Followers interested in organization, self-improvement, and productivity.",
                    "revenue_model": "DTC sale ($35/planner)",
                    "revenue_potential": "$150k - $300k ARR",
                    "rationale": "Wide general appeal to anyone interested in organizing their creative projects.",
                    "confidence_score": 0.85
                },
                {
                    "product_name": "Creative Circle Mastermind",
                    "product_category": "community",
                    "tagline": "Exclusive monthly community calls, feedback loops, and resource sharing.",
                    "description": "An invite-only online community designed for sharing resources, hosting live masterminds, and facilitating weekly goal accountability.",
                    "target_audience": "Aspiring creators and creative hobbyists.",
                    "revenue_model": "Monthly membership ($29/mo)",
                    "revenue_potential": "$250k - $500k ARR",
                    "rationale": "Enables direct, exclusive access to the creator, which drives high customer loyalty.",
                    "confidence_score": 0.88
                },
                {
                    "product_name": "Brand-Launch Blueprint",
                    "product_category": "course",
                    "tagline": "How to scale your creative side-hustle into a full-time brand.",
                    "description": "A structured step-by-step masterclass covering personal branding, audience building, and initial monetization strategies.",
                    "target_audience": "Side-hustlers and content creators starting out.",
                    "revenue_model": "One-time purchase ($149)",
                    "revenue_potential": "$300k - $600k ARR",
                    "rationale": "Builds on the creator's proven success of scaling their own online presence.",
                    "confidence_score": 0.90
                },
                {
                    "product_name": "Aura Lightroom Presets Pack",
                    "product_category": "other",
                    "tagline": "One-click professional photo filters to elevate your photography.",
                    "description": "A collection of premium lightroom filters modeled directly after the creator's signature photography style.",
                    "target_audience": "Instagram users and amateur photographers looking for quick, high-end edits.",
                    "revenue_model": "Digital download ($25)",
                    "revenue_potential": "$100k - $200k ARR",
                    "rationale": "High margin digital product that directly answers constant questions about 'how do you edit your photos?'.",
                    "confidence_score": 0.82
                }
            ]

    # Save recommendations to database
    recs = []
    for item in items:
        rec = ProductRecommendation(
            creator_id=creator_id,
            product_name=item["product_name"],
            product_category=item["product_category"],
            tagline=item["tagline"],
            description=item["description"],
            target_audience=item["target_audience"],
            revenue_model=item["revenue_model"],
            revenue_potential=item["revenue_potential"],
            rationale=item["rationale"],
            confidence_score=float(item.get("confidence_score", 0.85)),
            status="draft"
        )
        db.add(rec)
        recs.append(rec)
    db.commit()

    for r in recs:
        db.refresh(r)

    return recs


def generate_landing_page_outline_and_scaffold(db: Session, creator_id: str, idea_id: str) -> ProductRecommendation:
    """
    Generate the landing page outline and web app scaffold for a selected product idea.
    Saves the output as JSON inside the recommendation record and sets status to 'approved'.
    """
    rec = db.get(ProductRecommendation, idea_id)
    if not rec or rec.creator_id != creator_id:
        raise ValueError("Product idea not found for this creator")

    creator = db.get(Creator, creator_id)
    niche_str = ", ".join(creator.niche or ["Content Creation"])

    prompt = f"""You are a senior UX designer and software architect.
Generate a structured landing page outline and database/endpoint scaffold for:

Product: {rec.product_name}
Tagline: {rec.tagline}
Category: {rec.product_category}
Creator: {creator.display_name} (@{creator.handle})

Format the output strictly as a single JSON object with these two fields:
{{
  "landing_page_outline": {{
    "theme": {{
      "primary_color": "hex code representing niche",
      "font_family": "Outfit or Inter or Outfit"
    }},
    "sections": [
      {{
        "id": "hero",
        "type": "hero",
        "title": "Headline copy",
        "subtitle": "Subheadline copy",
        "cta_text": "Call to action text"
      }},
      {{
        "id": "features",
        "type": "features",
        "title": "Core benefits",
        "items": [
          {{"title": "Feature 1", "description": "Details"}}
        ]
      }},
      {{
        "id": "pricing",
        "type": "pricing",
        "title": "Pricing plans",
        "tiers": [
          {{"name": "Plan Name", "price": "$XX/mo", "features": ["Feature A"]}}
        ]
      }},
      {{
        "id": "faq",
        "type": "faq",
        "title": "Frequently Asked Questions",
        "questions": [
          {{"q": "Question?", "a": "Answer."}}
        ]
      }}
    ]
  }},
  "web_app_scaffold": {{
    "schema": [
      {{
        "table_name": "table name",
        "columns": [
          "id (UUID - PRIMARY KEY)",
          "column2 (datatype)"
        ]
      }}
    ],
    "endpoints": [
      {{
        "method": "GET|POST|PUT|DELETE",
        "path": "/api/...",
        "description": "What it does",
        "request_payload": "JSON mock schema or N/A",
        "response_payload": "JSON mock response schema"
      }}
    ]
  }}
}}

Return ONLY valid JSON.
"""

    data = None
    try:
        data = llm_generate_json(prompt, max_tokens=3500)
        print(f"LLM generated landing page + scaffold for {rec.product_name}")
    except Exception as e:
        print(f"LLM landing page generation failed, using fallback: {e}")

    # Fallback/mock generator if LLM fails
    if not data:
        # Construct dynamic mock data based on the category/niche
        primary_color = "#3B82F6" # Default blue
        if "fit" in rec.product_category or "coaching" in rec.product_category:
            primary_color = "#EF4444" # Red for fitness
        elif "cook" in rec.product_category or "food" in rec.product_category:
            primary_color = "#F59E0B" # Amber for culinary
        elif "tech" in rec.product_category or "saas" in rec.product_category:
            primary_color = "#10B981" # Emerald for SaaS/tech

        data = {
            "landing_page_outline": {
                "theme": {
                    "primary_color": primary_color,
                    "font_family": "Outfit"
                },
                "sections": [
                  {
                    "id": "hero",
                    "type": "hero",
                    "title": f"The Ultimate {rec.product_name} Tailored For You",
                    "subtitle": rec.tagline,
                    "cta_text": "Join the Waitlist Now"
                  },
                  {
                    "id": "problems",
                    "type": "problem",
                    "title": "Why other solutions fail",
                    "items": [
                      {"title": "Not Personalized", "description": "Generic guides don't respect your personal body metrics, style, or code setup."},
                      {"title": "Lack of Accountability", "description": "It's easy to fall off track when you are working out or coding completely alone."}
                    ]
                  },
                  {
                    "id": "features",
                    "type": "features",
                    "title": "How it works",
                    "items": [
                      {"title": "Tailored Architecture", "description": f"Designed directly alongside {creator.display_name} to fit your exact goals."},
                      {"title": "Interactive Community Hub", "description": "Share progress, get instant support, and scale with fellow members."},
                      {"title": "Direct Feedback Loop", "description": "Weekly group calls and reviews to help keep you focused and moving forward."}
                    ]
                  },
                  {
                    "id": "pricing",
                    "type": "pricing",
                    "title": "Flexible options for every goal",
                    "tiers": [
                      {
                        "name": "Standard Access",
                        "price": "$19/mo" if "app" in rec.product_category or "community" in rec.product_category else "$49 one-time",
                        "features": [
                          "Full platform access",
                          "Standard community chat",
                          "All basic guides & resources"
                        ]
                      },
                      {
                        "name": "Pro VIP Launchpad",
                        "price": "$49/mo" if "app" in rec.product_category or "community" in rec.product_category else "$149 one-time",
                        "features": [
                          "All standard tier features",
                          "Direct 1-on-1 feedback reviews",
                          "Monthly live Q&A sessions",
                          "Exclusive launch bonuses"
                        ]
                      }
                    ]
                  },
                  {
                    "id": "faq",
                    "type": "faq",
                    "title": "Frequently Asked Questions",
                    "questions": [
                      {
                        "q": f"Is this product suitable for absolute beginners?",
                        "a": "Yes, absolutely! We structure the onboarding to customize the difficulty and pace to match your exact current experience levels."
                      },
                      {
                        "q": f"How is {creator.display_name} involved in this?",
                        "a": f"This brand was co-founded by {creator.display_name}. They design all program parameters, lead live calls, and actively shape the weekly resources."
                      },
                      {
                        "q": "What is the cancellation policy?",
                        "a": "For monthly memberships, you can cancel at any time directly through your dashboard with no questions asked. Digital guides have a 14-day refund guarantee."
                      }
                    ]
                  }
                ]
            },
            "web_app_scaffold": {
                "schema": [
                  {
                    "table_name": "users",
                    "columns": [
                      "id (UUID - PRIMARY KEY)",
                      "email (VARCHAR(255) - UNIQUE)",
                      "display_name (VARCHAR(100))",
                      "created_at (TIMESTAMPTZ)"
                    ]
                  },
                  {
                    "table_name": "subscriptions",
                    "columns": [
                      "id (UUID - PRIMARY KEY)",
                      "user_id (UUID - REFERENCES users(id))",
                      "plan_tier (VARCHAR(50))",
                      "status (VARCHAR(20))",
                      "current_period_end (TIMESTAMPTZ)"
                    ]
                  },
                  {
                    "table_name": "progress_logs",
                    "columns": [
                      "id (UUID - PRIMARY KEY)",
                      "user_id (UUID - REFERENCES users(id))",
                      "activity_type (VARCHAR(50))",
                      "completion_details (JSONB)",
                      "logged_at (TIMESTAMPTZ)"
                    ]
                  }
                ],
                "endpoints": [
                  {
                    "method": "POST",
                    "path": "/api/auth/register",
                    "description": "Create user profile and trigger welcome series",
                    "request_payload": '{"email": "user@example.com", "password": "securepassword", "name": "John Doe"}',
                    "response_payload": '{"user_id": "8fa8fb6f-bc72...", "status": "registered", "token": "JWT_TOKEN"}'
                  },
                  {
                    "method": "GET",
                    "path": "/api/dashboard/summary",
                    "description": "Retrieve active subscription status and custom workout/coding progress logs",
                    "request_payload": "N/A",
                    "response_payload": '{"subscription_active": true, "progress_percentage": 42, "next_milestone": "Week 3 Day 2"}'
                  },
                  {
                    "method": "POST",
                    "path": "/api/progress/log",
                    "description": "Log a completed daily activity milestone",
                    "request_payload": '{"activity_id": "activity_99", "completed": true, "time_spent_seconds": 1800}',
                    "response_payload": '{"success": true, "updated_progress": 45, "points_earned": 50}'
                  }
                ]
            }
        }

    # Save to the product recommendation row
    rec.landing_page_outline = data["landing_page_outline"]
    rec.web_app_scaffold = data["web_app_scaffold"]
    rec.status = "approved" # Set as approved/selected

    db.commit()
    db.refresh(rec)

    # Set creator status to approved (which represents that they have an active plan/scaffold in the MVP)
    creator.status = "approved"
    db.commit()

    return rec
