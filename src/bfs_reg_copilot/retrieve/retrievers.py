"""Dense, full-text and hybrid retrievers.

Hybrid uses reciprocal rank fusion (RRF): each list gives a chunk 1/(k + rank), the scores add.
It needs only ranks, so the unrelated scales of cosine similarity and ts_rank do not matter.
k = 60 is the value from the original RRF paper; it is not tuned here.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Final

from bfs_reg_copilot.embed.ollama import Embedder
from bfs_reg_copilot.embed.search import dense_scored, fulltext_scored
from bfs_reg_copilot.retrieve.types import Hit, Retriever
from bfs_reg_copilot.store.db import Conn

RRF_K: Final = 60
CANDIDATE_DEPTH: Final = 50  # how many results each list contributes to the fusion


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[Hit]:
    """Fuse ranked lists of chunk ids. Ties break by chunk id so results are reproducible."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + position)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [Hit(chunk_id, score) for chunk_id, score in ordered]


class DenseRetriever:
    is_test_double = False

    def __init__(self, conn: Conn, embedder: Embedder) -> None:
        self._conn = conn
        self._embedder = embedder
        self.name = f"dense:{embedder.model.name}"
        self.is_test_double = embedder.is_test_double

    def retrieve(self, question: str, k: int) -> list[Hit]:
        [vector] = self._embedder.embed_queries([question])
        return [
            Hit(c, s) for c, s in dense_scored(self._conn, self._embedder.model.name, vector, k)
        ]


class FullTextRetriever:
    name = "fulltext"
    is_test_double = False

    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def retrieve(self, question: str, k: int) -> list[Hit]:
        return [Hit(c, s) for c, s in fulltext_scored(self._conn, question, k)]


class HybridRetriever:
    def __init__(self, dense: DenseRetriever, fulltext: FullTextRetriever) -> None:
        self._dense = dense
        self._fulltext = fulltext
        self.name = f"hybrid:{dense.name.split(':', 1)[1]}"
        self.is_test_double = dense.is_test_double

    def retrieve(self, question: str, k: int) -> list[Hit]:
        lists = [
            [h.chunk_id for h in self._dense.retrieve(question, CANDIDATE_DEPTH)],
            [h.chunk_id for h in self._fulltext.retrieve(question, CANDIDATE_DEPTH)],
        ]
        return rrf(lists)[:k]


def make_retrievers(conn: Conn, embedder: Embedder) -> dict[str, Retriever]:
    dense = DenseRetriever(conn, embedder)
    fulltext = FullTextRetriever(conn)
    return {"dense": dense, "fulltext": fulltext, "hybrid": HybridRetriever(dense, fulltext)}
