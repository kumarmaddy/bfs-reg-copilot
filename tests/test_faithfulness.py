"""M6 labelling material: the sample is reproducible, the export is complete, the flag is honest."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bfs_reg_copilot.eval.faithfulness import (
    COLUMNS,
    RELABEL_COUNT,
    build_rows,
    numbers_in,
    numbers_not_in,
    relabel_ids,
    render_context,
    select_candidates,
    write_sheet,
)
from bfs_reg_copilot.eval.gold import Split
from bfs_reg_copilot.eval.types import PipelineAnswer, RunMeta, RunRecord
from bfs_reg_copilot.rag.prompt import ContextChunk

CHUNK = ContextChunk(
    "A-T:aaaaaaaaaaaa:s001:c000", ("Guide", "Dates"), "Takes effect May 1, 2027. 250 staff."
)


def record(
    item: str,
    text: str,
    *,
    refused: bool = False,
    cited: tuple[str, ...] = (CHUNK.chunk_id,),
    kind: str = "answerable",
    guard: str = "",
) -> RunRecord:
    answer = PipelineAnswer(
        text=text, refused=refused, cited_chunks=cited, retrieved_chunks=cited, guard=guard
    )
    return RunRecord.model_validate(
        {
            "item_id": item,
            "kind": kind,
            "split": Split.DEV,
            "question": f"q {item}?",
            "answer": answer,
            "latency_s": 1.0,
        }
    )


def meta(run_id: str) -> RunMeta:
    now = datetime(2026, 11, 27, tzinfo=UTC)
    return RunMeta(
        run_id=run_id,
        started_at=now,
        finished_at=now,
        split=Split.DEV,
        pipeline="baseline",
        is_test_double=False,
        settings={},
        gold_sha256="x",
        gold_version=3,
        git_commit="c",
        n_items=0,
    )


class Source:
    def fetch(self, chunk_ids: Sequence[str]) -> list[ContextChunk]:
        return [CHUNK for i in chunk_ids if i == CHUNK.chunk_id]


def test_numbers_ignore_commas_and_single_digits() -> None:
    assert numbers_in("Section 3 lists 1,000 items, 2.5% and 2027.") == {"1000", "2.5", "2027"}


def test_numbers_not_in_the_cited_text_are_flagged() -> None:
    assert numbers_not_in("Effective May 1, 2027 for 300 staff.", [CHUNK.text]) == ["300"]
    assert numbers_not_in("Effective May 1, 2027.", [CHUNK.text]) == []


def test_reference_run_non_refusals_are_all_in_and_refusals_are_out() -> None:
    ref = (
        meta("ref"),
        [
            record("G-2", "b"),
            record("G-1", "a"),
            record("G-3", "x", refused=True, cited=()),
            record("G-4", "y", guard="uncited"),
            record("G-5", "z", kind="refusal"),
        ],
    )
    picked = select_candidates(ref, [])
    assert [c.record.item_id for c in picked] == ["G-1", "G-2"]
    assert {c.stratum for c in picked} == {"A"}


def test_other_runs_add_only_different_answers_up_to_the_cap() -> None:
    ref = (meta("ref"), [record("G-1", "same"), record("G-2", "ref answer")])
    other = (
        meta("o1"),
        [record("G-1", "same"), record("G-2", "different"), record(f"G-{9}", "new item")],
    )
    picked = select_candidates(ref, [other], other_cap=1)
    assert [c.stratum for c in picked] == ["A", "A", "B"]
    assert len(select_candidates(ref, [other], other_cap=5)) == 4  # 2 + the two that differ
    assert select_candidates(ref, [other, other], other_cap=5) == select_candidates(
        ref, [other], other_cap=5
    )


def test_the_pick_is_reproducible() -> None:
    ref = (meta("ref"), [record("G-1", "a")])
    others = [(meta(f"o{n}"), [record(f"G-{i}", f"t{n}{i}") for i in range(10)]) for n in range(3)]
    first = select_candidates(ref, others)
    assert first == select_candidates(ref, list(others))
    assert sum(c.stratum == "B" for c in first) == 9


def test_relabel_set_is_fixed_and_the_right_size() -> None:
    ids = [f"F-{n:02d}" for n in range(1, 41)]
    assert relabel_ids(ids) == relabel_ids(list(reversed(ids)))
    assert len(relabel_ids(ids)) == RELABEL_COUNT


def test_sheet_and_context_carry_everything_a_labeller_needs(tmp_path: Path) -> None:
    ref = (meta("ref"), [record("G-1", "Effective May 1, 2027 for 300 staff.")])
    rows, context = build_rows(select_candidates(ref, []), Source())
    path = tmp_path / "sheet.csv"
    write_sheet(path, rows)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        read = list(csv.DictReader(handle))
    assert tuple(read[0]) == COLUMNS
    assert read[0]["numbers_not_in_cited"] == "300"
    assert read[0]["owner_label"] == ""
    text = render_context(rows, context)
    assert "Takes effect May 1, 2027." in text
    assert "Numbers in the answer not found in the cited text:** 300" in text


def test_write_sheet_will_not_overwrite_labels(tmp_path: Path) -> None:
    path = tmp_path / "sheet.csv"
    write_sheet(path, [])
    with pytest.raises(FileExistsError):
        write_sheet(path, [])
