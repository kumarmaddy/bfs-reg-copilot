"""Comparing two runs question by question, and carrying grades across unchanged answers."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from bfs_reg_copilot.eval.cli import EXIT_OK, EXIT_UNREADABLE, main
from bfs_reg_copilot.eval.compare import CompareError, Rule, apply_rule, compare_runs, render
from bfs_reg_copilot.eval.fakes import DOUBLES
from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet, Split, load_gold
from bfs_reg_copilot.eval.grading import Grades, carry_grades, write_grading_sheet
from bfs_reg_copilot.eval.runner import run_eval
from bfs_reg_copilot.eval.types import RunMeta, RunRecord

REPO = Path(__file__).resolve().parent.parent
GOLD_FILE = REPO / "eval" / "gold" / "gold-v2.yaml"

Run = tuple[RunMeta, list[RunRecord], Grades]


@pytest.fixture(scope="module")
def gold() -> GoldSet:
    return load_gold(GOLD_FILE)


def _perfect(gold: GoldSet, records: list[RunRecord]) -> Grades:
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    return Grades(
        points={
            r.item_id: tuple(range(1, len(items[r.item_id].key_points) + 1))
            for r in records
            if r.item_id in items
        }
    )


def _run(gold: GoldSet, double: str, perfect: bool = True) -> Run:
    meta, records = run_eval(gold, DOUBLES[double](gold), Split.DEV, gold_hash="h" * 64, commit="c")
    return meta, records, _perfect(gold, records) if perfect else Grades()


def test_identical_runs_have_no_flips_and_the_rule_is_not_met(gold: GoldSet) -> None:
    run = _run(gold, "oracle")
    comparison = compare_runs(gold, run, run)
    assert (comparison.fixed, comparison.broken) == ((), ())
    assert comparison.still_pass == 32
    assert "do not adopt" in "\n".join(render(comparison, Rule()))


def test_every_question_fixed_meets_the_rule_and_is_large_enough_to_adopt(gold: GoldSet) -> None:
    comparison = compare_runs(gold, _run(gold, "uncited"), _run(gold, "oracle"))
    assert len(comparison.fixed) == 32
    assert comparison.broken == ()
    assert all(ok for _, ok in apply_rule(comparison, Rule()))
    assert "Verdict: adopt" in "\n".join(render(comparison, Rule()))


def test_a_small_gain_is_promising_not_proven(gold: GoldSet) -> None:
    comparison = compare_runs(gold, _run(gold, "uncited"), _run(gold, "oracle"))
    lines = render(comparison, Rule(proven_fixed=40))  # a bar this run cannot clear
    assert any("promising, not proven" in line for line in lines)


def test_everything_broken_fails_the_rule(gold: GoldSet) -> None:
    comparison = compare_runs(gold, _run(gold, "oracle"), _run(gold, "refuse"))
    assert len(comparison.broken) == 32
    assert comparison.refused_after - comparison.refused_before == 32
    results = dict(apply_rule(comparison, Rule()))
    assert not any(results.values()) or "do not adopt" in "\n".join(render(comparison, Rule()))


def test_fabricated_citations_fail_the_rule(gold: GoldSet) -> None:
    comparison = compare_runs(gold, _run(gold, "oracle"), _run(gold, "fabricating"))
    assert comparison.fabricated_after > 0
    failed = [text for text, ok in apply_rule(comparison, Rule(min_fixed=0)) if not ok]
    assert any("(b)" in text for text in failed)


def test_runs_on_different_gold_files_cannot_be_compared(gold: GoldSet) -> None:
    a = _run(gold, "oracle")
    b = (a[0].model_copy(update={"gold_sha256": "x" * 64}), a[1], a[2])
    with pytest.raises(CompareError, match="different gold"):
        compare_runs(gold, a, b)


def test_ungraded_answers_stop_the_comparison(gold: GoldSet) -> None:
    graded = _run(gold, "oracle")
    with pytest.raises(CompareError, match="still to grade"):
        compare_runs(gold, graded, _run(gold, "oracle", perfect=False))


def test_runs_over_different_questions_cannot_be_compared(gold: GoldSet) -> None:
    full = _run(gold, "oracle")
    meta, records = run_eval(
        gold, DOUBLES["oracle"](gold), Split.DEV, gold_hash="h" * 64, commit="c", limit=2
    )
    with pytest.raises(CompareError, match="different questions"):
        compare_runs(gold, full, (meta, records, _perfect(gold, records)))


def test_settings_that_differ_are_listed(gold: GoldSet) -> None:
    a = _run(gold, "oracle")
    b = (a[0].model_copy(update={"settings": {"k": "8"}}), a[1], a[2])
    comparison = compare_runs(
        gold, (a[0].model_copy(update={"settings": {"k": "5"}}), a[1], a[2]), b
    )
    assert comparison.settings_changed == {"k": ("5", "8")}


# --- carrying grades -------------------------------------------------------------------------


def _write_grades_csv(path: Path, gold: GoldSet, records: list[RunRecord]) -> int:
    sheet = path.with_name("sheet.csv")
    write_grading_sheet(sheet, gold, records)
    perfect = _perfect(gold, records)
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["item_id"] in perfect.points:
            row["points_hit"] = " ".join(str(n) for n in perfect.points[row["item_id"]])
        else:
            row["verdict"] = "pass"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def test_unchanged_answers_carry_their_grades_and_changed_ones_do_not(
    gold: GoldSet, tmp_path: Path
) -> None:
    meta, records, _ = _run(gold, "oracle")
    old_csv = tmp_path / "old.csv"
    total = _write_grades_csv(old_csv, gold, records)
    # a new run in which exactly one answer reads differently
    changed_id = next(r.item_id for r in records if r.kind == "answerable")
    new_records = [
        r.model_copy(update={"answer": r.answer.model_copy(update={"text": "reworded"})})
        if r.item_id == changed_id and r.answer
        else r
        for r in records
    ]
    sheet = tmp_path / "new-sheet.csv"
    write_grading_sheet(sheet, gold, new_records)
    carried, todo = carry_grades(sheet, new_records, records, old_csv, meta.run_id)
    assert (carried, todo) == (total - 1, 1)
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = {r["item_id"]: r for r in csv.DictReader(handle)}
    assert rows[changed_id]["points_hit"] == ""
    assert all(r["points_hit"] or r["verdict"] for i, r in rows.items() if i != changed_id)


def test_retrieval_depth_does_not_stop_a_grade_carrying(gold: GoldSet, tmp_path: Path) -> None:
    meta, records, _ = _run(gold, "oracle")
    old_csv = tmp_path / "old.csv"
    total = _write_grades_csv(old_csv, gold, records)
    deeper = [
        r.model_copy(
            update={
                "answer": r.answer.model_copy(
                    update={
                        "retrieved_chunks": (
                            *r.answer.retrieved_chunks,
                            "A-X:aaaaaaaaaaaa:s999:c000",
                        )
                    }
                )
            }
        )
        if r.answer
        else r
        for r in records
    ]
    sheet = tmp_path / "s.csv"
    write_grading_sheet(sheet, gold, deeper)
    assert carry_grades(sheet, deeper, records, old_csv, meta.run_id) == (total, 0)


# --- command line ----------------------------------------------------------------------------


def test_cli_flips_and_carry_flow(
    gold: GoldSet, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--gold", str(GOLD_FILE)]
    runs = tmp_path / "runs"
    for double in ("uncited", "oracle"):
        assert main([*base, "run", "--pipeline", double, "--out-dir", str(runs)]) == EXIT_OK
    capsys.readouterr()
    by_pipeline = {folder.name.split("-")[1]: folder for folder in runs.iterdir()}
    uncited, oracle = by_pipeline["uncited"], by_pipeline["oracle"]
    _, records = run_eval(gold, DOUBLES["oracle"](gold), Split.DEV, gold_hash="h" * 64, commit="c")
    grades_oracle = tmp_path / "oracle-grades.csv"
    _write_grades_csv(grades_oracle, gold, records)
    grades_uncited = tmp_path / "uncited-grades.csv"
    grades_uncited.write_text("item_id,points_hit,contradicts,verdict,note\n", encoding="utf-8")
    argv = [
        *base, "flips", str(uncited), str(oracle),
        "--grades-before", str(grades_uncited), "--grades-after", str(grades_oracle),
    ]  # fmt: skip
    assert main(argv) == EXIT_OK
    out = capsys.readouterr().out
    assert "Fixed (fail to pass)" in out
    assert "Verdict: adopt" in out
    missing = [*argv[:-1], str(tmp_path / "nope.csv")]
    assert main(missing) == EXIT_UNREADABLE


def test_cli_carry_works_across_gold_files_with_a_note(
    gold: GoldSet, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    older = tmp_path / "gold-older.yaml"
    older.write_text(GOLD_FILE.read_text(encoding="utf-8") + "\n# older copy\n", encoding="utf-8")
    folders = []
    for name, path in (("old", older), ("new", GOLD_FILE)):
        out_dir = tmp_path / f"runs-{name}"
        argv = ["--gold", str(path), "run", "--pipeline", "oracle", "--out-dir", str(out_dir)]
        assert main(argv) == EXIT_OK
        (folder,) = out_dir.iterdir()
        folders.append(folder)
    capsys.readouterr()
    old_run, new_run = folders
    _, records = run_eval(gold, DOUBLES["oracle"](gold), Split.DEV, gold_hash="h" * 64, commit="c")
    grades = tmp_path / "grades.csv"
    _write_grades_csv(grades, gold, records)
    argv = [
        "--gold", str(GOLD_FILE), "grade-sheet", str(new_run),
        "--carry-from", str(old_run), "--carry-grades", str(grades),
    ]  # fmt: skip
    assert main(argv) == EXIT_OK
    out = capsys.readouterr().out
    assert "different gold file" in out
    assert "0 still need a person" in out
