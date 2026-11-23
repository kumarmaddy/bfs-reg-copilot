"""Human grading by CSV: write a sheet of answers to judge, read the verdicts back.

Only answers that pass the mechanical checks need a person: refusals, citations and retrieval are
scored by the harness itself. The CSV opens in Excel or VS Code. Blank cells mean "not graded yet".
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from bfs_reg_copilot.eval.gold import AdversarialItem, AnswerableItem, GoldSet
from bfs_reg_copilot.eval.metrics import cites_support, section_id
from bfs_reg_copilot.eval.types import RunRecord

COLUMNS = (
    "item_id",
    "kind",
    "question",
    "what_to_check",
    "answer",
    "cited_sections",
    "points_hit",
    "contradicts",
    "verdict",
    "note",
)
_NUMBERS = re.compile(r"\d+")


class GradingError(Exception):
    """The grading file is unreadable or inconsistent with the gold set."""


@dataclass(frozen=True)
class Grades:
    """Verdicts read back from a sheet."""

    points: dict[str, tuple[int, ...]] = field(default_factory=dict)
    contradicts: frozenset[str] = frozenset()
    verdicts: dict[str, bool] = field(default_factory=dict)


def needs_grading(gold: GoldSet, record: RunRecord) -> bool:
    """True for answerable answers that survived the mechanical checks, and scored adversarial."""
    item = next(i for i in gold.items if i.id == record.item_id)
    if isinstance(item, AdversarialItem):
        return item.scored and record.answer is not None
    if not isinstance(item, AnswerableItem) or record.answer is None:
        return False
    return not record.answer.refused and cites_support(item, record.answer)


def write_grading_sheet(path: Path, gold: GoldSet, records: list[RunRecord]) -> int:
    """Write the sheet; returns the number of rows. Refuses to overwrite a file with grades."""
    if path.exists():
        raise GradingError(f"{path} already exists; move it aside before writing a new sheet")
    by_id = {i.id: i for i in gold.items}
    rows: list[dict[str, str]] = []
    for record in records:
        if not needs_grading(gold, record) or record.answer is None:
            continue
        item = by_id[record.item_id]
        if isinstance(item, AnswerableItem):
            check = " | ".join(f"{n}. {p}" for n, p in enumerate(item.key_points, 1))
            check += f"  [needs {item.pass_rule.text}]"
        elif isinstance(item, AdversarialItem):
            check = item.expected_behaviour
        else:
            continue
        rows.append(
            {
                "item_id": record.item_id,
                "kind": record.kind,
                "question": record.question,
                "what_to_check": check,
                "answer": record.answer.text,
                "cited_sections": " ".join(
                    sorted({section_id(c) for c in record.answer.cited_chunks})
                ),
                "points_hit": "",
                "contradicts": "",
                "verdict": "",
                "note": "",
            }
        )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _yes(cell: str) -> bool:
    return cell.strip().lower() in {"y", "yes", "true", "1"}


def read_grades(path: Path, gold: GoldSet) -> Grades:
    """Read verdicts. `points_hit` is numbers like `1 2 4` (`0` = none); `verdict` is pass/fail."""
    by_id = {i.id: i for i in gold.items}
    points: dict[str, tuple[int, ...]] = {}
    contradicts: set[str] = set()
    verdicts: dict[str, bool] = {}
    try:
        handle = path.open(encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise GradingError(f"cannot read {path}: {exc}") from exc
    with handle:
        for row in csv.DictReader(handle):
            item_id = (row.get("item_id") or "").strip()
            item = by_id.get(item_id)
            if item is None:
                raise GradingError(f"unknown item id {item_id!r} in {path}")
            cell = (row.get("points_hit") or "").strip()
            if isinstance(item, AnswerableItem) and cell:
                numbers = tuple(sorted({int(n) for n in _NUMBERS.findall(cell)} - {0}))
                if any(n > len(item.key_points) for n in numbers):
                    raise GradingError(f"{item_id}: points_hit {cell!r} has no such key point")
                points[item_id] = numbers
                if _yes(row.get("contradicts") or ""):
                    contradicts.add(item_id)
            verdict = (row.get("verdict") or "").strip().lower()
            if isinstance(item, AdversarialItem) and verdict:
                if verdict not in {"pass", "fail"}:
                    raise GradingError(f"{item_id}: verdict must be pass or fail, got {verdict!r}")
                verdicts[item_id] = verdict == "pass"
    return Grades(points=points, contradicts=frozenset(contradicts), verdicts=verdicts)
