"""Retriever tests: rank fusion (pure), keyword and dense search, hybrid, and the comparison.

Database tests run only when BFS_TEST_DATABASE_URL is set (see test_store.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bfs_reg_copilot.embed.compare import ModelResult
from bfs_reg_copilot.embed.fakes import HashingEmbedder
from bfs_reg_copilot.embed.indexer import index_model
from bfs_reg_copilot.embed.search import dense_scored, fulltext_scored
from bfs_reg_copilot.eval.gold import AnswerableItem
from bfs_reg_copilot.ingest.chunk_store import write_chunks
from bfs_reg_copilot.ingest.chunking import Chunk
from bfs_reg_copilot.retrieve.evaluate import (
    evaluate_retriever,
    hybrid_verdict,
    render_comparison,
)
from bfs_reg_copilot.retrieve.retrievers import (
    DenseRetriever,
    FullTextRetriever,
    HybridRetriever,
    make_retrievers,
    rrf,
)
from bfs_reg_copilot.store.db import Conn
from bfs_reg_copilot.store.loader import load_source
from dbhelpers import make_chunk as _make_chunk
from dbhelpers import needs_db

SRC = "A-TEST"


def make_chunk(**kwargs: Any) -> Chunk:
    return _make_chunk(source=SRC, **kwargs)


# --- no database needed ------------------------------------------------------------------------


def test_rrf_rewards_agreement_between_lists() -> None:
    fused = rrf([["a", "b", "c"], ["c", "d", "a"]])
    assert [h.chunk_id for h in fused][:2] == ["a", "c"]  # in both lists, so ahead of b and d
    assert {h.chunk_id for h in fused} == {"a", "b", "c", "d"}


def test_rrf_score_formula_and_tie_break() -> None:
    fused = rrf([["x"], ["y"]], k=60)
    assert [h.chunk_id for h in fused] == ["x", "y"]  # equal scores: chunk id order
    assert fused[0].score == pytest.approx(1 / 61)
    both = rrf([["x", "y"], ["x"]], k=10)
    assert both[0].score == pytest.approx(2 / 11)


def test_rrf_handles_empty_input() -> None:
    assert rrf([]) == []
    assert rrf([[], []]) == []
    assert [h.chunk_id for h in rrf([[], ["only"]])] == ["only"]


def _result(name: str, h3: int, h5: int, n: int = 32) -> ModelResult:
    return ModelResult(name, False, n, {1: 0, 3: h3, 5: h5, 10: h5}, 1.0)


@pytest.mark.parametrize(
    ("hybrid", "adopt"),
    [
        ((29, 30), False),  # no change: keep dense-only
        ((29, 31), True),  # one more at hit@5
        ((31, 30), True),  # two more at hit@3, hit@5 held
        ((30, 30), False),  # one more at hit@3 is not enough
        ((31, 29), False),  # hit@5 dropped, whatever hit@3 did
    ],
)
def test_hybrid_rule(hybrid: tuple[int, int], adopt: bool) -> None:
    verdict = hybrid_verdict(_result("dense:m", 29, 30), _result("hybrid:m", *hybrid))
    assert ("adopt hybrid" in verdict) is adopt


def test_comparison_report_ends_with_the_verdict() -> None:
    text = render_comparison([_result("dense:m", 29, 30), _result("hybrid:m", 29, 31)])
    assert text.startswith("Retriever comparison on the DEV split")
    assert text.rstrip().endswith("adopt hybrid.")


# --- database needed ---------------------------------------------------------------------------

TEXTS = {
    1: "Federally regulated institutions must manage model risk across the model lifecycle.",
    2: "Suspicious transaction reports must be submitted to FINTRAC as soon as practicable.",
    3: "Cyber security incidents must be reported to the supervisor within 24 hours.",
}


def _load(conn: Conn, tmp_path: Path, extra: tuple[Chunk, ...] = ()) -> None:
    base = tuple(make_chunk(n=n, text=t) for n, t in TEXTS.items())
    load_source(conn, SRC, write_chunks(tmp_path, base + extra, "1"))


@needs_db
def test_fulltext_matches_stems_and_uses_or_semantics(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    # words are stemmed ("reporting" matches "reports"); unrelated words do not prevent a match
    hits = fulltext_scored(migrated, "Where do I submit the reporting of suspicious items?", 5)
    assert hits[0][0] == make_chunk(n=2).chunk_id
    assert hits[0][1] > 0


@needs_db
def test_fulltext_edge_cases(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    assert fulltext_scored(migrated, "the of and to", 5) == []  # only stop words
    assert fulltext_scored(migrated, "", 5) == []
    assert fulltext_scored(migrated, "zzzxqy", 5) == []  # no match
    awkward = "What's the 'FINTRAC' <STR> (report)? a|b & c! :* \\ ;--"
    assert isinstance(fulltext_scored(migrated, awkward, 5), list)  # must not raise


@needs_db
def test_fulltext_ignores_superseded_chunks(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    newer = write_chunks(
        tmp_path / "v2", (make_chunk(sha="b" * 64, text="Nothing relevant."),), "1"
    )
    load_source(migrated, SRC, newer)
    assert fulltext_scored(migrated, "suspicious transaction reports", 5) == []


@needs_db
def test_dense_scores_are_similarities(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    embedder = HashingEmbedder()
    index_model(migrated, embedder)
    [vector] = embedder.embed_queries(["Suspicious transaction reports FINTRAC"])
    scored = dense_scored(migrated, "bge-m3", vector, 3)
    assert scored[0][0] == make_chunk(n=2).chunk_id
    similarities = [s for _, s in scored]
    assert similarities == sorted(similarities, reverse=True)
    assert all(-1.0 <= s <= 1.0001 for s in similarities)


@needs_db
def test_hybrid_puts_the_chunk_both_lists_agree_on_first(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    embedder = HashingEmbedder()
    index_model(migrated, embedder)
    retrievers = make_retrievers(migrated, embedder)
    hybrid = retrievers["hybrid"]
    assert isinstance(hybrid, HybridRetriever)
    hits = hybrid.retrieve("When must suspicious transaction reports be submitted to FINTRAC?", 3)
    assert hits[0].chunk_id == make_chunk(n=2).chunk_id
    assert len(hits) <= 3
    assert isinstance(retrievers["dense"], DenseRetriever)
    assert isinstance(retrievers["fulltext"], FullTextRetriever)
    assert hybrid.is_test_double  # built on the hashing stand-in, so labelled as such
    assert hybrid.name == "hybrid:bge-m3"


@needs_db
def test_hybrid_still_answers_when_keywords_find_nothing(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    embedder = HashingEmbedder()
    index_model(migrated, embedder)
    hybrid = make_retrievers(migrated, embedder)["hybrid"]
    hits = hybrid.retrieve("zzzxqy", 3)  # no keyword match; dense search still returns candidates
    assert len(hits) == 3


@needs_db
def test_evaluate_retriever_scores_and_times_each_question(migrated: Conn, tmp_path: Path) -> None:
    _load(migrated, tmp_path)
    embedder = HashingEmbedder()
    index_model(migrated, embedder)
    item = AnswerableItem.model_validate(
        {
            "id": "G-T-001",
            "split": "dev",
            "type": "lookup",
            "question": "When must suspicious transaction reports go to FINTRAC?",
            "kind": "answerable",
            "source": SRC,
            "difficulty": "easy",
            "key_points": ["a point"],
            "pass_rule": {"min_points": 1, "text": "one point"},
            "supporting_chunks": [make_chunk(n=2).chunk_id],
        }
    )
    result = evaluate_retriever(make_retrievers(migrated, embedder)["fulltext"], [item])
    assert result.model == "fulltext"
    assert (result.n, result.hits[1], result.hits[5]) == (1, 1, 1)
    assert len(result.latencies) == 1
    assert result.latencies[0] >= 0
