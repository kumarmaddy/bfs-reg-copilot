"""The gold-context ceiling probe: gold chunks first, then normal hits, dev questions only."""

from __future__ import annotations

from pathlib import Path

import pytest

from bfs_reg_copilot.eval.cli import main
from bfs_reg_copilot.eval.gold import Split, load_gold
from bfs_reg_copilot.eval.runner import select_items
from bfs_reg_copilot.retrieve.gold_context import GoldContextRetriever, gold_context_map
from bfs_reg_copilot.retrieve.types import Hit

GOLD = Path(__file__).resolve().parent.parent / "eval" / "gold" / "gold-v2.yaml"


class _Inner:
    name = "dense:x"
    is_test_double = True

    def retrieve(self, question: str, k: int) -> list[Hit]:
        return [Hit(f"F:{n}", 0.1) for n in range(k)]


def test_gold_first_then_filler_up_to_k() -> None:
    r = GoldContextRetriever(_Inner(), {"q": ["G:1", "G:2"]})
    assert [h.chunk_id for h in r.retrieve("q", 5)] == ["G:1", "G:2", "F:0", "F:1", "F:2"]
    assert r.name == "gold-context+dense:x"


def test_more_gold_than_k_keeps_every_gold_chunk() -> None:
    r = GoldContextRetriever(_Inner(), {"q": [f"G:{n}" for n in range(7)]})
    assert [h.chunk_id for h in r.retrieve("q", 5)] == [f"G:{n}" for n in range(7)]


def test_filler_never_repeats_a_gold_chunk() -> None:
    r = GoldContextRetriever(_Inner(), {"q": ["F:0", "G:1"]})
    ids = [h.chunk_id for h in r.retrieve("q", 4)]
    assert ids == ["F:0", "G:1", "F:1", "F:2"]


def test_unknown_question_falls_back_to_the_inner_retriever() -> None:
    r = GoldContextRetriever(_Inner(), {})
    assert [h.chunk_id for h in r.retrieve("other", 2)] == ["F:0", "F:1"]


def test_map_covers_only_dev_answerable_questions() -> None:
    gold = load_gold(GOLD)
    mapping = gold_context_map(gold)
    dev = {
        i.question
        for i in gold.items
        if i.split == Split.DEV
        and i.id in {j.id for j in gold.items if hasattr(j, "supporting_chunks")}
    }
    assert set(mapping) == dev
    assert len(mapping) == 32


def test_select_items_only_filters_and_rejects_unknown() -> None:
    gold = load_gold(GOLD)
    ids, _ = select_items(gold, Split.DEV, None, ["G-STR-003", "G-E21-005"])
    assert sorted(ids) == ["G-E21-005", "G-STR-003"]
    with pytest.raises(ValueError, match="G-NOPE"):
        select_items(gold, Split.DEV, None, ["G-NOPE"])


def test_cli_refuses_gold_context_on_holdout_and_with_doubles(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "--gold",
                str(GOLD),
                "run",
                "--pipeline",
                "baseline",
                "--split",
                "holdout",
                "--confirm-holdout",
                "--reason",
                "test",
                "--gold-context",
            ]
        )
        != 0
    )
    assert "dev split" in capsys.readouterr().out
    assert main(["--gold", str(GOLD), "run", "--pipeline", "oracle", "--gold-context"]) != 0
