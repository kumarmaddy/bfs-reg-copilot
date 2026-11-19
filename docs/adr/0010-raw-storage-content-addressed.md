# ADR-0010: Raw storage is content-addressed with an append-only manifest

- Status: Accepted
- Date: 2026-11-19
- Deciders: Project owner

## Context

Every chunk in the index must trace back to a register entry and a retrieval date, and the
evidence must survive a page being edited or removed by its publisher. The raw bytes are corpus
text, so they stay out of git (ADR-0007).

## Decision

- Bytes are stored exactly as received, named by their SHA-256:
  `data/raw/<source_id>/blobs/<sha256>.bin`.
- Each retrieval appends one JSON line to `data/raw/<source_id>/manifest.jsonl` with the source
  id, requested and final URL, status, content type, UTC retrieval time, hash, size, ETag and
  Last-Modified.
- Identical content shares one blob but still gets a manifest line, so "unchanged on this date"
  is recorded. Changed content is added next to the old, never over it.
- Blobs are written to a temporary file, synced, then renamed. The manifest line is written only
  after the blob exists.
- Reading a blob re-checks its hash and refuses a mismatch.
- The source id becomes a folder name, so only well-formed register ids are accepted.

## Alternatives considered

| Option | Why not |
|---|---|
| Overwrite one file per source | Loses history; cannot show what a page said when we used it |
| Timestamped file names only | Duplicates identical content and gives no integrity check |
| Database table from the start | Premature; the manifest has the same fields and can be loaded into Postgres in Phase 2 |

## Consequences

- Re-runs are cheap and idempotent in content terms.
- The manifest is the single lineage anchor that cleaning and chunking will reference.
- Local disk only; no backup, encryption or retention policy yet. Acceptable for public data on a
  learning machine; revisit before any shared deployment.

## Revisit when

Storage moves off a local disk, or a retention or deletion requirement appears.
