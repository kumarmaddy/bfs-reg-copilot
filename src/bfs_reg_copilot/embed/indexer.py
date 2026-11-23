"""Embed every current chunk that has no embedding yet for a model. Safe to stop and re-run."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from bfs_reg_copilot.embed.models import document_text
from bfs_reg_copilot.embed.ollama import Embedder
from bfs_reg_copilot.store.db import Conn, transaction

DEFAULT_BATCH = 16


@dataclass(frozen=True)
class IndexResult:
    model: str
    embedded: int
    already_done: int
    seconds: float


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in vector) + "]"


def index_model(
    conn: Conn,
    embedder: Embedder,
    batch_size: int = DEFAULT_BATCH,
    progress: Callable[[int, int], None] | None = None,
) -> IndexResult:
    name = embedder.model.name
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM chunks c WHERE c.superseded_at IS NULL AND EXISTS "
        "(SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.chunk_id AND e.model = %s)",
        (name,),
    )
    done = int((cur.fetchone() or [0])[0])
    cur.execute(
        "SELECT c.chunk_id, c.section_path, c.text FROM chunks c "
        "WHERE c.superseded_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.chunk_id AND e.model = %s) "
        "ORDER BY c.chunk_id",
        (name,),
    )
    todo = [(str(i), list(p), str(t)) for i, p, t in cur.fetchall()]
    conn.rollback()  # end the read transaction before the long embedding loop
    started = time.monotonic()
    embedded = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        vectors = embedder.embed_documents([document_text(p, t) for _, p, t in batch])
        with transaction(conn):
            cur = conn.cursor()
            cur.executemany(
                "INSERT INTO chunk_embeddings (chunk_id, model, embedding) "
                "VALUES (%s, %s, %s::vector) "
                "ON CONFLICT (chunk_id, model) DO UPDATE SET embedding = EXCLUDED.embedding, "
                "embedded_at = now()",
                [
                    (cid, name, vector_literal(v))
                    for (cid, _, _), v in zip(batch, vectors, strict=True)
                ],
            )
        embedded += len(batch)
        if progress:
            progress(embedded, len(todo))
    return IndexResult(name, embedded, done, time.monotonic() - started)
