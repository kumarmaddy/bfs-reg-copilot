"""Dense (vector) and full-text search over current chunks."""

from __future__ import annotations

from bfs_reg_copilot.embed.indexer import vector_literal
from bfs_reg_copilot.store.db import Conn

# The question's stemmed words, OR-ed together. A natural-language question rarely has every word
# in one chunk, so an AND query (plainto_tsquery) would find almost nothing. The lexemes are
# already stemmed by the 'english' config used for the stored column, so they are matched as they
# are ('simple'), and quoted so punctuation in a question cannot break the query syntax.
_FULLTEXT_SQL = (
    "WITH q AS (SELECT to_tsquery('simple', string_agg(quote_literal(l), ' | ')) AS query "
    "FROM unnest(tsvector_to_array(to_tsvector('english', %s))) AS l) "
    "SELECT c.chunk_id, ts_rank_cd(c.text_search, q.query, 1) AS score "
    "FROM chunks c, q WHERE c.superseded_at IS NULL AND c.text_search @@ q.query "
    "ORDER BY score DESC, c.chunk_id LIMIT %s"
)


def dense_scored(
    conn: Conn, model: str, query_vector: list[float], k: int
) -> list[tuple[str, float]]:
    """(chunk id, cosine similarity) of the k nearest current chunks, nearest first."""
    cur = conn.cursor()
    cur.execute(
        "SELECT e.chunk_id, 1 - (e.embedding <=> %s::vector) AS similarity "
        "FROM chunk_embeddings e JOIN chunks c USING (chunk_id) "
        "WHERE e.model = %s AND c.superseded_at IS NULL "
        "ORDER BY e.embedding <=> %s::vector, e.chunk_id LIMIT %s",
        (vector_literal(query_vector), model, vector_literal(query_vector), k),
    )
    return [(str(r[0]), float(r[1])) for r in cur.fetchall()]


def dense_search(conn: Conn, model: str, query_vector: list[float], k: int) -> list[str]:
    """Chunk ids of the k nearest current chunks, nearest first (cosine distance)."""
    return [chunk_id for chunk_id, _ in dense_scored(conn, model, query_vector, k)]


def fulltext_scored(conn: Conn, question: str, k: int) -> list[tuple[str, float]]:
    """(chunk id, rank) of the k best keyword matches among current chunks."""
    cur = conn.cursor()
    cur.execute(_FULLTEXT_SQL, (question, k))
    return [(str(r[0]), float(r[1])) for r in cur.fetchall()]
