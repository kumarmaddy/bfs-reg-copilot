"""The mechanical scoring rules, one at a time."""

from __future__ import annotations

import pytest

from bfs_reg_copilot.eval.gold import AnswerableItem, PassRule
from bfs_reg_copilot.eval.metrics import (
    cites_support,
    fabricated_citations,
    hit_at_k,
    percentile,
    points_ok,
    section_id,
    wilson_interval,
)
from bfs_reg_copilot.eval.types import PipelineAnswer

SHA = "a" * 12
SUPPORT = f"A-OSFI-E23:{SHA}:s005:c000"


def _item(min_points: int = 2, required: tuple[int, ...] = ()) -> AnswerableItem:
    return AnswerableItem(
        id="G-E23-001",
        kind="answerable",
        split="dev",
        source="A-OSFI-E23",
        type="lookup",
        difficulty="easy",
        question="What does the guideline say about models?",
        key_points=("one", "two", "three"),
        pass_rule=PassRule(min_points=min_points, required_points=required, text="x"),
        supporting_chunks=(SUPPORT,),
    )


def _answer(cited: tuple[str, ...] = (), retrieved: tuple[str, ...] = ()) -> PipelineAnswer:
    return PipelineAnswer(text="t", refused=False, cited_chunks=cited, retrieved_chunks=retrieved)


def test_section_id_drops_the_chunk_number() -> None:
    assert section_id(f"A-OSFI-E23:{SHA}:s005:c002") == f"A-OSFI-E23:{SHA}:s005"


def test_a_chunk_from_the_same_section_counts_as_support() -> None:
    other_chunk = f"A-OSFI-E23:{SHA}:s005:c001"
    assert cites_support(_item(), _answer(cited=(other_chunk,)))


def test_a_chunk_from_another_section_does_not() -> None:
    assert not cites_support(_item(), _answer(cited=(f"A-OSFI-E23:{SHA}:s006:c000",)))


def test_no_citation_is_no_support() -> None:
    assert not cites_support(_item(), _answer())


def test_hit_at_k_only_looks_at_the_first_k() -> None:
    filler = tuple(f"A-OSFI-E23:{SHA}:s{n:03d}:c000" for n in range(10, 15))
    assert hit_at_k(_item(), _answer(retrieved=(*filler[:4], SUPPORT)), k=5)
    assert not hit_at_k(_item(), _answer(retrieved=(*filler, SUPPORT)), k=5)


def test_fabricated_citations_are_those_not_retrieved() -> None:
    cited = (SUPPORT, f"A-OSFI-E23:{SHA}:s009:c000")
    fabricated = fabricated_citations(_answer(cited=cited, retrieved=(SUPPORT,)))
    assert fabricated == (f"A-OSFI-E23:{SHA}:s009:c000",)


def test_citing_another_chunk_of_a_retrieved_section_is_not_fabrication() -> None:
    cited = (f"A-OSFI-E23:{SHA}:s005:c001",)
    assert fabricated_citations(_answer(cited=cited, retrieved=(SUPPORT,))) == ()


@pytest.mark.parametrize(
    ("min_points", "required", "hit", "expected"),
    [
        (2, (), (1, 2), True),
        (2, (), (1,), False),
        (2, (1,), (2, 3), False),  # enough points, but the required one is missing
        (2, (1,), (1, 3), True),
        (3, (), (1, 2, 3), True),
        (2, (), (1, 1, 1), False),  # repeats do not count twice
    ],
)
def test_pass_rule(
    min_points: int, required: tuple[int, ...], hit: tuple[int, ...], expected: bool
) -> None:
    assert points_ok(_item(min_points, required), hit) is expected


def test_wilson_interval_edges_and_known_values() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.722, abs=0.005)
    assert high == 1.0
    low, high = wilson_interval(36, 40)
    assert low == pytest.approx(0.769, abs=0.01)
    assert high == pytest.approx(0.960, abs=0.01)


def test_percentile_uses_nearest_rank() -> None:
    values = [float(n) for n in range(1, 101)]
    assert percentile(values, 0.95) == 95.0
    assert percentile(values, 0.50) == 50.0
    assert percentile([], 0.95) == 0.0
