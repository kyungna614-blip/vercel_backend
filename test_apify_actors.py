"""Test which Apify actors work for YouTube email scraping."""
import os

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

import httpx
from apify_client import ApifyClient

APIFY_KEY = os.getenv("APIFY_API_KEY")
TEST_CHANNEL_URL = "https://www.youtube.com/channel/UCsBjURrPoezykLs9EqgamOA"
TEST_CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"

client = ApifyClient(APIFY_KEY)

# ── Test 1: dataovercoffee/youtube-channel-business-email-scraper ────────
print("=" * 60)
print("TEST 1: dataovercoffee/youtube-channel-business-email-scraper")
print("=" * 60)
try:
    run = client.actor("dataovercoffee/youtube-channel-business-email-scraper").call(
        run_input={"channels": [TEST_CHANNEL_URL]},
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"  SUCCESS - {len(items)} items returned")
    for item in items:
        print(f"  -> email: {item.get('email', 'N/A')}")
        print(f"  -> keys: {list(item.keys())}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

# ── Test 2: bhansalisoft/youtube-email-scraper (the failing one) ──────────
print()
print("=" * 60)
print("TEST 2: bhansalisoft/youtube-email-scraper (current - PAID)")
print("=" * 60)
try:
    run = client.actor("bhansalisoft/youtube-email-scraper").call(
        run_input={"Keyword": "tech reviews", "Limit": "1", "proxySettings": {"useApifyProxy": True}},
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"  SUCCESS - {len(items)} items returned")
    for item in items:
        print(f"  -> {item}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")

# ── Test 3: Direct YouTube About page scrape (no Apify) ──────────────────
print()
print("=" * 60)
print("TEST 3: Direct bio email extraction (YouTube API - FREE)")
print("=" * 60)
import re
YT_KEY = os.getenv("YOUTUBE_API_KEY")
try:
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,brandingSettings&id={TEST_CHANNEL_ID}&key={YT_KEY}"
    r = httpx.get(url, timeout=10)
    data = r.json()
    if data.get("items"):
        ch = data["items"][0]
        bio = ch["snippet"].get("description", "")
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", bio)
        print(f"  Bio length: {len(bio)} chars")
        print(f"  Emails found in bio: {emails}")
        print(f"  Channel: {ch['snippet']['title']}")
    else:
        print("  No channel data returned")
except Exception as e:
    print(f"  FAILED: {e}")

print()
print("DONE")
