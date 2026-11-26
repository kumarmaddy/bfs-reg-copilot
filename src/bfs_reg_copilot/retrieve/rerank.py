"""Rerank a candidate pool with a cross-encoder served by a local llama.cpp server.

A bi-encoder (bge-m3) scores the question and each chunk separately; a cross-encoder
(bge-reranker-v2-m3) reads them together, which is slower and sharper. The pool comes from the
hybrid retriever (depth 35 holds every gold chunk of the dev questions that failed at hybrid k=5);
only the order of the pool changes. Nothing leaves the machine. Server start-up and flags are in
docs/21-running-experiments.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, Protocol

import httpx

from bfs_reg_copilot.retrieve.types import Hit, Retriever

DEFAULT_URL: Final = "http://127.0.0.1:8081"
DEFAULT_POOL: Final = 35
# The server is started with a 2048-token physical batch; ~4 characters per token leaves headroom.
MAX_PASSAGE_CHARS: Final = 6000


class RerankError(Exception):
    pass


class Reranker(Protocol):
    is_test_double: bool

    def score(self, question: str, passages: Sequence[str]) -> list[float]:
        """One relevance score per passage, in the order given (higher is better)."""
        ...


class HasText(Protocol):
    @property
    def chunk_id(self) -> str: ...
    @property
    def text(self) -> str: ...


class TextSource(Protocol):
    def fetch(self, chunk_ids: Sequence[str]) -> Sequence[HasText]: ...


class LlamaServerReranker:
    is_test_double = False

    def __init__(
        self,
        url: str = DEFAULT_URL,
        client: httpx.Client | None = None,
        max_chars: int = MAX_PASSAGE_CHARS,
    ) -> None:
        self._url = url.rstrip("/") + "/v1/rerank"
        self._client = client or httpx.Client(timeout=300.0)
        self._max_chars = max_chars
        self.truncated = 0  # passages cut to fit the server's batch, counted for the run log

    def score(self, question: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        cut = [p[: self._max_chars] for p in passages]
        self.truncated += sum(len(a) != len(b) for a, b in zip(passages, cut, strict=True))
        try:
            response = self._client.post(self._url, json={"query": question, "documents": cut})
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RerankError(
                f"reranker at {self._url} failed: {type(exc).__name__}: {exc}. Is llama-server "
                "running with --reranking -b 2048 -ub 2048?"
            ) from exc
        scores: dict[int, float] = {}
        for result in body.get("results", []):
            index, value = result.get("index"), result.get("relevance_score")
            if isinstance(index, int) and isinstance(value, int | float):
                scores[index] = float(value)
        if len(scores) != len(passages) or set(scores) != set(range(len(passages))):
            raise RerankError(
                f"reranker returned {len(scores)} scores for {len(passages)} passages"
            )
        return [scores[i] for i in range(len(passages))]


class RerankedRetriever:
    """Take the inner retriever's top `pool`, reorder by cross-encoder score, return the top k."""

    def __init__(
        self, inner: Retriever, texts: TextSource, reranker: Reranker, pool: int = DEFAULT_POOL
    ) -> None:
        self._inner = inner
        self._texts = texts
        self._reranker = reranker
        self._pool = pool
        self.name = f"reranked:{inner.name}"
        self.is_test_double = inner.is_test_double or reranker.is_test_double

    def retrieve(self, question: str, k: int) -> list[Hit]:
        candidates = [h.chunk_id for h in self._inner.retrieve(question, self._pool)]
        found = {c.chunk_id: c.text for c in self._texts.fetch(candidates)}
        ids = [c for c in candidates if c in found]  # a chunk that vanished is simply dropped
        scores = self._reranker.score(question, [found[c] for c in ids])
        order = sorted(range(len(ids)), key=lambda i: (-scores[i], i))  # ties keep pool order
        return [Hit(ids[i], scores[i]) for i in order][:k]
