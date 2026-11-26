"""Rubric review sheet: each key point next to the gold source text, for a person to check.

Four questions fail although every supporting chunk reached the model, and two more omit a point
the source states. Either the model missed a fact the source states, or the rubric asks for more
than the source says. Only a person reading the source can tell. This writes one sheet per run
folder: the key points, the pass rule, the full text of the gold supporting chunks, and a line per
key point to fill in. It changes nothing; a rubric change is a separate, deliberate step that makes
a new gold version. The sheet holds corpus text, so it stays out of git.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet

DEFAULT_ITEMS = (
    "G-B10-001",
    "G-B13-001",
    "G-CPR-004",
    "G-E21-001",
    "G-STR-001",
    "G-STR-003",
)

HOW_TO = """Mark each key point with one letter after the arrow:
- S: the source text below states it (the model should have said it)
- P: the source implies it, but the wording of the key point adds a detail or needs an inference
- N: the source text below does not support it (the rubric asks for more than the source says)

A rubric is changed only for N, or for P when the pass rule *requires* that point. A model that
missed an S point is a model failure, never a reason to change the rubric. Read the source before
the model's answer."""


def render_sheet(gold: GoldSet, item_ids: Sequence[str], texts: Mapping[str, str]) -> list[str]:
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    lines = ["# Rubric review sheet", "", HOW_TO, ""]
    for item_id in item_ids:
        item = items[item_id]
        lines += [f"## {item.id}", "", f"**Question:** {item.question}", ""]
        lines += [f"**Pass rule:** {item.pass_rule.text}", "", "**Key points:**"]
        for number, point in enumerate(item.key_points, start=1):
            lines.append(f"{number}. {point}")
            lines.append("   -> ")
        lines += ["", "**Gold supporting chunks, full text:**", ""]
        for chunk_id in item.supporting_chunks:
            lines += [f"### `{chunk_id}`", "", texts.get(chunk_id, "(missing)"), ""]
        lines += ["**Decision for this item (keep / change; why):**", "", ""]
    return lines
