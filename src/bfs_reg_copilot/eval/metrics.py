"""Pure scoring rules. No I/O, so each rule can be tested on its own.

M1 cited-answer accuracy, M2 correct refusal, M4 retrieval hit@k, M5 fabricated citations.
Definitions: docs/02-success-metrics.md. Judgement of key points stays with a person (or, later, a
judge model that has been checked against people); everything else here is mechanical.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from bfs_reg_copilot.eval.gold import AnswerableItem
from bfs_reg_copilot.eval.types import PipelineAnswer

DEFAULT_K = 5


def section_id(chunk_id: str) -> str:
    """`<source>:<page hash>:s###`: the section of a chunk (its chunks share it)."""
    return ":".join(chunk_id.split(":")[:3])


def support_sections(item: AnswerableItem) -> frozenset[str]:
    return frozenset(section_id(c) for c in item.supporting_chunks)


def cites_support(item: AnswerableItem, answer: PipelineAnswer) -> bool:
    """M1 needs at least one cited section that holds the support."""
    wanted = support_sections(item)
    return any(section_id(c) in wanted for c in answer.cited_chunks)


def hit_at_k(item: AnswerableItem, answer: PipelineAnswer, k: int = DEFAULT_K) -> bool:
    """M4: a supporting section appears among the first k retrieved chunks."""
    wanted = support_sections(item)
    return any(section_id(c) in wanted for c in answer.retrieved_chunks[:k])


def fabricated_citations(answer: PipelineAnswer) -> tuple[str, ...]:
    """M5: cited chunks whose section is not in what was retrieved for this question."""
    seen = {section_id(c) for c in answer.retrieved_chunks}
    return tuple(c for c in answer.cited_chunks if section_id(c) not in seen)


def points_ok(item: AnswerableItem, points_hit: Iterable[int]) -> bool:
    """The item's pass rule: enough key points, including every required one."""
    hit = set(points_hit)
    rule = item.pass_rule
    return len(hit) >= rule.min_points and set(rule.required_points) <= hit


def wilson_interval(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. With 40 questions a few points of difference is noise."""
    if total == 0:
        return (0.0, 0.0)
    p = passed / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]
