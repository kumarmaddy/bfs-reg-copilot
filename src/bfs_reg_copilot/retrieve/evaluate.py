"""Compare retrievers (dense, keyword, hybrid) on the dev split: hit@k and latency.

Rule fixed before any hybrid or keyword number was seen (dense-only was already known: 30 of 32 at
hit@5): hybrid replaces dense-only only if its hit@5 does not drop AND it gains at least one
question at hit@5 or at least two at hit@3. Otherwise dense-only stays, because it is simpler to
run and to explain. Dev only; the hold-out stays sealed (ADR-0014).
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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


RANK_DEPTH = 50
COVERAGE_KS = (5, 8, 10, 20, 50)


@dataclass(frozen=True)
class SupportRank:
    """Where one gold supporting chunk lands in one retriever's ranking (None: beyond the depth)."""

    item_id: str
    chunk_id: str
    ranks: Mapping[str, int | None]  # retriever name -> 1-based rank


def support_ranks(
    retrievers: Mapping[str, Retriever], items: Sequence[AnswerableItem], depth: int = RANK_DEPTH
) -> list[SupportRank]:
    """For every supporting chunk of every item, its rank under each retriever, down to `depth`."""
    rows: list[SupportRank] = []
    for item in items:
        ranking = {
            name: [h.chunk_id for h in r.retrieve(item.question, depth)]
            for name, r in retrievers.items()
        }
        for chunk_id in item.supporting_chunks:
            ranks = {
                name: (listing.index(chunk_id) + 1 if chunk_id in listing else None)
                for name, listing in ranking.items()
            }
            rows.append(SupportRank(item.id, chunk_id, ranks))
    return rows


def all_support_within(rows: Sequence[SupportRank], name: str, k: int) -> tuple[int, int]:
    """(items whose every supporting chunk is in the top k, items). Stricter than hit@k."""
    by_item: dict[str, list[bool]] = {}
    for row in rows:
        rank = row.ranks[name]
        by_item.setdefault(row.item_id, []).append(rank is not None and rank <= k)
    return sum(all(v) for v in by_item.values()), len(by_item)


def render_ranks(
    rows: Sequence[SupportRank], names: Sequence[str], detail_for: Sequence[str]
) -> list[str]:
    """A coverage table over all items, then the rank of each supporting chunk for `detail_for`."""
    header = "every supporting chunk within the top k (items):"
    lines = [header, "k      " + "  ".join(f"{n.split(':')[0]:>9}" for n in names)]
    for k in COVERAGE_KS:
        cells = []
        for name in names:
            got, total = all_support_within(rows, name, k)
            cells.append(f"{got:>5}/{total:<3}")
        lines.append(f"{k:<6} " + "  ".join(cells))
    lines += ["", "rank of each supporting chunk (blank: beyond the depth):"]
    for row in rows:
        if row.item_id not in detail_for:
            continue
        cells = []
        for n in names:
            rank = row.ranks[n]
            cells.append(f"{n.split(':')[0]} {rank if rank is not None else f'>{RANK_DEPTH}'}")
        shown = "  ".join(cells)
        lines.append(f"{row.item_id:<10} {row.chunk_id.split(':', 1)[1]:<26} {shown}")
    return lines


RERANK_MIN_COVERED = 30  # pre-registered (doc 20): dense covers 27 of 32 at the top 5


def rerank_verdict(
    rows: Sequence[SupportRank],
    reranked: str,
    dense: str,
    k: int = 5,
    needed: int = RERANK_MIN_COVERED,
) -> str:
    got, total = all_support_within(rows, reranked, k)
    base, _ = all_support_within(rows, dense, k)
    detail = f"every supporting chunk in the top {k}: {base} -> {got} of {total}"
    if got >= needed:
        return f"Stage 1 rule met ({detail}; needs {needed}): go on to the generator run."
    return f"Stage 1 rule not met ({detail}; needs {needed}): drop the reranker for this baseline."
