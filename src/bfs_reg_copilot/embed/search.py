"""Dense (vector) search over current chunks for one embedding model."""

from __future__ import annotations

from bfs_reg_copilot.embed.indexer import vector_literal
from bfs_reg_copilot.store.db import Conn


def dense_search(conn: Conn, model: str, query_vector: list[float], k: int) -> list[str]:
    """Chunk ids of the k nearest current chunks, nearest first (cosine distance)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT e.chunk_id FROM chunk_embeddings e JOIN chunks c USING (chunk_id) "
        "WHERE e.model = %s AND c.superseded_at IS NULL "
        "ORDER BY e.embedding <=> %s::vector, e.chunk_id LIMIT %s",
        (model, vector_literal(query_vector), k),
    )
    return [str(row[0]) for row in cur.fetchall()]
