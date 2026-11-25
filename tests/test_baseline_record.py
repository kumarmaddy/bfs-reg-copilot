"""The recorded baselines must stay consistent with the gold set and with their own grades.

Changing a gold file after a baseline was scored against it silently invalidates the comparison.
These tests turn that into a visible failure: each gold file's hash must match the one its baseline
was scored against, or the change must go into a new, labelled gold version (docs/12).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bfs_reg_copilot.eval.gold import AdversarialItem, AnswerableItem, load_gold
from bfs_reg_copilot.eval.grading import read_grades
from bfs_reg_copilot.eval.metrics import points_ok
from bfs_reg_copilot.eval.runner import gold_sha256

REPO = Path(__file__).resolve().parent.parent
GOLD_DIR = REPO / "eval" / "gold"
BASELINES = REPO / "eval" / "baselines"
MANIFESTS = sorted(BASELINES.glob("baseline-*-dev.json"))

# The only items whose rubric differs between gold v1 and gold v2 (decision D-2, docs/20).
V2_CORRECTED = {"G-E23-001", "G-B10-002"}


def _manifest(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _gold_path(manifest: dict[str, Any]) -> Path:
    return GOLD_DIR / f"gold-v{manifest['gold_version']}.yaml"


def test_both_baselines_are_recorded() -> None:
    assert [m.name for m in MANIFESTS] == ["baseline-v1-dev.json", "baseline-v2-dev.json"]


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.stem)
def test_gold_set_is_unchanged_since_the_baseline_was_scored(path: Path) -> None:
    manifest = _manifest(path)
    assert gold_sha256(_gold_path(manifest)) == manifest["gold_sha256"], (
        "A gold file changed after its baseline was recorded. Do not edit a recorded gold "
        "version: add a new labelled version, re-score the baseline and record it (docs/12, 17)."
    )


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.stem)
def test_recorded_grades_load_against_their_gold_set(path: Path) -> None:
    manifest = _manifest(path)
    gold = load_gold(_gold_path(manifest))
    grades = read_grades(BASELINES / manifest["grades_file"], gold)
    dev_answerable = {
        i.id for i in gold.items if isinstance(i, AnswerableItem) and i.split == "dev"
    }
    assert set(grades.points) <= dev_answerable  # no grade for a hold-out or unknown item


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.stem)
def test_the_recorded_m1_can_be_rederived_from_the_grades(path: Path) -> None:
    manifest = _manifest(path)
    gold = load_gold(_gold_path(manifest))
    m1 = manifest["results"]["m1"]
    grades = read_grades(BASELINES / manifest["grades_file"], gold)
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    passed = sum(
        1
        for item_id, points in grades.points.items()
        if item_id not in grades.contradicts and points_ok(items[item_id], points)
    )
    assert len(grades.points) == m1["graded_by_person"]
    assert passed == m1["passed"]
    assert len(grades.points) + m1["failed_mechanically"] == m1["total"]
    assert m1["total"] == sum(1 for i in items.values() if i.split == "dev")


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.stem)
def test_the_recorded_adversarial_verdicts_match(path: Path) -> None:
    manifest = _manifest(path)
    gold = load_gold(_gold_path(manifest))
    grades = read_grades(BASELINES / manifest["grades_file"], gold)
    adversarial = {i.id for i in gold.items if isinstance(i, AdversarialItem)}
    assert set(grades.verdicts) <= adversarial
    assert sum(grades.verdicts.values()) == manifest["results"]["m8"]["passed"]
    assert len(grades.verdicts) == manifest["results"]["m8"]["total"]


def test_v2_differs_from_v1_only_in_the_two_corrected_rubrics() -> None:
    v1 = load_gold(GOLD_DIR / "gold-v1.yaml")
    v2 = load_gold(GOLD_DIR / "gold-v2.yaml")
    assert (v1.version, v2.version) == (1, 2)
    assert [i.id for i in v1.items] == [i.id for i in v2.items]  # nothing added, removed or moved
    assert v1.split_seed == v2.split_seed
    assert v1.corpus == v2.corpus
    changed = {a.id for a, b in zip(v1.items, v2.items, strict=True) if a != b}
    assert changed == V2_CORRECTED
    for a, b in zip(v1.items, v2.items, strict=True):
        assert a.split == b.split  # the hold-out is exactly the same set
        assert a.question == b.question  # the questions themselves never changed


def test_v2_grades_differ_from_v1_grades_only_on_the_two_corrected_items() -> None:
    def rows(name: str) -> dict[str, dict[str, str]]:
        import csv

        with (BASELINES / name).open(encoding="utf-8", newline="") as handle:
            return {r["item_id"]: r for r in csv.DictReader(handle)}

    v1, v2 = rows("baseline-v1-dev.grades.csv"), rows("baseline-v2-dev.grades.csv")
    assert v1.keys() == v2.keys()
    differing = {
        i
        for i in v1
        if (v1[i]["points_hit"], v1[i]["contradicts"])
        != (v2[i]["points_hit"], v2[i]["contradicts"])
    }
    assert differing <= V2_CORRECTED
