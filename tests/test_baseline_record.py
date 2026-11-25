"""The recorded baseline must stay consistent with the gold set and with its own grades.

Changing the gold set after a baseline was measured silently invalidates the comparison. This
test turns that into a visible failure: the gold file's hash must match the one the baseline was
scored against, or the baseline must be re-recorded against a new gold version (docs/12).
"""

from __future__ import annotations

import json
from pathlib import Path

from bfs_reg_copilot.eval.gold import AdversarialItem, AnswerableItem, load_gold
from bfs_reg_copilot.eval.grading import read_grades
from bfs_reg_copilot.eval.metrics import points_ok
from bfs_reg_copilot.eval.runner import gold_sha256

REPO = Path(__file__).resolve().parent.parent
GOLD_FILE = REPO / "eval" / "gold" / "gold-v1.yaml"
BASELINES = REPO / "eval" / "baselines"
MANIFEST = BASELINES / "baseline-v1-dev.json"


def _manifest() -> dict[str, object]:
    loaded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_gold_set_is_unchanged_since_the_baseline_was_scored() -> None:
    recorded = _manifest()["gold_sha256"]
    assert gold_sha256(GOLD_FILE) == recorded, (
        "The gold file changed after baseline v1 was recorded. Do not edit gold-v1: add a "
        "labelled gold v2, re-run the baseline and record it (docs/12, docs/17)."
    )


def test_recorded_grades_load_against_the_gold_set() -> None:
    gold = load_gold(GOLD_FILE)
    grades = read_grades(BASELINES / str(_manifest()["grades_file"]), gold)
    dev_answerable = {
        i.id for i in gold.items if isinstance(i, AnswerableItem) and i.split == "dev"
    }
    assert set(grades.points) <= dev_answerable  # no grade for a hold-out or unknown item


def test_the_recorded_m1_can_be_rederived_from_the_grades() -> None:
    gold = load_gold(GOLD_FILE)
    manifest = _manifest()
    results = manifest["results"]
    assert isinstance(results, dict)
    m1 = results["m1"]
    grades = read_grades(BASELINES / str(manifest["grades_file"]), gold)
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    passed = sum(
        1
        for item_id, points in grades.points.items()
        if item_id not in grades.contradicts and points_ok(items[item_id], points)
    )
    assert len(grades.points) == m1["graded_by_person"]
    assert passed == m1["passed"]
    assert len(grades.points) + m1["failed_mechanically"] == m1["total"]
    dev_total = sum(1 for i in items.values() if i.split == "dev")
    assert m1["total"] == dev_total


def test_the_recorded_adversarial_verdicts_match() -> None:
    gold = load_gold(GOLD_FILE)
    manifest = _manifest()
    results = manifest["results"]
    assert isinstance(results, dict)
    grades = read_grades(BASELINES / str(manifest["grades_file"]), gold)
    adversarial = {i.id for i in gold.items if isinstance(i, AdversarialItem)}
    assert set(grades.verdicts) <= adversarial
    assert sum(grades.verdicts.values()) == results["m8"]["passed"]
    assert len(grades.verdicts) == results["m8"]["total"]
