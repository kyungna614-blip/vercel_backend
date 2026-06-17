import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Detect Vercel serverless (read-only filesystem — no SQLite)
_is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
_db_url = settings.DATABASE_URL

# On Vercel without a real DB URL, use in-memory SQLite
if _is_vercel and "sqlite" in _db_url and ":memory:" not in _db_url:
    _db_url = "sqlite:///:memory:"

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
    echo=False if _is_vercel else settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    try:
        from app.models import creator, campaign, outreach, audit  # noqa: F401
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[DB] init_db warning: {e}")
