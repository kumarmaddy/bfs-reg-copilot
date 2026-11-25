"""Context diagnostic: what text reached the model for a question, and which key points it holds.

Three experiments on the generator (more context, a different prompt, a larger model) did not
raise M1. Before changing retrieval, this tells the two causes apart: the answer is not in the text
the model was given (corpus, chunking, retrieval), or it is there and the model missed it.

The report holds corpus text, so it goes to the run folder (not in git), never into the
repository. The word-overlap figures are a rough guide: the gold key points are paraphrases, so a
person reads the text and decides. Nothing here changes a score.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet
from bfs_reg_copilot.eval.grading import Grades
from bfs_reg_copilot.eval.metrics import section_id
from bfs_reg_copilot.eval.report import m1_outcome
from bfs_reg_copilot.eval.types import RunRecord

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    [
        "that",
        "this",
        "with",
        "from",
        "they",
        "their",
        "have",
        "been",
        "were",
        "will",
        "would",
        "should",
        "must",
        "which",
        "what",
        "when",
        "where",
        "there",
        "than",
        "then",
        "them",
        "these",
        "those",
        "into",
        "also",
        "such",
        "other",
        "more",
        "most",
        "only",
        "each",
        "both",
        "about",
        "over",
        "under",
        "between",
        "within",
        "without",
        "your",
        "does",
        "done",
        "being",
        "whose",
        "while",
        "upon",
        "onto",
    ]
)


class Support(StrEnum):
    EXACT = "the supporting chunk is in the context"
    SECTION = "another chunk of the supporting section is in the context"
    MISSING = "no chunk of the supporting section is in the context"


def content_words(text: str) -> frozenset[str]:
    """Words of four or more letters (stop words removed) and any number: what a point is about."""
    words = _WORD.findall(text.lower())
    return frozenset(w for w in words if (len(w) >= 4 and w not in _STOP) or w.isdigit())


def overlap(point: str, text: str) -> tuple[int, int]:
    """(content words of `point` found in `text`, content words of `point`)."""
    wanted = content_words(point)
    return len(wanted & content_words(text)), len(wanted)


@dataclass(frozen=True)
class SupportStatus:
    chunk_id: str
    status: Support
    rank: int | None  # 1-based position in the context, when present


@dataclass(frozen=True)
class Diagnosis:
    item: AnswerableItem
    record: RunRecord
    context_ids: tuple[str, ...]
    support: tuple[SupportStatus, ...]
    in_context: tuple[tuple[int, int], ...]  # per key point, overlap with the whole context
    in_support: tuple[tuple[int, int], ...]  # per key point, overlap with the supporting chunks

    @property
    def content_reached_the_model(self) -> bool:
        return any(s.status is not Support.MISSING for s in self.support)


def failing_items(gold: GoldSet, records: list[RunRecord], grades: Grades) -> list[str]:
    """Answerable questions whose M1 is decided and failed (mechanically or by a person's grade)."""
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    return [
        r.item_id
        for r in records
        if r.item_id in items and m1_outcome(items[r.item_id], r, grades) is False
    ]


def needed_chunk_ids(gold: GoldSet, records: list[RunRecord], item_ids: list[str]) -> list[str]:
    """Every chunk id the report will show: what was retrieved and what the gold says supports."""
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    wanted: dict[str, None] = {}
    for record in records:
        if record.item_id in item_ids and record.answer is not None:
            wanted.update(dict.fromkeys(record.answer.retrieved_chunks))
            wanted.update(dict.fromkeys(items[record.item_id].supporting_chunks))
    return list(wanted)


def diagnose(item: AnswerableItem, record: RunRecord, texts: Mapping[str, str]) -> Diagnosis:
    context = record.answer.retrieved_chunks if record.answer is not None else ()
    sections = {section_id(c): i for i, c in reversed(list(enumerate(context, start=1)))}
    support = []
    for chunk_id in item.supporting_chunks:
        if chunk_id in context:
            support.append(SupportStatus(chunk_id, Support.EXACT, context.index(chunk_id) + 1))
        elif section_id(chunk_id) in sections:
            support.append(SupportStatus(chunk_id, Support.SECTION, sections[section_id(chunk_id)]))
        else:
            support.append(SupportStatus(chunk_id, Support.MISSING, None))
    everything = "\n".join(texts.get(c, "") for c in context)
    supporting = "\n".join(texts.get(c, "") for c in item.supporting_chunks)
    return Diagnosis(
        item,
        record,
        tuple(context),
        tuple(support),
        tuple(overlap(p, everything) for p in item.key_points),
        tuple(overlap(p, supporting) for p in item.key_points),
    )


def summary_line(d: Diagnosis) -> str:
    reached = {
        Support.EXACT: "supporting chunk in context",
        Support.SECTION: "supporting section in context",
        Support.MISSING: "SUPPORT NOT IN CONTEXT",
    }
    best = min((s.status for s in d.support), key=list(Support).index)
    low = [i for i, (f, t) in enumerate(d.in_context, start=1) if t and f / t < 0.6]
    gaps = f"; key points with low word overlap: {', '.join(map(str, low))}" if low else ""
    return f"{d.item.id}: {reached[best]}{gaps}"


def render_item(d: Diagnosis, texts: Mapping[str, str], grades: Grades) -> list[str]:
    answer = d.record.answer
    lines = [f"## {d.item.id}", "", f"**Question:** {d.item.question}", ""]
    lines += [
        f"**Pass rule:** {d.item.pass_rule.text}",
        "",
        "**Key points** (word overlap with the ",
    ]
    lines[-1] += "context / with the gold supporting chunks; a rough guide only):"
    for number, point in enumerate(d.item.key_points, start=1):
        a, b = d.in_context[number - 1]
        c, e = d.in_support[number - 1]
        lines.append(f"{number}. {point}  [context {a}/{b}; supporting chunks {c}/{e}]")
    lines += ["", "**Supporting chunks (gold):**"]
    for s in d.support:
        where = f" at position {s.rank}" if s.rank else ""
        lines.append(f"- `{s.chunk_id}`: {s.status.value}{where}")
    if answer is not None:
        graded = grades.points.get(d.item.id)
        lines += [
            "",
            f"**Model answer** (refused: {answer.refused}; points hit by the grader: "
            f"{' '.join(map(str, graded)) if graded else 'none recorded'}): {answer.text}",
            f"**Cited:** {' '.join(answer.cited_chunks) or 'nothing'}",
        ]
    lines += ["", "**Text the model received, in order:**", ""]
    for position, chunk_id in enumerate(d.context_ids, start=1):
        gold_mark = " (gold support)" if chunk_id in d.item.supporting_chunks else ""
        lines += [
            f"### S{position} `{chunk_id}`{gold_mark}",
            "",
            texts.get(chunk_id, "(missing)"),
            "",
        ]
    missing = [s.chunk_id for s in d.support if s.status is not Support.EXACT]
    for chunk_id in missing:
        lines += [f"### Gold support not in the context: `{chunk_id}`", ""]
        lines += [texts.get(chunk_id, "(missing)"), ""]
    return lines


def render_report(
    gold: GoldSet,
    records: list[RunRecord],
    grades: Grades,
    item_ids: list[str],
    texts: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    """(the markdown report, one summary line per question)."""
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    by_id = {r.item_id: r for r in records}
    diagnoses = [diagnose(items[i], by_id[i], texts) for i in item_ids if i in by_id and i in items]
    out = [
        "# Context diagnostic",
        "",
        "Corpus text below: keep this file out of git. Word overlap is a rough guide.",
        "",
    ]
    for d in diagnoses:
        out += render_item(d, texts, grades)
    return out, [summary_line(d) for d in diagnoses]
