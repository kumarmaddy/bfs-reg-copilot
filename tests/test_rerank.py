"""Reranking: the llama-server client (mock transport), pool reordering, and the Stage 1 verdict."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import httpx
import pytest

from bfs_reg_copilot.retrieve.evaluate import SupportRank, rerank_verdict
from bfs_reg_copilot.retrieve.rerank import (
    LlamaServerReranker,
    RerankedRetriever,
    RerankError,
)
from bfs_reg_copilot.retrieve.types import Hit


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _ok(scores: dict[int, float]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        results = [{"index": i, "relevance_score": s} for i, s in scores.items()]
        return httpx.Response(200, json={"results": results})

    return httpx.MockTransport(handle)


def test_scores_come_back_in_the_order_the_passages_were_sent() -> None:
    # the server answers sorted by score, not by index; the client must undo that
    reranker = LlamaServerReranker(client=_client(_ok({1: 0.5, 2: -4.0, 0: -9.0})))
    assert reranker.score("q", ["a", "b", "c"]) == [-9.0, 0.5, -4.0]


def test_long_passages_are_cut_and_counted() -> None:
    seen: list[list[str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        import json

        docs = json.loads(request.content)["documents"]
        seen.append(docs)
        return httpx.Response(
            200, json={"results": [{"index": i, "relevance_score": 0.0} for i in range(len(docs))]}
        )

    reranker = LlamaServerReranker(client=_client(httpx.MockTransport(handle)), max_chars=10)
    reranker.score("q", ["x" * 50, "short"])
    assert seen == [["x" * 10, "short"]]
    assert reranker.truncated == 1


def test_server_down_or_wrong_shape_raises_a_clear_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(RerankError, match="llama-server"):
        LlamaServerReranker(client=_client(httpx.MockTransport(refuse))).score("q", ["a"])
    with pytest.raises(RerankError, match="1 scores for 2"):
        LlamaServerReranker(client=_client(_ok({0: 1.0}))).score("q", ["a", "b"])
    assert LlamaServerReranker(client=_client(_ok({}))).score("q", []) == []


@dataclass(frozen=True)
class _Chunk:
    chunk_id: str
    text: str


class _Texts:
    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts

    def fetch(self, chunk_ids: Sequence[str]) -> list[_Chunk]:
        return [_Chunk(i, self._texts[i]) for i in chunk_ids if i in self._texts]


class _Pool:
    name = "hybrid:x"
    is_test_double = True

    def __init__(self, ids: list[str]) -> None:
        self._ids = ids
        self.asked: list[int] = []

    def retrieve(self, question: str, k: int) -> list[Hit]:
        self.asked.append(k)
        return [Hit(i, 0.0) for i in self._ids[:k]]


class _ByLength:
    is_test_double = True

    def score(self, question: str, passages: Sequence[str]) -> list[float]:
        return [float(len(p)) for p in passages]


def test_pool_is_reordered_by_score_and_cut_to_k() -> None:
    pool = _Pool(["a", "b", "c", "d"])
    texts = _Texts({"a": "x", "b": "xxxx", "c": "xx", "d": "xxx"})
    retriever = RerankedRetriever(pool, texts, _ByLength(), pool=4)
    assert [h.chunk_id for h in retriever.retrieve("q", 2)] == ["b", "d"]
    assert pool.asked == [4]  # the pool depth, not k
    assert retriever.name == "reranked:hybrid:x"


def test_ties_keep_pool_order_and_vanished_chunks_are_dropped() -> None:
    pool = _Pool(["a", "gone", "b", "c"])
    texts = _Texts({"a": "xx", "b": "xx", "c": "xx"})
    retriever = RerankedRetriever(pool, texts, _ByLength(), pool=4)
    assert [h.chunk_id for h in retriever.retrieve("q", 5)] == ["a", "b", "c"]


def _rows(dense: list[int | None], reranked: list[int | None]) -> list[SupportRank]:
    return [
        SupportRank(f"G-{n}", f"S:{n}:c000", {"dense": d, "reranked": r})
        for n, (d, r) in enumerate(zip(dense, reranked, strict=True))
    ]


def test_stage_one_verdict_needs_the_pre_registered_count() -> None:
    meets = rerank_verdict(_rows([9, 1, 1, 1], [1, 1, 1, 1]), "reranked", "dense", needed=4)
    assert "rule met" in meets
    assert "3 -> 4 of 4" in meets
    misses = rerank_verdict(_rows([9, 1, 1, 1], [1, 1, 1, 7]), "reranked", "dense", needed=4)
    assert "not met" in misses
    assert "drop the reranker" in misses
