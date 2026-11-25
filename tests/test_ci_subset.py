"""A small, fixed evaluation that runs in CI with no model and no database.

It runs the real command line over the first three items of each kind (by id, so the subset never
changes unless the gold set does) with each test double, and checks the scores they must get.
This proves the harness, the scorer and the report still work end to end. It says NOTHING about
how good the real pipeline's answers are: that needs a model and is measured by hand (doc 17).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bfs_reg_copilot.eval.cli import EXIT_OK, main

REPO = Path(__file__).resolve().parent.parent
GOLD_FILE = REPO / "eval" / "gold" / "gold-v1.yaml"

# double -> lines the report must contain on the 3-per-kind subset
EXPECTED: dict[str, tuple[str, ...]] = {
    "oracle": (
        "M2 correct refusal         3/3 = 100%",
        "M4 retrieval hit@5         3/3 = 100%",
        "M5 fabricated citations    0/4 = 0.0%",
        "3 answers still need a person",
    ),
    "refuse": (
        "M1 cited-answer accuracy   0/3 = 0%",
        "M2 correct refusal         3/3 = 100%",
        "M4 retrieval hit@5         0/3 = 0%",
    ),
    "uncited": (
        "M1 cited-answer accuracy   0/3 = 0%",
        "M4 retrieval hit@5         3/3 = 100%",
    ),
    "wrong-cite": (
        "M1 cited-answer accuracy   0/3 = 0%",
        "M4 retrieval hit@5         0/3 = 0%",
        "M5 fabricated citations    0/3 = 0.0%",
    ),
    "fabricating": (
        "M2 correct refusal         0/3 = 0%",
        "M5 fabricated citations    4/4 = 100.0%",
    ),
}


@pytest.mark.parametrize("double", sorted(EXPECTED))
def test_each_double_gets_its_known_score_on_the_ci_subset(
    double: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--gold", str(GOLD_FILE)]
    runs = tmp_path / "runs"
    assert (
        main([*base, "run", "--pipeline", double, "--limit", "3", "--out-dir", str(runs)])
        == EXIT_OK
    )
    capsys.readouterr()
    (run_dir,) = runs.iterdir()
    assert main([*base, "score", str(run_dir)]) == EXIT_OK
    report = capsys.readouterr().out
    for line in EXPECTED[double]:
        assert line in report, f"{double}: expected {line!r} in\n{report}"
    assert "TEST DOUBLE" in report


def test_the_subset_is_the_first_three_ids_per_kind() -> None:
    from bfs_reg_copilot.eval.gold import Split, load_gold
    from bfs_reg_copilot.eval.runner import select_items

    ids, _ = select_items(load_gold(GOLD_FILE), Split.DEV, 3)
    assert len(ids) == 9  # three kinds, three each
