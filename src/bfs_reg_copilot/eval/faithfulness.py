"""Faithfulness (M6) labelling material: which answers to label, what to show, one cheap check.

M6 asks whether every claim in an answer is supported by the text it cites. Only a person can say
so reliably, so this module prepares the labelling and does not judge. It picks the answers
(deterministically, so the sample can be reproduced), exports each with the text of the chunks it
cites, and flags numbers that appear in the answer but not in those chunks. That flag is a lead
for the labeller, not a label: it cannot see numbers written as words or dates in another format.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bfs_reg_copilot.eval.types import RunMeta, RunRecord
from bfs_reg_copilot.rag.pipeline import ChunkSource
from bfs_reg_copilot.rag.prompt import ContextChunk

OTHER_CAP: Final = 9  # answers taken from other runs to include answers that were wrong
RELABEL_COUNT: Final = 15  # doc 02: re-label a random 15 after 48 hours
COLUMNS: Final = (
    "row_id",
    "stratum",
    "item_id",
    "source_run",
    "question",
    "answer",
    "cited_chunks",
    "numbers_not_in_cited",
    "relabel_after_48h",
    "owner_label",
    "owner_note",
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Candidate:
    stratum: str  # "A" reference run, "B" other runs
    run_id: str
    record: RunRecord


def numbers_in(text: str) -> set[str]:
    """Numbers as digits, commas removed, single digits dropped (list numbering, 'section 3')."""
    found = {m.group().rstrip(",.").replace(",", "") for m in _NUMBER.finditer(text)}
    return {n for n in found if len(n.split(".")[0]) > 1 or "." in n}


def numbers_not_in(answer: str, chunk_texts: Sequence[str]) -> list[str]:
    """Numbers the answer states that none of the given texts contains."""
    have: set[str] = set()
    for text in chunk_texts:
        have |= numbers_in(text)
    return sorted(numbers_in(answer) - have)


def _eligible(record: RunRecord) -> bool:
    answer = record.answer
    return (
        answer is not None
        and not answer.refused
        and not answer.guard
        and bool(answer.cited_chunks)
        and record.kind in ("answerable", "adversarial")
    )


def _order_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def select_candidates(
    reference: tuple[RunMeta, list[RunRecord]],
    others: Sequence[tuple[RunMeta, list[RunRecord]]],
    other_cap: int = OTHER_CAP,
) -> list[Candidate]:
    """Stratum A: every non-refused cited answer of the reference run, by item id. Stratum B: up
    to `other_cap` answers from the other runs that differ from the reference answer to the same
    item, in a fixed pseudo-random order (a hash of run and item), so no item is favoured."""
    ref_meta, ref_records = reference
    chosen = [
        Candidate("A", ref_meta.run_id, r)
        for r in sorted(ref_records, key=lambda r: r.item_id)
        if _eligible(r)
    ]
    ref_text = {r.item_id: r.answer.text for r in ref_records if r.answer is not None}
    pool: dict[tuple[str, str], Candidate] = {}
    for meta, records in others:
        for r in records:
            if not _eligible(r) or r.answer is None or ref_text.get(r.item_id) == r.answer.text:
                continue
            pool.setdefault((r.item_id, r.answer.text), Candidate("B", meta.run_id, r))
    ordered = sorted(pool.values(), key=lambda c: _order_key(c.run_id, c.record.item_id))
    return chosen + ordered[:other_cap]


def relabel_ids(row_ids: Sequence[str], count: int = RELABEL_COUNT) -> set[str]:
    return set(sorted(row_ids, key=lambda i: _order_key("relabel", i))[:count])


def build_rows(
    candidates: Sequence[Candidate], chunks: ChunkSource
) -> tuple[list[dict[str, str]], dict[str, list[ContextChunk]]]:
    ids = [f"F-{n:02d}" for n in range(1, len(candidates) + 1)]
    again = relabel_ids(ids)
    rows: list[dict[str, str]] = []
    context: dict[str, list[ContextChunk]] = {}
    for row_id, c in zip(ids, candidates, strict=True):
        answer = c.record.answer
        if answer is None:  # _eligible rules this out; the check keeps the types honest
            raise ValueError(f"{c.record.item_id} has no answer")
        cited = chunks.fetch(list(answer.cited_chunks))
        context[row_id] = cited
        rows.append(
            {
                "row_id": row_id,
                "stratum": c.stratum,
                "item_id": c.record.item_id,
                "source_run": c.run_id,
                "question": c.record.question,
                "answer": answer.text,
                "cited_chunks": " ".join(answer.cited_chunks),
                "numbers_not_in_cited": " ".join(
                    numbers_not_in(answer.text, [x.text for x in cited])
                ),
                "relabel_after_48h": "yes" if row_id in again else "",
                "owner_label": "",
                "owner_note": "",
            }
        )
    return rows, context


def write_sheet(path: Path, rows: Sequence[dict[str, str]]) -> None:
    if path.exists():
        raise FileExistsError(f"{path} already exists; move it aside first")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def render_context(rows: Sequence[dict[str, str]], context: dict[str, list[ContextChunk]]) -> str:
    """The cited text for every row. Corpus text: keep this file out of git."""
    out = [
        "# M6 labelling: answers and the text they cite",
        "",
        "Label `supported` only if EVERY claim in the answer is stated by the cited text below.",
        "Label `unsupported` if any claim is missing, changed or added, and say which in the note.",
        "",
    ]
    for row in rows:
        out += [
            f"## {row['row_id']} ({row['item_id']})",
            "",
            f"**Question:** {row['question']}",
            "",
        ]
        out += [f"**Answer:** {row['answer']}", ""]
        if row["numbers_not_in_cited"]:
            found = row["numbers_not_in_cited"]
            out += [f"**Numbers in the answer not found in the cited text:** {found}", ""]
        for chunk in context[row["row_id"]]:
            out += [
                f"### Cited: {chunk.chunk_id} ({' > '.join(chunk.section_path)})",
                "",
                chunk.text,
                "",
            ]
    return "\n".join(out) + "\n"
