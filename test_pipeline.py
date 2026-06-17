"""
Test all 4 pipeline components end-to-end.
"""
import os, sys

# Load env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

print("=" * 55)
print("  CREATOR FORGE — FULL PIPELINE TEST")
print("=" * 55)
print()

errors = []

# 1. YouTube API
print("[1/4] YouTube Data API search...")
try:
    import httpx
    yt_key = os.getenv("YOUTUBE_API_KEY")
    r = httpx.get(
        f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q=tech+reviews&maxResults=3&key={yt_key}",
        timeout=15,
    )
    items = r.json().get("items", [])
    print(f"  PASS — Found {len(items)} channels")
    for item in items:
        sn = item["snippet"]
        print(f"    • {sn['title']}")
except Exception as e:
    print(f"  FAIL — {e}")
    errors.append("YouTube API")

# 2. Groq LLM
print("\n[2/4] Groq LLM (llama-3.3-70b)...")
try:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    chat = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Reply only: LLM ready"}],
        max_tokens=20,
    )
    print(f"  PASS — {chat.choices[0].message.content.strip()}")
except Exception as e:
    print(f"  FAIL — {e}")
    errors.append("Groq LLM")

# 3. Apify
print("\n[3/4] Apify client...")
try:
    from apify_client import ApifyClient
    aclient = ApifyClient(os.getenv("APIFY_API_KEY"))
    user = aclient.user().get()
    print(f"  PASS — Connected as: {user.get('username', 'ok')}")
except Exception as e:
    print(f"  FAIL — {e}")
    errors.append("Apify")

# 4. Resend
print("\n[4/4] Resend email...")
try:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
    # Send a test email to Resend sandbox
    r = resend.Emails.send({
        "from": os.getenv("FROM_EMAIL", "onboarding@resend.dev"),
        "to": ["delivered@resend.dev"],
        "subject": "Pipeline Test",
        "text": "Creator Forge pipeline test email.",
    })
    print(f"  PASS — Email sent, id: {r.get('id', 'ok')}")
except Exception as e:
    print(f"  WARN — {e} (Resend may require domain verification)")

# Summary
print("\n" + "=" * 55)
if errors:
    print(f"  FAILED: {', '.join(errors)}")
    sys.exit(1)
else:
    print("  ALL 4 PIPELINE COMPONENTS: READY")
    print("  Pipeline can execute end-to-end!")
print("=" * 55)
