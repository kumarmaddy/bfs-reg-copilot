"""Chunk audit: how much of the context a run sent was low-value, and where lists were cut.

Diagnostics 3.4 and the ranks table showed that retrieval and chunking, not only the generator,
cost answers: a front-matter or tiny chunk can take one of five context slots, and a bulleted list
cut at the size limit can leave the answer split across two chunks. Before any ingestion change
(which would re-id chunks and force a new gold version), this counts both problems on the dev
questions. Read-only; it changes no score. Two rough rules, stated so they can be argued with:

- low value: the chunk is the first section of its page (front matter) or has under 150 characters;
- list cut: the last line of a chunk and the first line of the next chunk of the same section are
  both list items ("- " bullets, possibly indented), so a list runs across the boundary.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet
from bfs_reg_copilot.eval.grading import Grades
from bfs_reg_copilot.eval.report import m1_outcome
from bfs_reg_copilot.eval.types import RunRecord

SMALL_CHARS = 150


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    source_id: str
    section_index: int
    chunk_index: int
    chunk_count: int
    text: str


def is_low_value(row: ChunkRow) -> bool:
    return row.section_index == 0 or len(row.text.strip()) < SMALL_CHARS


def _is_list_item(line: str) -> bool:
    return line.lstrip().startswith("- ")


def _lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


def list_cut_after(row: ChunkRow, following: ChunkRow | None) -> bool:
    """True when `row` and the chunk after it (same section) are both cut through a list."""
    if following is None or following.section_index != row.section_index:
        return False
    if following.source_id != row.source_id or following.chunk_index != row.chunk_index + 1:
        return False
    mine, theirs = _lines(row.text), _lines(following.text)
    return bool(mine and theirs and _is_list_item(mine[-1]) and _is_list_item(theirs[0]))


def list_cut_boundaries(rows: Sequence[ChunkRow]) -> list[tuple[ChunkRow, ChunkRow]]:
    """Every pair of neighbouring chunks (same section) with a list running across the boundary."""
    ordered = sorted(rows, key=lambda r: (r.source_id, r.section_index, r.chunk_index))
    return [
        (row, following)
        for row, following in itertools.pairwise(ordered)
        if list_cut_after(row, following)
    ]


def cut_list_chunks(rows: Sequence[ChunkRow]) -> set[str]:
    """Ids of chunks that either end or begin on a list that crosses a chunk boundary."""
    return {r.chunk_id for pair in list_cut_boundaries(rows) for r in pair}


@dataclass(frozen=True)
class ItemAudit:
    item_id: str
    outcome: bool | None  # M1: True pass, False fail, None undecided (no grade yet)
    slots: int
    low_value_slots: int
    gold_in_context: int
    gold_total: int
    gold_cut_in_context: int  # gold chunks in context that sit on a cut list
    gold_cut_missing: int  # gold chunks NOT in context that sit on a cut list


def audit_run(
    gold: GoldSet,
    records: Sequence[RunRecord],
    grades: Grades,
    rows: Mapping[str, ChunkRow],
    cut: set[str],
) -> list[ItemAudit]:
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    out: list[ItemAudit] = []
    for record in records:
        item = items.get(record.item_id)
        if item is None or record.answer is None:
            continue
        context = record.answer.retrieved_chunks
        needed = list(item.supporting_chunks)
        out.append(
            ItemAudit(
                item_id=item.id,
                outcome=m1_outcome(item, record, grades),
                slots=len(context),
                low_value_slots=sum(1 for c in context if c in rows and is_low_value(rows[c])),
                gold_in_context=sum(1 for c in needed if c in context),
                gold_total=len(needed),
                gold_cut_in_context=sum(1 for c in needed if c in cut and c in context),
                gold_cut_missing=sum(1 for c in needed if c in cut and c not in context),
            )
        )
    return out


def summarise_audit(
    audits: Sequence[ItemAudit], corpus_cut: int, corpus_boundaries: int
) -> list[str]:
    total_slots = sum(a.slots for a in audits)
    wasted = sum(a.low_value_slots for a in audits)
    with_waste = [a for a in audits if a.low_value_slots]
    by_outcome: Counter[str] = Counter()
    for a in with_waste:
        by_outcome["pass" if a.outcome else "fail" if a.outcome is False else "ungraded"] += 1
    cut_hit = [a for a in audits if a.gold_cut_in_context or a.gold_cut_missing]
    share = f"{wasted} ({100 * wasted / total_slots:.0f}%)" if total_slots else "0"
    waste_by = (
        f"pass {by_outcome['pass']}, fail {by_outcome['fail']}, ungraded {by_outcome['ungraded']}"
    )
    lines = [
        f"questions audited: {len(audits)}",
        f"context slots: {total_slots}; low-value (front matter, or under {SMALL_CHARS} chars):"
        f" {share}",
        f"questions with at least one low-value slot: {len(with_waste)} ({waste_by})",
        f"corpus chunk boundaries inside a list: {corpus_cut} of {corpus_boundaries}",
        f"questions whose gold chunks sit on a cut list: {len(cut_hit)}",
    ]
    for a in cut_hit:
        state = "pass" if a.outcome else "fail" if a.outcome is False else "ungraded"
        lines.append(
            f"  {a.item_id}: {a.gold_cut_in_context} cut-list gold chunk(s) in context, "
            f"{a.gold_cut_missing} missing ({state})"
        )
    return lines
