# 14. Database

PostgreSQL with pgvector, run locally in Docker ([ADR-0004](adr/0004-postgres-pgvector-for-retrieval.md),
[ADR-0015](adr/0015-storage-schema-and-embedding-size.md)). It holds chunks and, from slice 2.4,
their embeddings. The source of truth stays the files under `data/` (git-ignored); the database
can always be rebuilt from them.

## Run it

```powershell
docker compose up -d --wait          # start (first run downloads the image)
uv run python -m bfs_reg_copilot.store migrate
uv run python -m bfs_reg_copilot.store load
uv run python -m bfs_reg_copilot.store status
docker compose down                  # stop; the data stays in a volume
docker compose down -v               # stop and delete the data
```

The address defaults to `postgresql://bfs:bfs_dev@127.0.0.1:5433/bfs` (loopback only). Override it
with the `BFS_DATABASE_URL` environment variable.

## Tables

| Table | Holds |
|---|---|
| `chunks` | One row per chunk: id, source, page hash, retrieval time, URL, heading path, text, generated full-text column. `superseded_at` is set when a newer page version is loaded |
| `chunk_embeddings` | One row per (chunk, model): a 1,024-dimension vector. Empty until slice 2.4 |
| `schema_migrations` | Which migrations ran, with checksums |

## What `load` does

For each source it reads the chunk file with the most recent `retrieved_at`, inserts new chunks,
leaves identical ones alone, updates changed ones (and deletes their embeddings), and marks chunks
of older page versions of that source as superseded. Running it twice changes nothing. It prints
the counts: for the Phase 1 snapshot the total is 624 chunks (B-10 is 71 here; see RAID I-6).

## Running the database tests

Without a database the storage tests that need one are skipped. To run them locally:

```powershell
$env:BFS_TEST_DATABASE_URL = "postgresql://bfs:bfs_dev@127.0.0.1:5433/bfs"
uv run python -m pytest tests/test_store.py
```

Each test creates and drops its own database, so the role needs permission to create databases
(the Docker role does). CI runs the same tests against a pgvector service container.

## Limits

- The driver is pg8000, chosen because it is pure Python and therefore not blocked by Windows
  Application Control (ADR-0015).
- Development password, no TLS, no backups: it is a local learning database, not a template for
  production. Production handling of credentials and encryption is Phase 4.
- Postgres on the laptop competes for memory with the model server; Docker Desktop shows 5.8 GiB
  available, enough for this corpus.
