from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.routers import (
    creators, discovery, outreach, campaigns, decks, suppression, analytics, audit, cofounder, automation
)
from app.routers import admin as admin_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Creator Forge internal ops pipeline",
)

# -- CORS -- allow frontend (dev + production Vercel)
_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:5173",
]
# Add production frontend URL from env
if settings.FRONTEND_URL and settings.FRONTEND_URL not in _cors_origins:
    _cors_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent


# -- Database init
@app.on_event("startup")
def startup():
    init_db()


# -- API Routers
app.include_router(creators.router)
app.include_router(discovery.router)
app.include_router(outreach.router)
app.include_router(campaigns.router)
app.include_router(decks.router)
app.include_router(suppression.router)
app.include_router(analytics.router)
app.include_router(audit.router)
app.include_router(cofounder.router)
app.include_router(admin_router.router)
app.include_router(automation.router)


# -- Settings API
@app.get("/api/settings")
def get_settings():
    def mask(v):
        return ("****" + v[-4:]) if v and len(v) > 4 else ("set" if v else "")
    return {
        "anthropic_api_key":  mask(settings.ANTHROPIC_API_KEY),
        "groq_api_key":       mask(settings.GROQ_API_KEY),
        "apify_api_key":      mask(settings.APIFY_API_KEY),
        "resend_api_key":     mask(settings.RESEND_API_KEY),
        "youtube_api_key":    mask(settings.YOUTUBE_API_KEY),
        "smtp_user":          settings.SMTP_USER,
        "smtp_configured":    bool(settings.SMTP_USER and settings.SMTP_PASS),
        "from_email":         settings.FROM_EMAIL,
        "from_name":          settings.FROM_NAME,
        "ai_model":           settings.AI_MODEL,
        "ai_provider":        settings.AI_PROVIDER,
        "ai_configured":      bool(settings.GROQ_API_KEY or settings.ANTHROPIC_API_KEY),
    }


# -- Avatar proxy (bypasses browser CORS on yt3.ggpht.com etc.)
@app.get("/api/proxy/avatar")
def proxy_avatar(url: str):
    import httpx
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.youtube.com/",
    }
    try:
        r = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception:
        return Response(status_code=404)


# -- Health
@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
