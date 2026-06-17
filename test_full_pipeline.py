# -*- coding: utf-8 -*-
"""
FULL END-TO-END PIPELINE TEST - ASCII only output
"""
import os, sys

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_db, SessionLocal
from app.services.pipeline import discover_creators_by_niche
from app.services.ideas import get_creator_ideas, generate_landing_page_outline_and_scaffold
from app.services.outreach import generate_outreach_email, send_outreach_email
from app.services.dashboard import get_dashboard_data

init_db()
db = SessionLocal()

KEYWORD = "tech reviews"

print("=" * 60)
print("  CREATOR FORGE - FULL PIPELINE EXECUTION")
print("  Keyword: '%s'" % KEYWORD)
print("=" * 60)

# STEP 1
print("\n>> STEP 1: YouTube Discovery + Apify Email Scrape")
print("-" * 50)
creators = []
try:
    creators = discover_creators_by_niche(db, KEYWORD, max_results=3)
    print("  OK - Discovered %d creators" % len(creators))
    for c in creators:
        em = c.get("email") or "no email"
        print("    - %s -- %s subs -- %s" % (c["display_name"], "{:,}".format(c["followers"]), em))
except Exception as e:
    print("  FAIL: %s" % e)

if not creators:
    print("\n  No creators found. Exiting.")
    db.close()
    sys.exit(1)

test_creator = creators[0]
creator_id = test_creator["id"]
print("\n  Using: %s (id=%s)" % (test_creator["display_name"], creator_id))

# STEP 2
print("\n>> STEP 2: AI Product Idea Generation (Groq LLM)")
print("-" * 50)
ideas = []
try:
    ideas = get_creator_ideas(db, creator_id)
    print("  OK - Generated %d product ideas:" % len(ideas))
    for idea in ideas:
        print("    - %s [%s] -- %s" % (idea.product_name, idea.product_category, idea.revenue_potential))
except Exception as e:
    print("  FAIL: %s" % e)

# STEP 3
print("\n>> STEP 3: AI Outreach Email + Send via Resend")
print("-" * 50)
try:
    draft = generate_outreach_email(db, creator_id, "friendly")
    print("  OK - Subject: %s" % draft["subject"])
    print("  OK - Body preview: %s..." % draft["body"][:120])
    msg = send_outreach_email(db, creator_id, draft["subject"], draft["body"])
    print("  OK - Email status: %s" % msg.status)
    if msg.send_error:
        print("    Note: %s" % msg.send_error[:100])
except Exception as e:
    print("  FAIL: %s" % e)

# STEP 4
print("\n>> STEP 4: Select Idea + Generate Landing Page")
print("-" * 50)
if ideas:
    try:
        selected = ideas[0]
        rec = generate_landing_page_outline_and_scaffold(db, creator_id, selected.id)
        lp = rec.landing_page_outline or {}
        sc = rec.web_app_scaffold or {}
        sections = lp.get("sections", [])
        endpoints = sc.get("endpoints", [])
        print("  OK - Landing page: %d sections" % len(sections))
        print("  OK - API scaffold: %d endpoints" % len(endpoints))
        for s in sections:
            print("    - [%s] %s" % (s.get("type", "?"), s.get("title", "Untitled")))
    except Exception as e:
        print("  FAIL: %s" % e)
else:
    print("  Skipped (no ideas)")

# STEP 5
print("\n>> STEP 5: Creator Dashboard + AI Marketing Suggestions")
print("-" * 50)
try:
    dashboard = get_dashboard_data(db, creator_id)
    cr = dashboard.get("creator", {})
    sel = dashboard.get("selected_idea")
    mktg = dashboard.get("marketing_suggestions")
    msgs = dashboard.get("outreach_messages", [])
    print("  OK - Creator: %s -- status: %s" % (cr.get("display_name"), cr.get("outreach_status")))
    if sel:
        print("  OK - Active product: %s" % sel.get("product_name"))
    print("  OK - Outreach emails: %d" % len(msgs))
    if mktg:
        le = mktg.get("launch_email", {})
        print("  OK - Launch email subject: %s" % le.get("subject", "N/A"))
        tp = str(mktg.get("teaser_post", ""))[:80]
        print("  OK - Teaser post: %s..." % tp)
        cal = mktg.get("launch_calendar", [])
        print("  OK - 7-day calendar: %d days planned" % len(cal))
except Exception as e:
    print("  FAIL: %s" % e)

db.close()

print("\n" + "=" * 60)
print("  PIPELINE COMPLETE - ALL 5 STEPS EXECUTED")
print("=" * 60)
