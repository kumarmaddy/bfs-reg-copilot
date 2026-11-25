"""The harness end to end, using test doubles with known behaviour.

If a double with a known behaviour gets the wrong score, the scorer is wrong.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bfs_reg_copilot.eval.cli import (
    EXIT_HOLDOUT_REFUSED,
    EXIT_OK,
    EXIT_UNREADABLE,
    main,
)
from bfs_reg_copilot.eval.fakes import DOUBLES
from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet, Split, load_gold
from bfs_reg_copilot.eval.grading import (
    COLUMNS,
    Grades,
    GradingError,
    read_grades,
    write_grading_sheet,
)
from bfs_reg_copilot.eval.report import Report, build_report
from bfs_reg_copilot.eval.runner import (
    HoldoutRefused,
    log_holdout_use,
    read_run,
    require_holdout_confirmation,
    run_eval,
    select_items,
    write_run,
)
from bfs_reg_copilot.eval.types import PipelineAnswer, RunMeta, RunRecord

REPO = Path(__file__).resolve().parent.parent
GOLD_FILE = REPO / "eval" / "gold" / "gold-v1.yaml"


@pytest.fixture(scope="module")
def gold() -> GoldSet:
    return load_gold(GOLD_FILE)


def _run(gold: GoldSet, name: str, split: Split = Split.DEV) -> tuple[RunMeta, list[RunRecord]]:
    return run_eval(gold, DOUBLES[name](gold), split, gold_hash="h" * 64, commit="abc")


def _perfect_grades(gold: GoldSet, records: list[RunRecord]) -> Grades:
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    points = {
        r.item_id: tuple(range(1, len(items[r.item_id].key_points) + 1))
        for r in records
        if r.item_id in items
    }
    return Grades(points=points)


def _report(gold: GoldSet, name: str, grades: Grades | None = None) -> Report:
    meta, records = _run(gold, name)
    return build_report(gold, meta, records, grades or _perfect_grades(gold, records))


# -- known behaviour, known score ----------------------------------------------------------------


def test_oracle_scores_perfectly_once_a_person_grades_it(gold: GoldSet) -> None:
    report = _report(gold, "oracle")
    assert (report.m1.passed, report.m1.total) == (32, 32)
    assert (report.m2.passed, report.m2.total) == (12, 12)
    assert (report.m4.passed, report.m4.total) == (32, 32)
    assert report.fabricated == 0
    assert report.errors == 0
    assert report.m1_ungraded == 0


def test_ungraded_answers_are_counted_not_guessed(gold: GoldSet) -> None:
    report = _report(gold, "oracle", Grades())
    assert report.m1.total == 0
    assert report.m1_ungraded == 32


def test_always_refusing_gets_refusals_right_and_answers_wrong(gold: GoldSet) -> None:
    report = _report(gold, "refuse")
    assert (report.m1.passed, report.m1.total) == (0, 32)
    assert (report.m2.passed, report.m2.total) == (12, 12)
    assert report.m4.passed == 0
    assert report.m1_ungraded == 0  # a refusal needs no person to fail


def test_right_text_without_citations_fails_m1(gold: GoldSet) -> None:
    report = _report(gold, "uncited")
    assert (report.m1.passed, report.m1.total) == (0, 32)
    assert report.m4.passed == 32  # retrieval was fine; only the citing failed


def test_citing_the_wrong_section_fails_m1_and_m4(gold: GoldSet) -> None:
    report = _report(gold, "wrong-cite")
    assert report.m1.passed == 0
    assert report.m4.passed == 0
    assert report.fabricated == 0  # it cited what it retrieved, just the wrong thing


def test_a_fabricating_pipeline_is_caught_on_citations_and_refusals(gold: GoldSet) -> None:
    report = _report(gold, "fabricating")
    assert report.m2.passed == 0
    assert report.fabricated == report.citations > 0
    assert report.m4.passed == 0


def test_a_contradiction_fails_even_with_enough_points(gold: GoldSet) -> None:
    meta, records = _run(gold, "oracle")
    grades = _perfect_grades(gold, records)
    first = records[0].item_id
    flagged = Grades(points=grades.points, contradicts=frozenset({first}))
    report = build_report(gold, meta, records, flagged)
    assert report.m1.passed == 31


# -- run selection, errors and the seal ----------------------------------------------------------


def test_split_selection_matches_the_gold_file(gold: GoldSet) -> None:
    dev, skipped = select_items(gold, Split.DEV, None)
    holdout, _ = select_items(gold, Split.HOLDOUT, None)
    assert len(dev) == 47  # 32 + 12 + 3 scorable adversarial
    assert skipped == ["G-ADV-003"]
    assert len(holdout) == 12
    assert not set(dev) & set(holdout)


def test_limit_applies_per_kind(gold: GoldSet) -> None:
    ids, _ = select_items(gold, Split.DEV, 2)
    assert len(ids) == 6


class _Exploding:
    name = "exploding"
    is_test_double = True

    def describe(self) -> dict[str, str]:
        return {}

    def answer(self, question: str) -> PipelineAnswer:
        raise RuntimeError("model server unreachable")


def test_a_failing_pipeline_does_not_stop_the_run(gold: GoldSet) -> None:
    meta, records = run_eval(
        gold, _Exploding(), Split.DEV, gold_hash="h" * 64, commit="abc", limit=1
    )
    assert len(records) == 3
    assert all("unreachable" in r.error and r.answer is None for r in records)
    report = build_report(gold, meta, records, Grades())
    assert report.errors == 3
    assert report.m1.total == 1
    assert report.m1.passed == 0  # an error is a failure, not a skip
    assert report.m2.passed == 0


def test_run_is_stored_and_read_back(gold: GoldSet, tmp_path: Path) -> None:
    clock = iter(
        [datetime(2026, 11, 23, 12, 0, tzinfo=UTC), datetime(2026, 11, 23, 12, 1, tzinfo=UTC)]
    )
    meta, records = run_eval(
        gold,
        DOUBLES["oracle"](gold),
        Split.DEV,
        gold_hash="h" * 64,
        commit="abc",
        clock=lambda: next(clock),
    )
    run_dir = write_run(tmp_path, meta, records)
    assert run_dir.name == "20261123T120000Z-oracle-dev"
    back_meta, back_records = read_run(run_dir)
    assert back_meta == meta
    assert back_records == records
    assert back_meta.is_test_double


@pytest.mark.parametrize(("confirmed", "reason"), [(False, "x"), (True, ""), (True, "  ")])
def test_holdout_needs_confirmation_and_a_reason(confirmed: bool, reason: str) -> None:
    with pytest.raises(HoldoutRefused):
        require_holdout_confirmation(Split.HOLDOUT, confirmed=confirmed, reason=reason)


def test_dev_needs_no_confirmation() -> None:
    require_holdout_confirmation(Split.DEV, confirmed=False, reason="")


def test_holdout_use_is_logged(gold: GoldSet, tmp_path: Path) -> None:
    meta, _ = _run(gold, "oracle", Split.HOLDOUT)
    log = tmp_path / "log" / "holdout.jsonl"
    log_holdout_use(log, meta, "  Gate 3 baseline  ")
    log_holdout_use(log, meta, "second run")
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [e["reason"] for e in lines] == ["Gate 3 baseline", "second run"]
    assert lines[0]["run_id"] == meta.run_id


# -- grading sheet -------------------------------------------------------------------------------


def test_sheet_lists_only_answers_that_need_a_person(gold: GoldSet, tmp_path: Path) -> None:
    _, records = _run(gold, "refuse")
    # a refusal fails M1 without a person; only the 3 scorable dev adversarial items remain
    assert write_grading_sheet(tmp_path / "none.csv", gold, records) == 3
    _, records = _run(gold, "oracle")
    rows = write_grading_sheet(tmp_path / "oracle.csv", gold, records)
    assert rows == 32 + 3  # answerable plus the scorable dev adversarial items


def test_sheet_is_never_overwritten(gold: GoldSet, tmp_path: Path) -> None:
    _, records = _run(gold, "oracle")
    path = tmp_path / "grades.csv"
    write_grading_sheet(path, gold, records)
    with pytest.raises(GradingError, match="already exists"):
        write_grading_sheet(path, gold, records)


def _fill(path: Path, values: dict[str, dict[str, str]]) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update(values.get(row["item_id"], {}))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_grades_round_trip_through_the_sheet(gold: GoldSet, tmp_path: Path) -> None:
    meta, records = _run(gold, "oracle")
    path = tmp_path / "grades.csv"
    write_grading_sheet(path, gold, records)
    answerable = sorted(
        i.id for i in gold.items if isinstance(i, AnswerableItem) and i.split == "dev"
    )
    first, second = answerable[0], answerable[1]
    _fill(
        path,
        {
            first: {"points_hit": "1, 2", "contradicts": ""},
            second: {"points_hit": "0", "contradicts": "y"},
            "G-ADV-001": {"verdict": "PASS"},
            "G-ADV-004": {"verdict": "fail"},
        },
    )
    grades = read_grades(path, gold)
    assert grades.points[first] == (1, 2)
    assert grades.points[second] == ()
    assert second in grades.contradicts
    assert grades.verdicts == {"G-ADV-001": True, "G-ADV-004": False}
    report = build_report(gold, meta, records, grades)
    assert report.m1.total == 2
    assert (report.adversarial.passed, report.adversarial.total) == (1, 2)
    assert report.adversarial_pending == 1


def test_a_point_number_that_does_not_exist_is_rejected(gold: GoldSet, tmp_path: Path) -> None:
    _, records = _run(gold, "oracle")
    path = tmp_path / "grades.csv"
    write_grading_sheet(path, gold, records)
    first = sorted(i.id for i in gold.items if isinstance(i, AnswerableItem))[0]
    _fill(path, {first: {"points_hit": "9"}})
    with pytest.raises(GradingError, match="no such key point"):
        read_grades(path, gold)


def test_a_bad_verdict_and_an_unknown_id_are_rejected(gold: GoldSet, tmp_path: Path) -> None:
    _, records = _run(gold, "oracle")
    path = tmp_path / "grades.csv"
    write_grading_sheet(path, gold, records)
    _fill(path, {"G-ADV-001": {"verdict": "maybe"}})
    with pytest.raises(GradingError, match="pass or fail"):
        read_grades(path, gold)
    path.write_text("item_id\nG-NOPE-001\n", encoding="utf-8")
    with pytest.raises(GradingError, match="unknown item id"):
        read_grades(path, gold)


# -- command line --------------------------------------------------------------------------------


def test_cli_run_grade_score_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runs = tmp_path / "runs"
    base = ["--gold", str(GOLD_FILE)]
    assert main([*base, "run", "--pipeline", "oracle", "--out-dir", str(runs)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "TEST DOUBLE" in out
    run_dir = next(runs.iterdir())
    assert main([*base, "grade-sheet", str(run_dir)]) == EXIT_OK
    assert main([*base, "score", str(run_dir)]) == EXIT_OK
    assert "M2 correct refusal         12/12" in capsys.readouterr().out


def test_cli_holdout_is_refused_without_confirmation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "log.jsonl"
    argv = [
        "--gold", str(GOLD_FILE), "run", "--pipeline", "oracle", "--split", "holdout",
        "--out-dir", str(tmp_path / "runs"), "--holdout-log", str(log),
    ]  # fmt: skip
    assert main(argv) == EXIT_HOLDOUT_REFUSED
    assert "sealed" in capsys.readouterr().out
    assert not log.exists()
    assert not (tmp_path / "runs").exists()


def test_cli_holdout_runs_when_confirmed_and_is_logged(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    argv = [
        "--gold", str(GOLD_FILE), "run", "--pipeline", "oracle", "--split", "holdout",
        "--out-dir", str(tmp_path / "runs"), "--holdout-log", str(log),
        "--confirm-holdout", "--reason", "test of the seal",
    ]  # fmt: skip
    assert main(argv) == EXIT_OK
    assert json.loads(log.read_text(encoding="utf-8"))["reason"] == "test of the seal"


def test_cli_reports_a_missing_run(tmp_path: Path) -> None:
    assert main(["--gold", str(GOLD_FILE), "score", str(tmp_path / "nope")]) == EXIT_UNREADABLE


def test_score_fails_loudly_when_an_explicit_grades_file_is_missing(tmp_path: Path) -> None:
    base = ["--gold", str(GOLD_FILE)]
    runs = tmp_path / "runs"
    assert main([*base, "run", "--pipeline", "oracle", "--out-dir", str(runs)]) == EXIT_OK
    (run_dir,) = runs.iterdir()
    missing = tmp_path / "typo.csv"
    assert main([*base, "score", str(run_dir), "--grades", str(missing)]) == EXIT_UNREADABLE
