"""Turn a run (and optional human grades) into the numbers of docs/02: M1, M2, M4, M5, M8."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bfs_reg_copilot.eval.gold import AdversarialItem, AnswerableItem, GoldSet, RefusalItem
from bfs_reg_copilot.eval.grading import Grades
from bfs_reg_copilot.eval.metrics import (
    cites_support,
    fabricated_citations,
    hit_at_k,
    percentile,
    points_ok,
    wilson_interval,
)
from bfs_reg_copilot.eval.types import RunMeta, RunRecord


@dataclass(frozen=True)
class Rate:
    passed: int
    total: int

    @property
    def value(self) -> float | None:
        return self.passed / self.total if self.total else None

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.passed, self.total)

    def text(self) -> str:
        if not self.total:
            return "n/a (0 items)"
        low, high = self.interval
        share = self.passed / self.total
        return f"{self.passed}/{self.total} = {share:.0%} (95% CI {low:.0%} to {high:.0%})"


@dataclass(frozen=True)
class Report:
    meta: RunMeta
    m1: Rate
    m1_ungraded: int
    m2: Rate
    m4: Rate
    citations: int
    fabricated: int
    adversarial: Rate
    adversarial_pending: int
    errors: int
    latency_p50: float
    latency_p95: float
    by_source: dict[str, tuple[Rate, Rate]]  # source -> (M1 over graded, M4)
    # Answerable questions the system refused. Lower is better; it is the cost side of M2.
    over_refusal: Rate = Rate(0, 0)


def m1_outcome(item: AnswerableItem, record: RunRecord, grades: Grades) -> bool | None:
    """True/False once decided, None while a person still has to grade the answer."""
    answer = record.answer
    if answer is None or answer.refused or not cites_support(item, answer):
        return False  # fails a mechanical rule, no person needed
    if item.id in grades.points:
        return item.id not in grades.contradicts and points_ok(item, grades.points[item.id])
    return None


def build_report(gold: GoldSet, meta: RunMeta, records: list[RunRecord], grades: Grades) -> Report:
    by_id = {i.id: i for i in gold.items}
    m1_pass = m1_total = ungraded = 0
    m2_pass = m2_total = 0
    m4_pass = m4_total = 0
    over_refused = answerable_total = 0
    adv_pass = adv_total = adv_pending = 0
    citations = fabricated = errors = 0
    per_source: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # m1 p, m1 n, m4 p, m4 n
    for record in records:
        item = by_id[record.item_id]
        answer = record.answer
        if record.error or answer is None:
            errors += 1
        else:
            citations += len(answer.cited_chunks)
            fabricated += len(fabricated_citations(answer))
        if isinstance(item, AnswerableItem):
            row = per_source[item.source]
            hit = answer is not None and hit_at_k(item, answer)
            m4_total += 1
            m4_pass += hit
            answerable_total += 1
            over_refused += answer is not None and answer.refused
            row[2] += hit
            row[3] += 1
            graded_ok = m1_outcome(item, record, grades)
            if graded_ok is None:
                ungraded += 1
            else:
                m1_total += 1
                m1_pass += graded_ok
                row[0] += graded_ok
                row[1] += 1
        elif isinstance(item, RefusalItem):
            m2_total += 1
            m2_pass += answer is not None and answer.refused
        elif isinstance(item, AdversarialItem):
            if item.id in grades.verdicts:
                adv_total += 1
                adv_pass += grades.verdicts[item.id]
            else:
                adv_pending += 1
    latencies = [r.latency_s for r in records]
    return Report(
        meta=meta,
        m1=Rate(m1_pass, m1_total),
        m1_ungraded=ungraded,
        m2=Rate(m2_pass, m2_total),
        m4=Rate(m4_pass, m4_total),
        citations=citations,
        fabricated=fabricated,
        adversarial=Rate(adv_pass, adv_total),
        adversarial_pending=adv_pending,
        errors=errors,
        latency_p50=percentile(latencies, 0.50),
        latency_p95=percentile(latencies, 0.95),
        by_source={s: (Rate(v[0], v[1]), Rate(v[2], v[3])) for s, v in sorted(per_source.items())},
        over_refusal=Rate(over_refused, answerable_total),
    )


def render_report(report: Report) -> list[str]:
    meta = report.meta
    lines = [f"Run {meta.run_id}   split {meta.split.value}   pipeline {meta.pipeline}"]
    if meta.is_test_double:
        lines.append("TEST DOUBLE: these numbers check the scorer, they are not a system result.")
    lines.append(f"commit {meta.git_commit}   gold v{meta.gold_version} {meta.gold_sha256[:12]}")
    lines.append(f"M1 cited-answer accuracy   {report.m1.text()}")
    if report.m1_ungraded:
        lines.append(
            f"   {report.m1_ungraded} answers still need a person; M1 covers graded ones only"
        )
    lines.append(f"M2 correct refusal         {report.m2.text()}")
    lines.append(
        f"   over-refusal (answerable but refused; lower is better)  {report.over_refusal.text()}"
    )
    lines.append(f"M4 retrieval hit@5         {report.m4.text()}")
    rate = f"{report.fabricated / report.citations:.1%}" if report.citations else "n/a"
    lines.append(f"M5 fabricated citations    {report.fabricated}/{report.citations} = {rate}")
    lines.append(
        f"M8 adversarial passed      {report.adversarial.text()}"
        + (f"; {report.adversarial_pending} not graded" if report.adversarial_pending else "")
    )
    lines.append(
        f"errors {report.errors}   latency p50 {report.latency_p50:.2f}s "
        f"p95 {report.latency_p95:.2f}s"
    )
    lines.append("by source (M1 graded, M4):")
    lines += [
        f"  {source:<14} M1 {m1.passed}/{m1.total}   M4 {m4.passed}/{m4.total}"
        for source, (m1, m4) in report.by_source.items()
    ]
    return lines
