"""The context diagnostic: which text reached the model, and whether the support was in it."""

from __future__ import annotations

from pathlib import Path

import pytest

from bfs_reg_copilot.eval.cli import EXIT_UNREADABLE, main
from bfs_reg_copilot.eval.context import (
    Support,
    content_words,
    diagnose,
    failing_items,
    needed_chunk_ids,
    overlap,
    render_report,
)
from bfs_reg_copilot.eval.fakes import DOUBLES
from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet, Split, load_gold
from bfs_reg_copilot.eval.grading import Grades
from bfs_reg_copilot.eval.runner import run_eval, write_run
from bfs_reg_copilot.eval.types import PipelineAnswer, RunRecord

REPO = Path(__file__).resolve().parent.parent
GOLD_FILE = REPO / "eval" / "gold" / "gold-v2.yaml"


@pytest.fixture(scope="module")
def gold() -> GoldSet:
    return load_gold(GOLD_FILE)


def _item(gold: GoldSet) -> AnswerableItem:
    return next(i for i in gold.items if isinstance(i, AnswerableItem) and i.split is Split.DEV)


def _record(item: AnswerableItem, retrieved: tuple[str, ...]) -> RunRecord:
    answer = PipelineAnswer(
        text="an answer", refused=False, cited_chunks=(), retrieved_chunks=retrieved
    )
    return RunRecord(
        item_id=item.id,
        kind="answerable",
        split=item.split,
        question=item.question,
        answer=answer,
        latency_s=1.0,
    )


def test_content_words_keep_numbers_and_drop_short_and_stop_words() -> None:
    words = content_words("The review must be done within 30 days, and the report is for B-10.")
    assert {"review", "days", "report", "30"} <= words
    assert "the" not in words
    assert "must" not in words  # stop words are dropped
    assert "within" not in words


def test_overlap_counts_the_words_of_the_point_found_in_the_text() -> None:
    found, total = overlap("Triggers for invoking exit plans", "plans with triggers to invoke exit")
    assert (found, total) == (3, 4)  # plans, triggers, exit; "invoking" is not "invoke"


def test_support_status_exact_section_and_missing(gold: GoldSet) -> None:
    item = _item(gold)
    chunk = item.supporting_chunks[0]
    exact = diagnose(item, _record(item, (chunk,)), {chunk: "text"})
    assert exact.support[0].status is Support.EXACT
    assert exact.support[0].rank == 1
    sibling = chunk.rsplit(":", 1)[0] + ":c099"
    section = diagnose(item, _record(item, ("A-X:aaaaaaaaaaaa:s001:c000", sibling)), {})
    assert section.support[0].status is Support.SECTION
    assert section.support[0].rank == 2
    assert section.content_reached_the_model
    missing = diagnose(item, _record(item, ("A-X:aaaaaaaaaaaa:s001:c000",)), {})
    assert missing.support[0].status is Support.MISSING
    assert not missing.content_reached_the_model


def test_key_point_overlap_uses_the_text_the_model_received(gold: GoldSet) -> None:
    item = _item(gold)
    chunk = item.supporting_chunks[0]
    full = diagnose(item, _record(item, (chunk,)), {chunk: " ".join(item.key_points)})
    assert all(found == total for found, total in full.in_context)
    empty = diagnose(item, _record(item, (chunk,)), {chunk: "nothing relevant"})
    assert all(found < total for found, total in empty.in_context if total > 2)


def test_failing_items_are_the_decided_failures(gold: GoldSet) -> None:
    _, records = run_eval(gold, DOUBLES["refuse"](gold), Split.DEV, gold_hash="h" * 64, commit="c")
    assert len(failing_items(gold, records, Grades())) == 32  # all refused: mechanical failures
    _, records = run_eval(gold, DOUBLES["oracle"](gold), Split.DEV, gold_hash="h" * 64, commit="c")
    assert failing_items(gold, records, Grades()) == []  # not decided yet: not a failure


def test_needed_chunks_cover_what_was_retrieved_and_what_the_gold_supports(gold: GoldSet) -> None:
    item = _item(gold)
    record = _record(item, ("A-X:aaaaaaaaaaaa:s001:c000",))
    ids = needed_chunk_ids(gold, [record], [item.id])
    assert "A-X:aaaaaaaaaaaa:s001:c000" in ids
    assert set(item.supporting_chunks) <= set(ids)


def test_report_shows_the_text_the_model_saw_and_the_missing_support(gold: GoldSet) -> None:
    item = _item(gold)
    seen = "A-X:aaaaaaaaaaaa:s001:c000"
    support = item.supporting_chunks[0]
    texts = {seen: "THE TEXT THE MODEL SAW", support: "THE GOLD SUPPORT TEXT"}
    report, summary = render_report(gold, [_record(item, (seen,))], Grades(), [item.id], texts)
    body = "\n".join(report)
    assert "THE TEXT THE MODEL SAW" in body
    assert "Gold support not in the context" in body
    assert "THE GOLD SUPPORT TEXT" in body
    assert "SUPPORT NOT IN CONTEXT" in summary[0]


def test_cli_needs_a_grades_file_and_never_writes_into_the_repo(
    gold: GoldSet, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta, records = run_eval(
        gold, DOUBLES["oracle"](gold), Split.DEV, gold_hash="h" * 64, commit="c"
    )
    run_dir = write_run(tmp_path, meta, records)
    code = main(["--gold", str(GOLD_FILE), "context", str(run_dir)])
    assert code == EXIT_UNREADABLE
    assert "grades file not found" in capsys.readouterr().out
    assert not (run_dir / "context-report.md").exists()
