import sys
import os

# Ensure the backend directory is in the path
sys.path.append(os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.creator import Creator
from app.models.outreach import OutreachMessage, Thread
from app.services.scraper import scrape_profile
from app.services.ideas import get_creator_ideas, generate_landing_page_outline_and_scaffold
from app.services.outreach import generate_outreach_email, send_outreach_email, process_drip_sequences
from app.services.dashboard import get_dashboard_data

def test_pipeline():
    db = SessionLocal()
    try:
        print("=== 1. Starting YouTube Scraper Test ===")
        creator_data = scrape_profile("youtube", "@techworldwithnana")
        if "error" in creator_data:
            print(f"Scraper error: {creator_data['error']}")
            return
        
        print(f"Scrape succeeded: handle={creator_data['handle']}, followers={creator_data['follower_count']}")
        
        # Save to database
        creator = Creator(
            handle=creator_data["handle"],
            platform="youtube",
            display_name=creator_data["display_name"],
            bio=creator_data["bio"],
            avatar_url=creator_data["avatar_url"],
            follower_count=creator_data["follower_count"],
            niche=creator_data["niche"],
            email_public=creator_data["email_public"] or "test-dev-creator@example.com",
            status="discovered"
        )
        db.add(creator)
        db.commit()
        db.refresh(creator)
        print(f"Saved creator to DB with ID: {creator.id}")

        print("\n=== 2. Starting Product Idea Generator Test ===")
        ideas = get_creator_ideas(db, creator.id)
        print(f"Generated {len(ideas)} product ideas:")
        for idx, idea in enumerate(ideas):
            print(f" - Idea {idx+1}: {idea.product_name} ({idea.product_category}) - {idea.tagline}")

        print("\n=== 3. Starting Idea Selection & Scaffold Generation Test ===")
        selected_idea = ideas[0]
        updated_idea = generate_landing_page_outline_and_scaffold(db, creator.id, selected_idea.id)
        print("Scaffold generation succeeded!")
        print("Landing Page outline theme:", updated_idea.landing_page_outline.get("theme"))
        print("Database tables in scaffold:", [t.get("table_name") for t in updated_idea.web_app_scaffold.get("schema")])

        print("\n=== 4. Starting Outreach Drafting & Delivery Test ===")
        draft = generate_outreach_email(db, creator.id)
        print("Generated email draft:")
        print(f" - Subject: {draft['subject']}")
        print(f" - Body preview: {draft['body'][:100]}...")

        print("Sending outreach email...")
        msg = send_outreach_email(db, creator.id, draft["subject"], draft["body"])
        print(f"Email delivery status: {msg.status}")

        print("\n=== 5. Starting Dashboard Aggregation Test ===")
        dashboard = get_dashboard_data(db, creator.id)
        print("Dashboard aggregation succeeded!")
        print(f" - Creator handle: {dashboard['creator']['handle']}")
        print(f" - Active product: {dashboard['selected_idea']['product_name']}")
        print(f" - Social suggestions count: {len(dashboard['marketing_suggestions']['launch_calendar'])}")

        print("\n=== 6. Clean up Test Record ===")
        db.query(Thread).filter(Thread.creator_id == creator.id).delete()
        db.query(OutreachMessage).filter(OutreachMessage.creator_id == creator.id).delete()
        db.query(Creator).filter(Creator.id == creator.id).delete()
        db.commit()
        print("Cleaned up test records from database.")
        print("PIPELINE TEST PASSED SUCCESSFULLY!")

    except Exception as e:
        print(f"PIPELINE TEST FAILED: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_pipeline()
