import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class Creator(Base):
    __tablename__ = "creators"

    id = Column(String, primary_key=True, default=_uuid)
    handle = Column(String, nullable=False, index=True)
    platform = Column(
        SAEnum("instagram", "youtube", "tiktok", "twitter", "linkedin", "podcast", name="platform_enum"),
        nullable=False,
    )
    display_name = Column(String)
    bio = Column(Text)
    profile_url = Column(String)
    avatar_url = Column(String)
    follower_count = Column(Integer, default=0)
    niche = Column(JSON, default=list)          # list of niche tags
    location = Column(String)
    website = Column(String)
    email_public = Column(String)               # publicly listed email only
    status = Column(
        SAEnum(
            "discovered", "qualified", "disqualified",
            "in_review", "approved", "rejected", "suppressed",
            name="creator_status_enum",
        ),
        default="discovered",
        index=True,
    )
    discovery_source = Column(String)           # how we found them
    discovery_notes = Column(Text)
    engagement_score = Column(Float)            # 0-10 computed quality score
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    # relationships
    metrics_snapshots = relationship("MetricsSnapshot", back_populates="creator", cascade="all, delete-orphan")
    content_samples = relationship("ContentSample", back_populates="creator", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="creator", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="creator", cascade="all, delete-orphan")
    product_recommendations = relationship("ProductRecommendation", back_populates="creator", cascade="all, delete-orphan")
    decks = relationship("Deck", back_populates="creator", cascade="all, delete-orphan")
    outreach_messages = relationship("OutreachMessage", back_populates="creator")
    threads = relationship("Thread", back_populates="creator")
    suppression_entries = relationship("SuppressionList", back_populates="creator")

    # platform-specific extension tables
    youtube_lead = relationship("YoutubeLead", back_populates="creator", uselist=False, cascade="all, delete-orphan")
    instagram_lead = relationship("InstagramLead", back_populates="creator", uselist=False, cascade="all, delete-orphan")
    tiktok_lead = relationship("TiktokLead", back_populates="creator", uselist=False, cascade="all, delete-orphan")
    twitter_lead = relationship("TwitterLead", back_populates="creator", uselist=False, cascade="all, delete-orphan")



class MetricsSnapshot(Base):
    __tablename__ = "metrics_snapshots"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    followers = Column(Integer, default=0)
    following = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    avg_likes = Column(Float, default=0.0)
    avg_comments = Column(Float, default=0.0)
    avg_shares = Column(Float, default=0.0)
    avg_views = Column(Float, default=0.0)
    engagement_rate = Column(Float, default=0.0)      # (likes+comments) / followers
    engagement_quality_score = Column(Float, default=0.0)  # 0-10 adjusted score
    growth_rate_30d = Column(Float, default=0.0)      # % change over 30 days
    snapshot_date = Column(DateTime, default=_now)

    creator = relationship("Creator", back_populates="metrics_snapshots")


class ContentSample(Base):
    __tablename__ = "content_samples"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    platform = Column(String)
    content_url = Column(String)
    content_type = Column(
        SAEnum("post", "video", "reel", "story", "tweet", "short", name="content_type_enum"),
        default="post",
    )
    caption = Column(Text)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    views = Column(Integer, default=0)
    top_comments = Column(JSON, default=list)   # list of comment strings
    sentiment_score = Column(Float)             # -1 to 1
    topics = Column(JSON, default=list)         # extracted topics/themes
    posted_at = Column(DateTime)
    collected_at = Column(DateTime, default=_now)

    creator = relationship("Creator", back_populates="content_samples")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    analysis_type = Column(
        SAEnum("engagement", "audience_demand", "brand_fit", "overall", name="analysis_type_enum"),
        default="overall",
    )
    engagement_quality_score = Column(Float)    # 0-10
    audience_demand_signals = Column(JSON)       # dict of demand signals
    content_themes = Column(JSON, default=list)
    brand_safety_score = Column(Float)          # 0-10
    recommended_niches = Column(JSON, default=list)
    audience_pain_points = Column(JSON, default=list)
    summary = Column(Text)
    raw_output = Column(Text)                   # full AI response
    model_used = Column(String)
    analyzed_at = Column(DateTime, default=_now)

    creator = relationship("Creator", back_populates="analyses")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    contact_type = Column(
        SAEnum(
            "email", "agency", "management", "pr_firm",
            "business_inquiry_form", "social_dm", name="contact_type_enum",
        ),
        nullable=False,
    )
    value = Column(String, nullable=False)       # email address or URL
    source = Column(String)                      # WHERE we found it (bio, linktree, etc.)
    is_public = Column(Boolean, default=True)    # must always be True — no private scraping
    is_verified = Column(Boolean, default=False)
    is_valid = Column(Boolean, default=True)
    validation_notes = Column(Text)
    is_suppressed = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=_now)
    last_verified_at = Column(DateTime)

    creator = relationship("Creator", back_populates="contacts")
    outreach_messages = relationship("OutreachMessage", back_populates="contact")


class ProductRecommendation(Base):
    __tablename__ = "product_ideas"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    product_name = Column(String, nullable=False)
    product_category = Column(String)
    tagline = Column(String)
    description = Column(Text)
    target_audience = Column(Text)
    revenue_model = Column(String)
    revenue_potential = Column(String)          # e.g. "$500k-$2M ARR"
    rationale = Column(Text)
    confidence_score = Column(Float)            # 0-1
    status = Column(
        SAEnum("draft", "approved", "rejected", name="product_status_enum"),
        default="draft",
    )
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=_now)

    landing_page_outline = Column(JSON, nullable=True)
    web_app_scaffold = Column(JSON, nullable=True)

    creator = relationship("Creator", back_populates="product_recommendations")
    decks = relationship("Deck", back_populates="product_recommendation")


class Deck(Base):
    __tablename__ = "decks"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id"), nullable=False, index=True)
    product_recommendation_id = Column(String, ForeignKey("product_ideas.id"))
    title = Column(String)
    slides = Column(JSON, default=list)          # list of {title, body, notes, type}
    version = Column(Integer, default=1)
    status = Column(
        SAEnum("draft", "finalized", "sent", name="deck_status_enum"),
        default="draft",
    )
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("Creator", back_populates="decks")
    product_recommendation = relationship("ProductRecommendation", back_populates="decks")
    outreach_messages = relationship("OutreachMessage", back_populates="deck")


class YoutubeLead(Base):
    __tablename__ = "youtube_leads"

    id = Column(String, ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True)
    channel_id = Column(String)
    video_count = Column(Integer, default=0)
    total_views = Column(Integer, default=0)
    subscriber_count = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("Creator", back_populates="youtube_lead")


class InstagramLead(Base):
    __tablename__ = "instagram_leads"

    id = Column(String, ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True)
    username = Column(String)
    biography = Column(Text)
    follower_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("Creator", back_populates="instagram_lead")


class TiktokLead(Base):
    __tablename__ = "tiktok_leads"

    id = Column(String, ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True)
    sec_uid = Column(String)
    follower_count = Column(Integer, default=0)
    heart_count = Column(Integer, default=0)
    video_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("Creator", back_populates="tiktok_lead")


class TwitterLead(Base):
    __tablename__ = "twitter_leads"

    id = Column(String, ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True)
    twitter_id = Column(String)
    follower_count = Column(Integer, default=0)
    tweet_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("Creator", back_populates="twitter_lead")

