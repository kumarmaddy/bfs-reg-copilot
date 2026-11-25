"""Compare two runs of the same gold set, question by question, against a stated decision rule.

A change is judged by which questions flip, not only by the totals: the same questions are asked
of both versions, so what matters is how many go from fail to pass and how many the other way.
The rule is written before the run (docs/20) and passed in; this module only applies it.
"""

from __future__ import annotations

from dataclasses import dataclass

from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet
from bfs_reg_copilot.eval.grading import Grades
from bfs_reg_copilot.eval.metrics import fabricated_citations, percentile
from bfs_reg_copilot.eval.report import m1_outcome
from bfs_reg_copilot.eval.types import RunMeta, RunRecord


class CompareError(Exception):
    """The two runs cannot be compared fairly."""


@dataclass(frozen=True)
class Rule:
    """Defaults are the rule pre-registered for experiment 3.1 in docs/20."""

    min_fixed: int = 4
    max_broken: int = 1
    max_refusal_rise: int = 1
    max_p95_s: float = 32.0
    proven_fixed: int = 6  # about the number of clean flips a sign test on 32 questions needs


@dataclass(frozen=True)
class Comparison:
    fixed: tuple[str, ...]
    broken: tuple[str, ...]
    still_pass: int
    still_fail: int
    refused_before: int
    refused_after: int
    fabricated_after: int
    p95_before: float
    p95_after: float
    settings_changed: dict[str, tuple[str, str]]


def _outcomes(
    gold: GoldSet, records: list[RunRecord], grades: Grades, label: str
) -> dict[str, bool]:
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    result: dict[str, bool] = {}
    pending: list[str] = []
    for record in records:
        item = items.get(record.item_id)
        if item is None:
            continue
        outcome = m1_outcome(item, record, grades)
        if outcome is None:
            pending.append(record.item_id)
        else:
            result[record.item_id] = outcome
    if pending:
        raise CompareError(
            f"{label} has {len(pending)} answers still to grade: {', '.join(sorted(pending))}"
        )
    return result


def compare_runs(
    gold: GoldSet,
    before: tuple[RunMeta, list[RunRecord], Grades],
    after: tuple[RunMeta, list[RunRecord], Grades],
) -> Comparison:
    meta_a, rec_a, grades_a = before
    meta_b, rec_b, grades_b = after
    if meta_a.gold_sha256 != meta_b.gold_sha256:
        raise CompareError("the runs used different gold files; re-score one of them first")
    if meta_a.split != meta_b.split:
        raise CompareError("the runs used different splits")
    if {r.item_id for r in rec_a} != {r.item_id for r in rec_b}:
        raise CompareError("the runs cover different questions (was --limit used on one?)")
    out_a = _outcomes(gold, rec_a, grades_a, "the first run")
    out_b = _outcomes(gold, rec_b, grades_b, "the second run")
    fixed = tuple(sorted(i for i in out_a if not out_a[i] and out_b[i]))
    broken = tuple(sorted(i for i in out_a if out_a[i] and not out_b[i]))
    answerable = set(out_a)

    def refused(records: list[RunRecord]) -> int:
        return sum(
            1
            for r in records
            if r.item_id in answerable and r.answer is not None and r.answer.refused
        )

    changed = {
        key: (meta_a.settings.get(key, "-"), meta_b.settings.get(key, "-"))
        for key in sorted(set(meta_a.settings) | set(meta_b.settings))
        if meta_a.settings.get(key) != meta_b.settings.get(key)
    }
    return Comparison(
        fixed=fixed,
        broken=broken,
        still_pass=sum(1 for i in out_a if out_a[i] and out_b[i]),
        still_fail=sum(1 for i in out_a if not out_a[i] and not out_b[i]),
        refused_before=refused(rec_a),
        refused_after=refused(rec_b),
        fabricated_after=sum(len(fabricated_citations(r.answer)) for r in rec_b if r.answer),
        p95_before=percentile([r.latency_s for r in rec_a], 0.95),
        p95_after=percentile([r.latency_s for r in rec_b], 0.95),
        settings_changed=changed,
    )


def apply_rule(c: Comparison, rule: Rule) -> list[tuple[str, bool]]:
    return [
        (
            f"(a) at least {rule.min_fixed} fixed and at most {rule.max_broken} broken "
            f"(fixed {len(c.fixed)}, broken {len(c.broken)})",
            len(c.fixed) >= rule.min_fixed and len(c.broken) <= rule.max_broken,
        ),
        (f"(b) no fabricated citations ({c.fabricated_after})", c.fabricated_after == 0),
        (
            f"(c) refusals of answerable questions rise by at most {rule.max_refusal_rise} "
            f"({c.refused_before} to {c.refused_after})",
            c.refused_after - c.refused_before <= rule.max_refusal_rise,
        ),
        (
            f"(d) p95 latency at most {rule.max_p95_s:.0f}s "
            f"({c.p95_before:.1f}s to {c.p95_after:.1f}s)",
            c.p95_after <= rule.max_p95_s,
        ),
    ]


def render(c: Comparison, rule: Rule) -> list[str]:
    lines = ["Settings that differ between the runs:"]
    lines += [f"  {k}: {a} -> {b}" for k, (a, b) in c.settings_changed.items()] or ["  none"]
    lines.append(f"Questions: {c.still_pass} pass in both, {c.still_fail} fail in both")
    lines.append(f"Fixed (fail to pass): {', '.join(c.fixed) or 'none'}")
    lines.append(f"Broken (pass to fail): {', '.join(c.broken) or 'none'}")
    lines.append("Decision rule:")
    results = apply_rule(c, rule)
    lines += [f"  {'PASS' if ok else 'FAIL'}  {text}" for text, ok in results]
    if all(ok for _, ok in results):
        if len(c.fixed) - len(c.broken) >= rule.proven_fixed:
            lines.append("Verdict: adopt. The net gain is large enough to be more than noise.")
        else:
            lines.append(
                "Verdict: promising, not proven. The rule is met but the net gain is under "
                f"{rule.proven_fixed}; re-test on a larger dev set before relying on it."
            )
    else:
        lines.append("Verdict: do not adopt. At least one condition of the rule failed.")
    return lines
