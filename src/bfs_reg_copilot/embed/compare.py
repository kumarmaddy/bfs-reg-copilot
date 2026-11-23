"""Compare embedding models on retrieval only: hit@k on the dev split of the gold set.

Deliberately blind to the hold-out (ADR-0014): the model is a tuning choice, so it is chosen on
dev. Decision rule, fixed before looking at numbers: pick the model with the higher dev hit@5; if
the two are within 5 percentage points, pick the one that embeds faster. With about 30 dev
questions the intervals overlap heavily, so a small gap is noise and the tie rule decides.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from bfs_reg_copilot.embed.ollama import Embedder
from bfs_reg_copilot.embed.search import dense_search
from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet, Split
from bfs_reg_copilot.eval.metrics import (
    hit_at_k,
    percentile,
    section_id,
    support_sections,
    wilson_interval,
)
from bfs_reg_copilot.eval.types import PipelineAnswer
from bfs_reg_copilot.store.db import Conn

KS = (1, 3, 5, 10)
TIE_MARGIN = 0.05


@dataclass
class ModelResult:
    model: str
    is_test_double: bool
    n: int
    hits: dict[int, int]
    query_seconds: float
    misses_at_5: list[str] = field(default_factory=list)
    by_source: dict[str, tuple[int, int]] = field(default_factory=dict)  # source -> (hit@5, n)
    latencies: list[float] = field(default_factory=list)  # seconds per question, if measured

    def rate(self, k: int) -> float:
        return self.hits[k] / self.n if self.n else 0.0


def dev_items(gold: GoldSet) -> tuple[AnswerableItem, ...]:
    return tuple(i for i in gold.items if isinstance(i, AnswerableItem) and i.split == Split.DEV)


def missing_support(conn: Conn, items: Sequence[AnswerableItem]) -> list[str]:
    """Items whose supporting sections are not in the database's current chunks."""
    cur = conn.cursor()
    cur.execute("SELECT chunk_id FROM chunks WHERE superseded_at IS NULL")
    present = {section_id(str(r[0])) for r in cur.fetchall()}
    return [i.id for i in items if not support_sections(i) <= present]


def score_rankings(
    items: Sequence[AnswerableItem], rankings: Sequence[Sequence[str]]
) -> tuple[dict[int, int], list[str], dict[str, tuple[int, int]]]:
    """hits per k, ids missed at 5, and (hit@5, n) per source, for one ranking per item."""
    hits = dict.fromkeys(KS, 0)
    misses: list[str] = []
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item, ranking in zip(items, rankings, strict=True):
        answer = PipelineAnswer(text="", refused=False, retrieved_chunks=tuple(ranking))
        for k in KS:
            hits[k] += hit_at_k(item, answer, k)
        ok5 = hit_at_k(item, answer, 5)
        by_source[item.source][0] += ok5
        by_source[item.source][1] += 1
        if not ok5:
            misses.append(item.id)
    return hits, misses, {s: (a, b) for s, (a, b) in by_source.items()}


def evaluate_model(conn: Conn, embedder: Embedder, items: Sequence[AnswerableItem]) -> ModelResult:
    started = time.monotonic()
    vectors = embedder.embed_queries([i.question for i in items])
    elapsed = time.monotonic() - started
    rankings = [dense_search(conn, embedder.model.name, v, max(KS)) for v in vectors]
    hits, misses, by_source = score_rankings(items, rankings)
    return ModelResult(
        embedder.model.name, embedder.is_test_double, len(items), hits, elapsed, misses, by_source
    )


def render(results: Sequence[ModelResult]) -> str:
    lines = ["Retrieval comparison on the DEV split (hit@k, section level)", ""]
    for r in results:
        label = " (TEST DOUBLE)" if r.is_test_double else ""
        lines.append(f"{r.model}{label}: {r.n} dev questions, query time {r.query_seconds:.1f}s")
        for k in KS:
            lo, hi = wilson_interval(r.hits[k], r.n)
            lines.append(
                f"  hit@{k:<2} {r.hits[k]:>3}/{r.n}  {r.rate(k):6.1%}  95% CI {lo:.0%}-{hi:.0%}"
            )
        per_source = ", ".join(f"{s} {a}/{b}" for s, (a, b) in sorted(r.by_source.items()))
        lines.append(f"  hit@5 by source: {per_source}")
        if r.latencies:
            p50, p95 = percentile(r.latencies, 0.5), percentile(r.latencies, 0.95)
            lines.append(
                f"  latency per question: p50 {p50 * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms"
            )
        lines.append(f"  missed at 5: {', '.join(r.misses_at_5) or 'none'}")
        lines.append("")
    if len(results) == 2:
        a, b = results
        gap = a.rate(5) - b.rate(5)
        if abs(gap) < TIE_MARGIN:
            lines.append(
                f"hit@5 gap is {abs(gap):.1%}, inside the {TIE_MARGIN:.0%} tie margin: choose the "
                "model that embeds faster (see the indexing times)."
            )
        else:
            winner = a if gap > 0 else b
            lines.append(f"hit@5 gap is {abs(gap):.1%}: higher is {winner.model}.")
    return "\n".join(lines)
