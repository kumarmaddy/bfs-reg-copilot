# ADR-0015: Plain-SQL migrations, one chunk table, embeddings per model at 1024 dimensions

- Status: Accepted
- Date: 2026-11-23
- Deciders: Project owner

## Context

ADR-0004 chose PostgreSQL with pgvector. Phase 2 needs a schema before any embedding exists, and a
vector column has a fixed size, so the size has to be chosen before the model is. Chunks are at
most 1,800 characters (about 400 tokens), so every candidate model's input limit is far above
what we send.

Candidates for a local model on the project machine (published figures, not measured here):

| Model | Size | Output dimensions | Notes |
|---|---|---|---|
| bge-m3 | 567M parameters, about 1.2 GB | 1,024 | 8K-token input, MIT licence, no query prefix needed |
| qwen3-embedding:0.6b | 0.6B, about 639 MB | adjustable, up to 1,024 | 32K-token input, Apache 2.0, wants an instruction before the query |
| nomic-embed-text | 137M, 274 MB | 768 | Most pulled on Ollama; needs task prefixes; Ollama 0.30.0 changed it to lowercase input, which loses capitalisation in names |

## Decision

- **Vector size 1,024.** Both bge-m3 and qwen3-embedding:0.6b fit it. nomic-embed-text (768) is
  out unless we pay for a new migration.
- **The model is chosen in slice 2.4 by measurement,** not by leaderboard: embed the corpus with
  each of the two, run retrieval only, and compare hit@5 on the dev split (never the hold-out).
  Retrieval-only runs cost seconds. The choice and the numbers go in the next ADR.
- **Embeddings are keyed by (chunk, model).** Two models can sit side by side, so the comparison
  needs no rebuild and a later swap leaves the old vectors in place until we drop them.
- **One `chunks` table holding every loaded page version.** A newer page version marks the older
  rows `superseded_at`; retrieval reads only current rows. Old rows are kept so a gold-set id from
  an earlier version can still be explained.
- **Changed text drops its embeddings.** Chunk ids hold the page hash but not the cleaner or
  chunker version, so a re-chunk can reuse an id with new text. The loader updates the row and
  deletes its embeddings.
- **Full-text search from day one:** a generated `tsvector` (English) with a GIN index, for the
  keyword half of hybrid retrieval (ADR-0004).
- **No vector index yet.** With about 600 chunks a sequential scan is exact and fast, and an
  approximate index would add its own error to the retrieval metric. Add HNSW when the scale
  test (S2) needs it, with the recall loss measured.
- **Driver: pg8000 (pure Python), not psycopg.** On the project machine Windows Application Control
  blocked the native `libpq` library that `psycopg[binary]` bundles, the same policy that blocks
  `.exe` launchers. pg8000 loads no native code. Trade-offs: it ships no type information (mypy is
  told to ignore it, and the thin `store` layer is tested against a real database instead), it is
  slower than psycopg, and it has no `COPY`; none matters at this corpus size.
- **Migrations are numbered plain SQL files** applied by a small runner. Each applied file's
  checksum is recorded; editing an applied file stops the run. One advisory lock allows one
  migrator at a time.

## Alternatives considered

| Option | Why not |
|---|---|
| Alembic or another migration framework | More machinery than five or six SQL files need; the runner is under 100 lines and fully tested. Revisit if migrations need branching or data transforms |
| An ORM (SQLAlchemy) | The queries are few and specific (`<=>`, `tsvector`); plain SQL through the driver is easier to review and tune |
| Vector size per model (separate tables) | Faster to start, harder to compare models and to query uniformly |
| Delete old page versions on refresh | Simpler, but loses the ability to explain old gold-set ids |

## Consequences

- Changing the vector size means a new migration and re-embedding everything.
- The test suite runs against a real Postgres with pgvector in CI (a service container), so SQL
  mistakes fail the build rather than a demo.
- The local database is a throwaway: loopback only, a development password in `docker-compose.yml`,
  no real data. A shared or cloud database needs real secrets handling (Phase 4).

## Revisit when

Retrieval p95 exceeds the S2 target; the chosen model needs a different size; or migrations need
data transforms.
