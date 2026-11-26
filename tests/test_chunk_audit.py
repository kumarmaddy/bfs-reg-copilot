"""Chunk audit: low-value slots and lists cut across chunk boundaries (pure functions)."""

from __future__ import annotations

from bfs_reg_copilot.eval.chunk_audit import (
    ChunkRow,
    ItemAudit,
    cut_list_chunks,
    is_low_value,
    summarise_audit,
)


def _row(i: int, text: str, section: int = 3, count: int = 3) -> ChunkRow:
    return ChunkRow(f"S:h:s{section:03d}:c{i:03d}", "S", section, i, count, text)


def test_front_matter_and_tiny_chunks_are_low_value() -> None:
    assert is_low_value(_row(0, "x" * 500, section=0))
    assert is_low_value(_row(0, "short"))
    assert not is_low_value(_row(0, "x" * 500))


def test_a_list_running_across_a_boundary_marks_both_chunks() -> None:
    a = _row(0, "Intro\n- one\n- two")
    b = _row(1, "- three\n- four\nClosing")
    c = _row(2, "Plain paragraph")
    assert cut_list_chunks([a, b, c]) == {a.chunk_id, b.chunk_id}


def test_no_cut_when_the_boundary_is_prose_or_a_different_section() -> None:
    a = _row(0, "- one\nA closing sentence.")
    b = _row(1, "- two")
    other = _row(0, "- one\n- two", section=4, count=1)
    assert cut_list_chunks([a, b, other]) == set()


def test_summary_counts_slots_and_names_cut_list_questions() -> None:
    audits = [
        ItemAudit("G-A", True, 5, 1, 1, 1, 0, 0),
        ItemAudit("G-B", False, 5, 2, 1, 2, 1, 1),
    ]
    text = "\n".join(summarise_audit(audits, corpus_cut=4, corpus_boundaries=40))
    assert "low-value (front matter, or under 150 chars): 3 (30%)" in text
    assert "pass 1, fail 1, ungraded 0" in text
    assert "corpus chunk boundaries inside a list: 4 of 40" in text
    assert "G-B: 1 cut-list gold chunk(s) in context, 1 missing (fail)" in text
