-- ============================================================
-- PartSelect Chatbot · PostgreSQL Schema
-- Requires: PostgreSQL 15+, pgvector extension
-- Run: psql -d partselect -f schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Taxonomy ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS appliance_type (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(50)  NOT NULL UNIQUE,
    slug VARCHAR(50)  NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS brand (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS part_category (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    appliance_type_id INTEGER      NOT NULL REFERENCES appliance_type(id),
    slug              VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS symptom (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(200) NOT NULL,
    appliance_type_id INTEGER      NOT NULL REFERENCES appliance_type(id)
);

-- ── Entities ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS appliance_model (
    id                SERIAL PRIMARY KEY,
    model_number      VARCHAR(50)  NOT NULL UNIQUE,
    brand_id          INTEGER      NOT NULL REFERENCES brand(id),
    appliance_type_id INTEGER      NOT NULL REFERENCES appliance_type(id),
    description       TEXT
);

CREATE TABLE IF NOT EXISTS part (
    id              SERIAL PRIMARY KEY,
    ps_number       VARCHAR(20)   NOT NULL UNIQUE,
    mfr_part_number VARCHAR(50)   NOT NULL,
    name            VARCHAR(200)  NOT NULL,
    description     TEXT          NOT NULL,
    price           DECIMAL(10,2),
    in_stock        BOOLEAN       NOT NULL DEFAULT true,
    category_id     INTEGER       NOT NULL REFERENCES part_category(id),
    product_url     VARCHAR(500),
    embedding       vector(1536)
);

-- ── Junctions ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_part_compat (
    model_id  INTEGER NOT NULL REFERENCES appliance_model(id) ON DELETE CASCADE,
    part_id   INTEGER NOT NULL REFERENCES part(id)            ON DELETE CASCADE,
    PRIMARY KEY (model_id, part_id)
);

CREATE TABLE IF NOT EXISTS part_supersedes (
    part_id         INTEGER     NOT NULL REFERENCES part(id) ON DELETE CASCADE,
    old_part_number VARCHAR(50) NOT NULL,
    PRIMARY KEY (part_id, old_part_number)
);

CREATE TABLE IF NOT EXISTS part_symptom_fix (
    part_id      INTEGER NOT NULL REFERENCES part(id)    ON DELETE CASCADE,
    symptom_id   INTEGER NOT NULL REFERENCES symptom(id) ON DELETE CASCADE,
    fix_rate_pct INTEGER NOT NULL CHECK (fix_rate_pct BETWEEN 1 AND 100),
    PRIMARY KEY (part_id, symptom_id)
);

-- ── Knowledge ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expert_qa (
    id            SERIAL PRIMARY KEY,
    model_id      INTEGER REFERENCES appliance_model(id) ON DELETE SET NULL,
    question      TEXT    NOT NULL,
    answer        TEXT    NOT NULL,
    asker_name    VARCHAR(100),
    asked_at      DATE,
    helpful_count INTEGER NOT NULL DEFAULT 0,
    embedding     vector(1536)
);

CREATE TABLE IF NOT EXISTS repair_story (
    id          SERIAL PRIMARY KEY,
    model_id    INTEGER REFERENCES appliance_model(id) ON DELETE SET NULL,
    story       TEXT    NOT NULL,
    author      VARCHAR(100),
    difficulty  VARCHAR(50),
    repair_time VARCHAR(50),
    tools       VARCHAR(200),
    created_at  DATE,
    embedding   vector(1536)
);

CREATE TABLE IF NOT EXISTS qa_part_ref (
    qa_id   INTEGER NOT NULL REFERENCES expert_qa(id)    ON DELETE CASCADE,
    part_id INTEGER NOT NULL REFERENCES part(id)         ON DELETE CASCADE,
    PRIMARY KEY (qa_id, part_id)
);

CREATE TABLE IF NOT EXISTS repair_story_part (
    story_id   INTEGER NOT NULL REFERENCES repair_story(id) ON DELETE CASCADE,
    part_id    INTEGER NOT NULL REFERENCES part(id)         ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (story_id, part_id)
);

CREATE TABLE IF NOT EXISTS part_review (
    id                SERIAL PRIMARY KEY,
    part_id           INTEGER  NOT NULL REFERENCES part(id) ON DELETE CASCADE,
    rating            SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body              TEXT,
    author            VARCHAR(100),
    created_at        DATE,
    verified_purchase BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS video (
    id            SERIAL PRIMARY KEY,
    part_id       INTEGER      NOT NULL REFERENCES part(id) ON DELETE CASCADE,
    title         VARCHAR(300) NOT NULL,
    url           VARCHAR(500) NOT NULL,
    thumbnail_url VARCHAR(500)
);

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_model_number_trgm ON appliance_model USING gin(model_number gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_part_ps_number     ON part(ps_number);
CREATE INDEX IF NOT EXISTS idx_part_mfr_number    ON part(mfr_part_number);
CREATE INDEX IF NOT EXISTS idx_compat_model       ON model_part_compat(model_id);
CREATE INDEX IF NOT EXISTS idx_compat_part        ON model_part_compat(part_id);
CREATE INDEX IF NOT EXISTS idx_supersedes_old     ON part_supersedes(old_part_number);
CREATE INDEX IF NOT EXISTS idx_fix_symptom        ON part_symptom_fix(symptom_id);
CREATE INDEX IF NOT EXISTS idx_review_part        ON part_review(part_id);
CREATE INDEX IF NOT EXISTS idx_video_part         ON video(part_id);
CREATE INDEX IF NOT EXISTS idx_qa_model           ON expert_qa(model_id);
CREATE INDEX IF NOT EXISTS idx_story_model        ON repair_story(model_id);

-- Note: IVFFlat vector indexes are built by generate_embeddings.py
-- AFTER embeddings are populated — IVFFlat requires data at build time.
