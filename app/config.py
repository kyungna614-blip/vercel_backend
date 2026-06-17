import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if present (no external deps needed)
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

class Settings:
    APP_NAME: str = "Creator Forge Internal Ops"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Database — Supabase Postgres in production, SQLite locally
    _raw_db = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/creator_forge.db")
    # SQLAlchemy requires "postgresql://" not "postgres://"
    DATABASE_URL: str = _raw_db.replace("postgres://", "postgresql://", 1) if _raw_db.startswith("postgres://") else _raw_db

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # Safety Controls
    DAILY_SEND_LIMIT_DEFAULT: int = int(os.getenv("DAILY_SEND_LIMIT", "10"))
    AUTO_SEND_ENABLED: bool = False   # Never auto-send; always require human approval
    MIN_FOLLOWERS_THRESHOLD: int = 100_000
    MIN_ENGAGEMENT_SCORE: float = 3.0  # minimum quality score (0-10)

    # AI
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "groq")  # 'groq' or 'anthropic'

    # Email / Outreach
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "")
    FROM_NAME: str = os.getenv("FROM_NAME", "Creator Forge Team").strip('"')

    # SMTP (Gmail)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")

    # Integration stubs
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
    INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    TIKTOK_API_KEY: str = os.getenv("TIKTOK_API_KEY", "")

    # Apify — enables accurate scraping for Instagram & TikTok
    APIFY_API_KEY: str = os.getenv("APIFY_API_KEY", "")

    # Frontend URL (used in outreach email links)
    # VERCEL_URL on the backend points to the backend domain — NOT the frontend.
    # Always default to the real frontend deployment.
    FRONTEND_URL: str = os.getenv(
        "FRONTEND_URL",
        "https://vercel-frontend-cyan-iota.vercel.app"
    )


settings = Settings()
