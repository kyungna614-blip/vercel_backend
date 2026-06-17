-- Creator Forge — Supabase / PostgreSQL schema
-- Run this in your Supabase SQL editor: app.supabase.com → project → SQL Editor
-- Idempotent: safe to run multiple times

-- ── ENUM types ─────────────────────────────────────────────────────────────────
DO $$ BEGIN CREATE TYPE platform_enum AS ENUM ('instagram','youtube','tiktok','twitter','linkedin','podcast'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE creator_status_enum AS ENUM ('discovered','qualified','disqualified','in_review','approved','rejected','suppressed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE contact_type_enum AS ENUM ('email','agency','management','pr_firm','business_inquiry_form','social_dm'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE content_type_enum AS ENUM ('post','video','reel','story','tweet','short'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE analysis_type_enum AS ENUM ('engagement','audience_demand','brand_fit','overall'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE product_status_enum AS ENUM ('draft','approved','rejected'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE deck_status_enum AS ENUM ('draft','finalized','sent'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE campaign_status_enum AS ENUM ('draft','active','paused','completed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE send_method_enum AS ENUM ('email','dm','contact_form'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE message_status_enum AS ENUM ('draft','review_pending','approved','rejected','queued','sent','bounced','failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE thread_status_enum AS ENUM ('open','replied','closed','converted','lost'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE followup_status_enum AS ENUM ('draft','review_pending','approved','sent','skipped'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE reply_classification_enum AS ENUM ('interested','not_interested','more_info','out_of_office','bounced','spam','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE crm_stage_enum AS ENUM ('new','contacted','qualified','negotiating','closed_won','closed_lost'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE suppression_reason_enum AS ENUM ('opt_out','bounce','invalid','do_not_contact','complaint'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE review_decision_enum AS ENUM ('approved','rejected','needs_changes'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- ── creators ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS creators (
  id                TEXT PRIMARY KEY,
  handle            TEXT NOT NULL,
  platform          platform_enum NOT NULL,
  display_name      TEXT,
  bio               TEXT,
  profile_url       TEXT,
  avatar_url        TEXT,
  follower_count    INTEGER DEFAULT 0,
  niche             JSONB DEFAULT '[]',
  location          TEXT,
  website           TEXT,
  email_public      TEXT,
  status            creator_status_enum DEFAULT 'discovered',
  discovery_source  TEXT,
  discovery_notes   TEXT,
  engagement_score  FLOAT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_creators_handle   ON creators(handle);
CREATE INDEX IF NOT EXISTS idx_creators_status   ON creators(status);
CREATE INDEX IF NOT EXISTS idx_creators_platform ON creators(platform);


-- ── metrics_snapshots ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metrics_snapshots (
  id                        TEXT PRIMARY KEY,
  creator_id                TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  followers                 INTEGER DEFAULT 0,
  following                 INTEGER DEFAULT 0,
  posts_count               INTEGER DEFAULT 0,
  avg_likes                 FLOAT DEFAULT 0,
  avg_comments              FLOAT DEFAULT 0,
  avg_shares                FLOAT DEFAULT 0,
  avg_views                 FLOAT DEFAULT 0,
  engagement_rate           FLOAT DEFAULT 0,
  engagement_quality_score  FLOAT DEFAULT 0,
  growth_rate_30d           FLOAT DEFAULT 0,
  snapshot_date             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_metrics_creator ON metrics_snapshots(creator_id);


-- ── content_samples ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_samples (
  id              TEXT PRIMARY KEY,
  creator_id      TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  platform        TEXT,
  content_url     TEXT,
  content_type    content_type_enum DEFAULT 'post',
  caption         TEXT,
  likes           INTEGER DEFAULT 0,
  comments        INTEGER DEFAULT 0,
  shares          INTEGER DEFAULT 0,
  views           INTEGER DEFAULT 0,
  top_comments    JSONB DEFAULT '[]',
  sentiment_score FLOAT,
  topics          JSONB DEFAULT '[]',
  posted_at       TIMESTAMPTZ,
  collected_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_content_creator ON content_samples(creator_id);


-- ── analyses ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analyses (
  id                       TEXT PRIMARY KEY,
  creator_id               TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  analysis_type            analysis_type_enum DEFAULT 'overall',
  engagement_quality_score FLOAT,
  audience_demand_signals  JSONB,
  content_themes           JSONB DEFAULT '[]',
  brand_safety_score       FLOAT,
  recommended_niches       JSONB DEFAULT '[]',
  audience_pain_points     JSONB DEFAULT '[]',
  summary                  TEXT,
  raw_output               TEXT,
  model_used               TEXT,
  analyzed_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analyses_creator ON analyses(creator_id);


-- ── contacts ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
  id               TEXT PRIMARY KEY,
  creator_id       TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  contact_type     contact_type_enum NOT NULL,
  value            TEXT NOT NULL,
  source           TEXT,
  is_public        BOOLEAN DEFAULT TRUE,
  is_verified      BOOLEAN DEFAULT FALSE,
  is_valid         BOOLEAN DEFAULT TRUE,
  validation_notes TEXT,
  is_suppressed    BOOLEAN DEFAULT FALSE,
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  last_verified_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_contacts_creator ON contacts(creator_id);


-- ── product_ideas ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_ideas (
  id                TEXT PRIMARY KEY,
  creator_id        TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  product_name      TEXT NOT NULL,
  product_category  TEXT,
  tagline           TEXT,
  description       TEXT,
  target_audience   TEXT,
  revenue_model     TEXT,
  revenue_potential TEXT,
  rationale         TEXT,
  confidence_score  FLOAT,
  status            product_status_enum DEFAULT 'draft',
  reviewed_by       TEXT,
  reviewed_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ideas_creator ON product_ideas(creator_id);


-- ── decks ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decks (
  id                        TEXT PRIMARY KEY,
  creator_id                TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  product_recommendation_id TEXT REFERENCES product_ideas(id),
  title                     TEXT,
  slides                    JSONB DEFAULT '[]',
  version                   INTEGER DEFAULT 1,
  status                    deck_status_enum DEFAULT 'draft',
  created_at                TIMESTAMPTZ DEFAULT NOW(),
  updated_at                TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decks_creator ON decks(creator_id);


-- ── campaigns ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
  id                     TEXT PRIMARY KEY,
  name                   TEXT NOT NULL,
  description            TEXT,
  product_category       TEXT,
  status                 campaign_status_enum DEFAULT 'draft',
  daily_send_limit       INTEGER DEFAULT 10,
  total_sent             INTEGER DEFAULT 0,
  total_replied          INTEGER DEFAULT 0,
  total_converted        INTEGER DEFAULT 0,
  require_human_approval BOOLEAN DEFAULT TRUE,
  created_by             TEXT,
  created_at             TIMESTAMPTZ DEFAULT NOW(),
  updated_at             TIMESTAMPTZ DEFAULT NOW()
);


-- ── outreach_logs ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_logs (
  id           TEXT PRIMARY KEY,
  creator_id   TEXT NOT NULL REFERENCES creators(id),
  campaign_id  TEXT REFERENCES campaigns(id),
  contact_id   TEXT REFERENCES contacts(id),
  deck_id      TEXT REFERENCES decks(id),
  subject      TEXT,
  body         TEXT NOT NULL,
  send_method  send_method_enum DEFAULT 'email',
  status       message_status_enum DEFAULT 'draft',
  reviewed_by  TEXT,
  reviewed_at  TIMESTAMPTZ,
  review_notes TEXT,
  queued_at    TIMESTAMPTZ,
  sent_at      TIMESTAMPTZ,
  send_error   TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_outreach_creator ON outreach_logs(creator_id);
CREATE INDEX IF NOT EXISTS idx_outreach_status  ON outreach_logs(status);


-- ── threads ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS threads (
  id                  TEXT PRIMARY KEY,
  creator_id          TEXT NOT NULL REFERENCES creators(id),
  outreach_message_id TEXT REFERENCES outreach_logs(id),
  status              thread_status_enum DEFAULT 'open',
  last_activity       TIMESTAMPTZ DEFAULT NOW(),
  created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_threads_creator ON threads(creator_id);
CREATE INDEX IF NOT EXISTS idx_threads_status  ON threads(status);


-- ── follow_ups ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS follow_ups (
  id            TEXT PRIMARY KEY,
  thread_id     TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  draft         TEXT NOT NULL,
  status        followup_status_enum DEFAULT 'draft',
  scheduled_for TIMESTAMPTZ,
  sent_at       TIMESTAMPTZ,
  reviewed_by   TEXT,
  reviewed_at   TIMESTAMPTZ,
  review_notes  TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_followups_thread ON follow_ups(thread_id);


-- ── replies ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replies (
  id             TEXT PRIMARY KEY,
  thread_id      TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  from_address   TEXT,
  subject        TEXT,
  body           TEXT,
  received_at    TIMESTAMPTZ DEFAULT NOW(),
  classification reply_classification_enum DEFAULT 'other',
  sentiment      TEXT,
  ai_summary     TEXT,
  crm_stage      crm_stage_enum DEFAULT 'new',
  processed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_replies_thread ON replies(thread_id);


-- ── suppression_list ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppression_list (
  id            TEXT PRIMARY KEY,
  creator_id    TEXT REFERENCES creators(id),
  email         TEXT,
  domain        TEXT,
  reason        suppression_reason_enum NOT NULL,
  suppressed_at TIMESTAMPTZ DEFAULT NOW(),
  suppressed_by TEXT,
  notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_suppression_creator ON suppression_list(creator_id);
CREATE INDEX IF NOT EXISTS idx_suppression_email   ON suppression_list(email);
CREATE INDEX IF NOT EXISTS idx_suppression_domain  ON suppression_list(domain);


-- ── reviews ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reviews (
  id          TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id   TEXT NOT NULL,
  reviewer    TEXT NOT NULL,
  decision    review_decision_enum NOT NULL,
  notes       TEXT,
  reviewed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reviews_entity ON reviews(entity_type, entity_id);


-- ── audit_logs ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
  id          TEXT PRIMARY KEY,
  entity_type TEXT,
  entity_id   TEXT,
  action      TEXT NOT NULL,
  actor       TEXT,
  details     JSONB,
  ip_address  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_entity     ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at DESC);


-- ── platform-specific lead tables ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS youtube_leads (
  id                TEXT PRIMARY KEY REFERENCES creators(id) ON DELETE CASCADE,
  channel_id        TEXT,
  video_count       INTEGER DEFAULT 0,
  total_views       BIGINT DEFAULT 0,
  subscriber_count  INTEGER DEFAULT 0,
  engagement_rate   FLOAT DEFAULT 0.0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS instagram_leads (
  id                TEXT PRIMARY KEY REFERENCES creators(id) ON DELETE CASCADE,
  username          TEXT,
  biography         TEXT,
  follower_count    INTEGER DEFAULT 0,
  following_count   INTEGER DEFAULT 0,
  engagement_rate   FLOAT DEFAULT 0.0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tiktok_leads (
  id                TEXT PRIMARY KEY REFERENCES creators(id) ON DELETE CASCADE,
  sec_uid           TEXT,
  follower_count    INTEGER DEFAULT 0,
  heart_count       INTEGER DEFAULT 0,
  video_count       INTEGER DEFAULT 0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS twitter_leads (
  id                TEXT PRIMARY KEY REFERENCES creators(id) ON DELETE CASCADE,
  twitter_id        TEXT,
  follower_count    INTEGER DEFAULT 0,
  tweet_count       INTEGER DEFAULT 0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

