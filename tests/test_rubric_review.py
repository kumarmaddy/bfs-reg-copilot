"""The rubric review sheet: key points beside the full gold text, and the rule for changes."""

from __future__ import annotations

from pathlib import Path

import pytest

from bfs_reg_copilot.eval.cli import main
from bfs_reg_copilot.eval.gold import AnswerableItem, load_gold
from bfs_reg_copilot.eval.rubric_review import DEFAULT_ITEMS, HOW_TO, render_sheet

GOLD = Path(__file__).resolve().parent.parent / "eval" / "gold" / "gold-v2.yaml"


def test_default_items_exist_and_are_answerable() -> None:
    gold = load_gold(GOLD)
    answerable = {i.id for i in gold.items if isinstance(i, AnswerableItem)}
    assert set(DEFAULT_ITEMS) <= answerable


def test_sheet_has_key_points_chunk_text_and_a_line_to_fill_in() -> None:
    gold = load_gold(GOLD)
    item = next(i for i in gold.items if isinstance(i, AnswerableItem))
    texts = {c: f"TEXT OF {c}" for c in item.supporting_chunks}
    sheet = "\n".join(render_sheet(gold, [item.id], texts))
    assert item.question in sheet
    for number, point in enumerate(item.key_points, start=1):
        assert f"{number}. {point}" in sheet
    assert sheet.count("   -> ") == len(item.key_points)
    for chunk_id in item.supporting_chunks:
        assert f"TEXT OF {chunk_id}" in sheet
    assert "never a reason to change the rubric" in HOW_TO


def test_missing_chunk_text_is_shown_not_hidden() -> None:
    gold = load_gold(GOLD)
    sheet = "\n".join(render_sheet(gold, ["G-B10-001"], {}))
    assert "(missing)" in sheet


def test_cli_rejects_unknown_item(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--gold", str(GOLD), "rubric-review", "--items", "G-NOPE"])
    assert code != 0
    assert "G-NOPE" in capsys.readouterr().out
