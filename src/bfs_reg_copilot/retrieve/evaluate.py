"""Compare retrievers (dense, keyword, hybrid) on the dev split: hit@k and latency.

Rule fixed before any hybrid or keyword number was seen (dense-only was already known: 30 of 32 at
hit@5): hybrid replaces dense-only only if its hit@5 does not drop AND it gains at least one
question at hit@5 or at least two at hit@3. Otherwise dense-only stays, because it is simpler to
run and to explain. Dev only; the hold-out stays sealed (ADR-0014).
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from bfs_reg_copilot.embed.compare import ModelResult, render, score_rankings
from bfs_reg_copilot.eval.gold import AnswerableItem
from bfs_reg_copilot.retrieve.types import Retriever

MAX_K = 10


def evaluate_retriever(retriever: Retriever, items: Sequence[AnswerableItem]) -> ModelResult:
    rankings: list[list[str]] = []
    latencies: list[float] = []
    for item in items:
        started = time.monotonic()
        hits = retriever.retrieve(item.question, MAX_K)
        latencies.append(time.monotonic() - started)
        rankings.append([h.chunk_id for h in hits])
    hits_per_k, misses, by_source = score_rankings(items, rankings)
    return ModelResult(
        retriever.name,
        retriever.is_test_double,
        len(items),
        hits_per_k,
        sum(latencies),
        misses,
        by_source,
        latencies,
    )


def hybrid_verdict(dense: ModelResult, hybrid: ModelResult) -> str:
    d5, h5 = dense.hits[5], hybrid.hits[5]
    gain3 = hybrid.hits[3] - dense.hits[3]
    adopt = h5 >= d5 and (h5 > d5 or gain3 >= 2)
    detail = f"hit@5 {d5} -> {h5}, hit@3 {dense.hits[3]} -> {hybrid.hits[3]} (of {dense.n})"
    if adopt:
        return f"hybrid meets the rule ({detail}): adopt hybrid."
    return f"hybrid does not meet the rule ({detail}): keep dense-only."


def render_comparison(results: Sequence[ModelResult]) -> str:
    text = render(results).replace(
        "Retrieval comparison on the DEV split", "Retriever comparison on the DEV split"
    )
    by_prefix = {r.model.split(":")[0]: r for r in results}
    if "dense" in by_prefix and "hybrid" in by_prefix:
        text += "\n\n" + hybrid_verdict(by_prefix["dense"], by_prefix["hybrid"])
    return text
