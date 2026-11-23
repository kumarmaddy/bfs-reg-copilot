"""Load stored chunk files into the `chunks` table.

The current page version of a source is the chunk file with the most recent `retrieved_at`.
Loading is idempotent. Chunk ids hold the page hash but not the cleaner or chunker version, so a
re-chunk can give the same id with different text: such a chunk is updated and its embeddings are
deleted, because they describe text that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bfs_reg_copilot.ingest.chunk_store import read_chunks
from bfs_reg_copilot.ingest.chunking import Chunk
from bfs_reg_copilot.store.db import Conn, transaction

COLUMNS = (
    "chunk_id",
    "source_id",
    "raw_sha256",
    "retrieved_at",
    "final_url",
    "page_title",
    "date_modified",
    "section_index",
    "section_heading",
    "section_path",
    "anchor",
    "chunk_index",
    "chunk_count",
    "section_start",
    "section_end",
    "text",
)


@dataclass
class LoadResult:
    source_id: str
    path: Path
    inserted: int = 0
    unchanged: int = 0
    changed: int = 0
    superseded: int = 0
    notes: list[str] = field(default_factory=list)


def chunk_to_row(chunk: Chunk) -> dict[str, Any]:
    row = chunk.model_dump()
    row["section_path"] = list(chunk.section_path)
    return row


def current_chunk_files(curated_root: Path, only: str | None = None) -> dict[str, Path]:
    """source_id -> the chunk file of its most recently retrieved page version."""
    chosen: dict[str, tuple[Any, Path]] = {}
    for folder in sorted(p for p in curated_root.iterdir() if p.is_dir()):
        if only is not None and folder.name != only:
            continue
        for path in sorted(folder.glob("*.jsonl")):
            chunks = read_chunks(path)
            if not chunks:
                continue
            key = (chunks[0].retrieved_at, path.stat().st_mtime)
            if folder.name not in chosen or key > chosen[folder.name][0]:
                chosen[folder.name] = (key, path)
    return {source: path for source, (_, path) in chosen.items()}


def load_source(conn: Conn, source_id: str, path: Path) -> LoadResult:
    chunks = read_chunks(path)
    result = LoadResult(source_id, path)
    wrong = [c.chunk_id for c in chunks if c.source_id != source_id]
    if wrong:
        raise ValueError(f"{path.name}: chunks belong to another source: {wrong[:3]}")
    ids = [c.chunk_id for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: duplicate chunk ids")
    cur = conn.cursor()
    with transaction(conn):
        cur.execute("SELECT chunk_id, text FROM chunks WHERE chunk_id = ANY(%s)", (ids,))
        existing = {str(i): str(t) for i, t in cur.fetchall()}
        changed_ids = [
            c.chunk_id for c in chunks if c.chunk_id in existing and existing[c.chunk_id] != c.text
        ]
        result.inserted = sum(1 for c in chunks if c.chunk_id not in existing)
        result.changed = len(changed_ids)
        result.unchanged = len(chunks) - result.inserted - result.changed
        if changed_ids:
            cur.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ANY(%s)", (changed_ids,))
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])
        cur.executemany(
            f"INSERT INTO chunks ({', '.join(COLUMNS)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT (chunk_id) DO UPDATE SET {updates}, superseded_at = NULL",
            [tuple(chunk_to_row(c)[col] for col in COLUMNS) for c in chunks],
        )
        cur.execute(
            "UPDATE chunks SET superseded_at = now() "
            "WHERE source_id = %s AND superseded_at IS NULL AND chunk_id <> ALL(%s)",
            (source_id, ids),
        )
        result.superseded = cur.rowcount
    return result


def counts(conn: Conn) -> list[tuple[str, int, int]]:
    """(source_id, current chunks, current chunks with at least one embedding)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT c.source_id, count(*), "
        "count(*) FILTER (WHERE EXISTS "
        "(SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.chunk_id)) "
        "FROM chunks c WHERE c.superseded_at IS NULL GROUP BY c.source_id ORDER BY 1"
    )
    return [(str(s), int(n), int(e)) for s, n, e in cur.fetchall()]
