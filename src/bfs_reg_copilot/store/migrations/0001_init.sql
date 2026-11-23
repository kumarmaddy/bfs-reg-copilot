-- 0001: chunks, their embeddings, and full-text search.
-- Embedding size: 1024 fits both candidate models (bge-m3 natively; qwen3-embedding:0.6b at 1024
-- dimensions). Changing it needs a new migration and a full re-embed (ADR-0015).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    chunk_id        text PRIMARY KEY,
    source_id       text        NOT NULL,
    raw_sha256      text        NOT NULL,
    retrieved_at    timestamptz NOT NULL,
    final_url       text        NOT NULL,
    page_title      text        NOT NULL,
    date_modified   text,
    section_index   integer     NOT NULL,
    section_heading text        NOT NULL,
    section_path    text[]      NOT NULL,
    anchor          text,
    chunk_index     integer     NOT NULL,
    chunk_count     integer     NOT NULL,
    section_start   integer     NOT NULL,
    section_end     integer     NOT NULL,
    text            text        NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    -- set when a newer page version of the same source is loaded; retrieval ignores these rows
    superseded_at   timestamptz,
    text_search     tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(section_heading, '') || ' ' || text)
    ) STORED
);

CREATE INDEX chunks_source_current_idx ON chunks (source_id) WHERE superseded_at IS NULL;
CREATE INDEX chunks_text_search_idx ON chunks USING gin (text_search);

-- One row per (chunk, model), so two embedding models can be compared on the same chunks.
-- No vector index yet: at this corpus size a sequential scan is exact and fast, and an
-- approximate index would blur the retrieval metric. Add one when the scale test needs it.
CREATE TABLE chunk_embeddings (
    chunk_id    text        NOT NULL REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    model       text        NOT NULL,
    embedding   vector(1024) NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, model)
);
