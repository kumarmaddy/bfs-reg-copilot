"""Embedding tests: the Ollama client (mock server), indexing, dense search and the comparison.

Database tests run only when BFS_TEST_DATABASE_URL is set (see test_store.py).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from bfs_reg_copilot.embed.compare import (
    ModelResult,
    dev_items,
    evaluate_model,
    missing_support,
    render,
)
from bfs_reg_copilot.embed.fakes import HashingEmbedder
from bfs_reg_copilot.embed.indexer import index_model, vector_literal
from bfs_reg_copilot.embed.models import (
    BGE_M3,
    MODELS,
    QWEN3_06B,
    document_text,
    get_model,
)
from bfs_reg_copilot.embed.ollama import EmbedError, OllamaEmbedder
from bfs_reg_copilot.embed.search import dense_search
from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet
from bfs_reg_copilot.ingest.chunk_store import write_chunks
from bfs_reg_copilot.ingest.chunking import Chunk
from bfs_reg_copilot.store.db import EMBEDDING_DIMS, Conn
from bfs_reg_copilot.store.loader import counts, embedded_by_model, load_source
from dbhelpers import make_chunk as _make_chunk
from dbhelpers import needs_db

SRC = "A-TEST"  # gold-set source ids must look like A-... to B-...


def make_chunk(**kwargs: Any) -> Chunk:
    return _make_chunk(source=SRC, **kwargs)


# --- no database needed ------------------------------------------------------------------------


def test_every_model_fits_the_column() -> None:
    assert {m.dims for m in MODELS.values()} == {EMBEDDING_DIMS}
    with pytest.raises(KeyError, match="unknown embedding model"):
        get_model("nope")


def test_document_text_matches_the_chunk_method() -> None:
    chunk = make_chunk()
    assert document_text(chunk.section_path, chunk.text) == chunk.contextualised()


def test_only_qwen3_gets_a_query_instruction() -> None:
    assert BGE_M3.query_format("what is scope?") == "what is scope?"
    formatted = QWEN3_06B.query_format("what is scope?")
    assert formatted.startswith("Instruct: ")
    assert formatted.endswith("Query: what is scope?")


def _mock(handler: httpx.MockTransport) -> OllamaEmbedder:
    return OllamaEmbedder(BGE_M3, host="http://ollama.test", client=httpx.Client(transport=handler))


def test_ollama_request_and_response() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"embeddings": [[0.5] * EMBEDDING_DIMS for _ in body["input"]]}
        )

    embedder = _mock(httpx.MockTransport(handler))
    vectors = embedder.embed_documents(["a", "b"])
    assert len(vectors) == 2
    assert len(vectors[0]) == EMBEDDING_DIMS
    assert seen[0] == {"model": "bge-m3", "input": ["a", "b"], "truncate": False}
    assert embedder.embed_documents([]) == []  # no request for nothing
    assert len(seen) == 1


def test_queries_use_the_model_query_format() -> None:
    seen: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        seen.append(texts)
        return httpx.Response(200, json={"embeddings": [[0.0] * EMBEDDING_DIMS for _ in texts]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    OllamaEmbedder(QWEN3_06B, host="http://x", client=client).embed_queries(["q"])
    assert seen[0][0].startswith("Instruct: ")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"embeddings": [[0.0] * EMBEDDING_DIMS]}),  # 1 for 2 inputs
        httpx.Response(200, json={"embeddings": [[0.0] * 3, [0.0] * 3]}),  # wrong size
        httpx.Response(200, json={"error": "model not found"}),
    ],
)
def test_ollama_problems_become_embed_errors(response: httpx.Response) -> None:
    embedder = _mock(httpx.MockTransport(lambda request: response))
    with pytest.raises(EmbedError):
        embedder.embed_documents(["a", "b"])


def test_unreachable_server_is_an_embed_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(EmbedError, match="failed"):
        _mock(httpx.MockTransport(refuse)).embed_documents(["a"])


def test_transient_disconnects_are_retried_then_succeed() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return httpx.Response(200, json={"embeddings": [[0.0] * EMBEDDING_DIMS]})

    client = httpx.Client(transport=httpx.MockTransport(flaky))
    embedder = OllamaEmbedder(BGE_M3, host="http://x", client=client, sleep=lambda _s: None)
    assert len(embedder.embed_documents(["a"])) == 1
    assert calls["n"] == 3


def test_client_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def bad(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"error": "model not found"})

    client = httpx.Client(transport=httpx.MockTransport(bad))
    embedder = OllamaEmbedder(BGE_M3, host="http://x", client=client, sleep=lambda _s: None)
    with pytest.raises(EmbedError):
        embedder.embed_documents(["a"])
    assert calls["n"] == 1


def test_vector_literal_round_trips_precision() -> None:
    assert vector_literal([0.1, -2.0, 1e-9]) == "[0.1,-2,1e-09]"


def _result(model: str, hits5: int, n: int = 30) -> ModelResult:
    return ModelResult(model, False, n, {1: hits5, 3: hits5, 5: hits5, 10: hits5}, 1.0)


def test_report_applies_the_tie_rule() -> None:
    close = render([_result("a", 24), _result("b", 23)])
    assert "tie margin" in close
    far = render([_result("a", 27), _result("b", 20)])
    assert "higher is a" in far
    assert "tie margin" not in far


def test_dev_items_exclude_the_hold_out() -> None:
    gold = _tiny_gold()
    assert [i.id for i in dev_items(gold)] == ["G-T-001"]


# --- database needed ---------------------------------------------------------------------------

TEXTS = {
    1: "Federally regulated institutions must manage model risk across the model lifecycle.",
    2: "Suspicious transaction reports must be submitted to FINTRAC as soon as practicable.",
    3: "Cyber security incidents must be reported to the supervisor within 24 hours.",
}


def _item(item_id: str, split: str, question: str, chunk: int) -> AnswerableItem:
    return AnswerableItem.model_validate(
        {
            "id": item_id,
            "split": split,
            "type": "lookup",
            "question": question,
            "kind": "answerable",
            "source": "A-TEST",
            "difficulty": "easy",
            "key_points": ["a point"],
            "pass_rule": {"min_points": 1, "text": "one point"},
            "supporting_chunks": [make_chunk(n=chunk).chunk_id],
        }
    )


def _tiny_gold() -> GoldSet:
    sha = "a" * 12
    return GoldSet.model_validate(
        {
            "version": 1,
            "dataset": "tiny",
            "created": "2026-11-23",
            "labelling": "test",
            "split_seed": 1,
            "split_method": "test",
            "corpus": {
                "A-TEST": {
                    "raw_sha256_prefix": sha,
                    "page_date": "n/a",
                    "retrieved": "2026-11-01",
                    "url": "https://example.test",
                }
            },
            "items": [
                _item("G-T-001", "dev", "Which reports go to FINTRAC?", 2).model_dump(),
                _item("G-T-002", "holdout", "How is model risk managed?", 1).model_dump(),
            ],
        }
    )


def _load_three(conn: Conn, tmp_path: Path) -> None:
    chunks = tuple(make_chunk(n=n, text=t) for n, t in TEXTS.items())
    load_source(conn, "A-TEST", write_chunks(tmp_path, chunks, "1"))


@needs_db
def test_index_embeds_everything_once(migrated: Conn, tmp_path: Path) -> None:
    _load_three(migrated, tmp_path)
    first = index_model(migrated, HashingEmbedder(), batch_size=2)
    assert (first.embedded, first.already_done) == (3, 0)
    again = index_model(migrated, HashingEmbedder())
    assert (again.embedded, again.already_done) == (0, 3)
    assert embedded_by_model(migrated) == [("bge-m3", 3)]
    assert counts(migrated) == [("A-TEST", 3, 3)]


class _FailsOnSecondBatch(HashingEmbedder):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.calls >= 1:
            raise EmbedError("server went away")
        return super().embed_documents(texts)


@needs_db
def test_a_failed_run_keeps_finished_batches_and_can_resume(migrated: Conn, tmp_path: Path) -> None:
    _load_three(migrated, tmp_path)
    with pytest.raises(EmbedError):
        index_model(migrated, _FailsOnSecondBatch(), batch_size=2)
    assert embedded_by_model(migrated) == [("bge-m3", 2)]
    resumed = index_model(migrated, HashingEmbedder(), batch_size=2)
    assert (resumed.embedded, resumed.already_done) == (1, 2)


@needs_db
def test_models_are_kept_separate(migrated: Conn, tmp_path: Path) -> None:
    _load_three(migrated, tmp_path)
    index_model(migrated, HashingEmbedder(BGE_M3))
    assert embedded_by_model(migrated) == [("bge-m3", 3)]
    index_model(migrated, HashingEmbedder(QWEN3_06B))
    assert embedded_by_model(migrated) == [("bge-m3", 3), ("qwen3-embedding:0.6b", 3)]


@needs_db
def test_search_ranks_by_meaning_and_ignores_superseded(migrated: Conn, tmp_path: Path) -> None:
    _load_three(migrated, tmp_path)
    embedder = HashingEmbedder()
    index_model(migrated, embedder)
    [query] = embedder.embed_queries(["suspicious transaction reports to FINTRAC"])
    ranked = dense_search(migrated, "bge-m3", query, 3)
    assert ranked[0] == make_chunk(n=2).chunk_id
    assert len(ranked) == 3
    # a newer page version supersedes all three: nothing current remains to find
    newer = write_chunks(tmp_path / "v2", (make_chunk(sha="b" * 64, n=1, text="Other."),), "1")
    load_source(migrated, "A-TEST", newer)
    assert dense_search(migrated, "bge-m3", query, 3) == []


@needs_db
def test_evaluate_model_scores_hits_and_misses(migrated: Conn, tmp_path: Path) -> None:
    """Support is matched by section, so the look-alikes and the answer sit in different ones."""

    def in_section(chunk: Chunk, section: int, text: str) -> Chunk:
        chunk_id = chunk.chunk_id.replace(":s001:", f":s{section:03d}:")
        return chunk.model_copy(
            update={"chunk_id": chunk_id, "section_index": section, "text": text}
        )

    base = tuple(make_chunk(n=n, text=t) for n, t in TEXTS.items())  # all section 1
    lookalikes = tuple(
        in_section(make_chunk(n=n), 2, f"Cyber security incident reporting deadlines, variant {n}.")
        for n in range(4, 10)
    )
    retention = in_section(make_chunk(n=10), 3, "Records must be retained for five years.")
    load_source(migrated, "A-TEST", write_chunks(tmp_path, (*base, *lookalikes, retention), "1"))
    embedder = HashingEmbedder()
    index_model(migrated, embedder)
    hit = _item("G-T-001", "dev", "Which suspicious transaction reports go to FINTRAC?", 2)
    miss = AnswerableItem.model_validate(
        {
            **_item(
                "G-T-003", "dev", "What are cyber security incident reporting deadlines?", 2
            ).model_dump(),
            "supporting_chunks": [retention.chunk_id],  # the answer is in section 3
        }
    )
    result = evaluate_model(migrated, embedder, [hit, miss])
    assert result.is_test_double
    assert result.n == 2
    assert result.hits[1] == 1
    assert result.hits[5] == 1
    assert result.misses_at_5 == ["G-T-003"]
    assert result.by_source == {"A-TEST": (1, 2)}


@needs_db
def test_missing_support_flags_other_page_versions(migrated: Conn, tmp_path: Path) -> None:
    _load_three(migrated, tmp_path)
    present = _item("G-T-001", "dev", "Which reports go to FINTRAC?", 2)
    elsewhere = AnswerableItem.model_validate(
        {
            **present.model_dump(),
            "id": "G-T-009",
            "supporting_chunks": ["A-TEST:ffffffffffff:s001:c001"],
        }
    )
    assert missing_support(migrated, [present, elsewhere]) == ["G-T-009"]
