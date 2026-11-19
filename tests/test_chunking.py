"""Tests for chunking. Documents are built in code from invented text."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bfs_reg_copilot.ingest import (
    CHUNKER_VERSION,
    CLEANER_VERSION,
    Chunk,
    ChunkingConfig,
    CleanedDocument,
    FetchResult,
    RawStore,
    Section,
    chunk_document,
    clean_record,
    read_chunks,
    write_chunks,
    write_cleaned,
)
from bfs_reg_copilot.ingest.chunk_store import chunks_path
from bfs_reg_copilot.ingest.cli import EXIT_FETCH_FAILED, EXIT_OK, EXIT_REFUSED, main
from bfs_reg_copilot.registry import load_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "data" / "sources" / "register.yaml"
SMALL = ChunkingConfig(max_chars=200, overlap_chars=40)
SHA = "a" * 64


def _section(index: int, text: str, heading: str = "H") -> Section:
    return Section(
        index=index,
        level=2,
        heading=heading,
        path=("Title", heading),
        anchor=f"s{index}",
        text=text,
    )


def _doc(*sections: Section) -> CleanedDocument:
    return CleanedDocument(
        source_id="A-OSFI-E21",
        raw_sha256=SHA,
        retrieved_at=datetime(2026, 11, 19, 9, 0, tzinfo=UTC),
        final_url="https://example.gc.ca/p",
        cleaner_version=CLEANER_VERSION,
        page_title="Title",
        date_modified="2025-01-01",
        sections=tuple(sections),
    )


def _lines(n: int, width: int = 60) -> str:
    return "\n".join(f"Line {i:03d} " + "x" * (width - 9) for i in range(n))


def _check_invariants(doc: CleanedDocument, chunks: tuple[Chunk, ...], max_chars: int) -> None:
    by_section = {s.index: s for s in doc.sections}
    seen_ids: set[str] = set()
    for chunk in chunks:
        section = by_section[chunk.section_index]
        assert chunk.text == section.text[chunk.section_start : chunk.section_end]
        assert 0 < len(chunk.text) <= max_chars
        assert chunk.section_path == section.path
        assert chunk.chunk_id not in seen_ids
        seen_ids.add(chunk.chunk_id)
    for section in doc.sections:
        mine = [c for c in chunks if c.section_index == section.index]
        assert [c.chunk_index for c in mine] == list(range(len(mine)))
        assert {c.chunk_count for c in mine} == {len(mine)}
        for earlier, later in itertools.pairwise(mine):
            gap = section.text[earlier.section_end : later.section_start]
            assert gap.strip() == ""  # nothing is lost between neighbours
            assert later.section_start > earlier.section_start  # always moves forward
        # every character that is not whitespace lies inside at least one chunk
        covered = [False] * len(section.text)
        for chunk in mine:
            for position in range(chunk.section_start, chunk.section_end):
                covered[position] = True
        missing = [i for i, ch in enumerate(section.text) if not ch.isspace() and not covered[i]]
        assert missing == []


def test_short_section_is_one_chunk_with_full_lineage() -> None:
    doc = _doc(_section(0, "Short body."))
    (chunk,) = chunk_document(doc, SMALL)
    assert chunk.text == "Short body."
    assert chunk.chunk_id == f"A-OSFI-E21:{SHA[:12]}:s000:c000"
    assert (chunk.source_id, chunk.raw_sha256) == ("A-OSFI-E21", SHA)
    assert chunk.retrieved_at == doc.retrieved_at
    assert chunk.final_url == doc.final_url
    assert chunk.date_modified == "2025-01-01"
    assert chunk.anchor == "s0"
    assert (chunk.chunk_index, chunk.chunk_count) == (0, 1)


def test_chunks_never_cross_sections() -> None:
    doc = _doc(_section(0, "first body", "One"), _section(1, "second body", "Two"))
    chunks = chunk_document(doc, SMALL)
    assert [c.section_heading for c in chunks] == ["One", "Two"]
    assert [c.text for c in chunks] == ["first body", "second body"]


def test_long_section_splits_on_line_boundaries_and_overlaps() -> None:
    # 30-character lines, so one whole line fits inside the 40-character overlap
    doc = _doc(_section(0, _lines(40, width=30)))
    chunks = chunk_document(doc, SMALL)
    assert len(chunks) > 3
    _check_invariants(doc, chunks, SMALL.max_chars)
    for chunk in chunks:
        assert all(line.startswith("Line ") for line in chunk.text.split("\n"))
    assert all(
        later.section_start < earlier.section_end for earlier, later in itertools.pairwise(chunks)
    )


def test_overlap_is_whole_lines_only() -> None:
    # 60-character lines cannot fit in a 40-character overlap, so there is none
    doc = _doc(_section(0, _lines(12, width=60)))
    chunks = chunk_document(doc, SMALL)
    assert all(a.section_end <= b.section_start for a, b in itertools.pairwise(chunks))


def test_zero_overlap_means_no_repeated_text() -> None:
    config = ChunkingConfig(max_chars=200, overlap_chars=0)
    doc = _doc(_section(0, _lines(12)))
    chunks = chunk_document(doc, config)
    _check_invariants(doc, chunks, 200)
    assert all(a.section_end <= b.section_start for a, b in itertools.pairwise(chunks))


def test_overlap_is_small() -> None:
    doc = _doc(_section(0, _lines(30)))
    chunks = chunk_document(doc, SMALL)
    for earlier, later in itertools.pairwise(chunks):
        assert earlier.section_end - later.section_start <= SMALL.overlap_chars


def test_long_line_is_cut_at_sentence_ends() -> None:
    sentence = "This sentence is exactly fifty characters long, ok."  # 51 chars
    doc = _doc(_section(0, " ".join([sentence] * 12)))
    chunks = chunk_document(doc, SMALL)
    assert len(chunks) > 1
    _check_invariants(doc, chunks, SMALL.max_chars)
    assert all(c.text.endswith(".") for c in chunks)


def test_long_line_without_sentences_is_cut_at_spaces() -> None:
    doc = _doc(_section(0, " ".join(["word"] * 200)))
    chunks = chunk_document(doc, SMALL)
    _check_invariants(doc, chunks, SMALL.max_chars)
    assert all(c.text.split(" ")[0] == "word" and c.text.split(" ")[-1] == "word" for c in chunks)


def test_unbroken_text_is_cut_hard_as_a_last_resort() -> None:
    doc = _doc(_section(0, "z" * 500))
    chunks = chunk_document(doc, SMALL)
    _check_invariants(doc, chunks, SMALL.max_chars)
    assert "".join(c.text for c in chunks) == "z" * 500


def test_chunking_is_deterministic() -> None:
    doc = _doc(_section(0, _lines(20)), _section(1, "tail"))
    assert chunk_document(doc, SMALL) == chunk_document(doc, SMALL)


def test_contextualised_text_adds_the_heading_path_but_text_stays_verbatim() -> None:
    (chunk,) = chunk_document(_doc(_section(0, "Body.")), SMALL)
    assert chunk.contextualised() == "Title > H\nBody."
    assert chunk.text == "Body."


@pytest.mark.parametrize(("max_chars", "overlap"), [(100, 0), (1000, -1), (1000, 501), (1000, 900)])
def test_bad_config_is_rejected(max_chars: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="must"):
        ChunkingConfig(max_chars=max_chars, overlap_chars=overlap)


def test_default_config_keeps_chunks_within_limit() -> None:
    doc = _doc(_section(0, _lines(400, width=120)))
    chunks = chunk_document(doc)
    _check_invariants(doc, chunks, ChunkingConfig().max_chars)


# -- storage -------------------------------------------------------------------------------


def test_chunks_round_trip_through_disk(tmp_path: Path) -> None:
    chunks = chunk_document(_doc(_section(0, _lines(12))), SMALL)
    path = write_chunks(tmp_path, chunks, CLEANER_VERSION)
    assert path == chunks_path(tmp_path, "A-OSFI-E21", SHA, CLEANER_VERSION)
    assert path.name == f"{SHA}.v{CLEANER_VERSION}.c{CHUNKER_VERSION}.jsonl"
    assert read_chunks(path) == chunks
    assert list(path.parent.glob("*.tmp")) == []


def test_empty_chunk_list_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        write_chunks(tmp_path, (), CLEANER_VERSION)


def test_mixed_sources_are_refused(tmp_path: Path) -> None:
    one = chunk_document(_doc(_section(0, "a")), SMALL)
    other = one[0].model_copy(update={"source_id": "A-OSFI-B10"})
    with pytest.raises(ValueError, match="same source"):
        write_chunks(tmp_path, (one[0], other), CLEANER_VERSION)


# -- command line --------------------------------------------------------------------------

PAGE = "<main><h1>T</h1><p>Intro.</p><h2>One</h2><p>Body text.</p></main>"


def _prepare(tmp_path: Path, source_id: str, *, clean: bool = True) -> None:
    store = RawStore(tmp_path / "raw")
    store.save(
        FetchResult(
            source_id=source_id,
            requested_url="https://example.gc.ca/p",
            final_url="https://example.gc.ca/p",
            status_code=200,
            content_type="text/html",
            body=PAGE.encode(),
            retrieved_at=datetime(2026, 11, 19, 9, 0, tzinfo=UTC),
            etag=None,
            last_modified=None,
        )
    )
    if clean:
        record = store.latest(source_id)
        assert record is not None
        write_cleaned(tmp_path / "cleaned", clean_record(store, record))


def _args(tmp_path: Path, source_id: str) -> list[str]:
    return [
        "--register", str(REGISTER_PATH), "chunk", source_id,
        "--raw-dir", str(tmp_path / "raw"),
        "--cleaned-dir", str(tmp_path / "cleaned"),
        "--out-dir", str(tmp_path / "out"),
    ]  # fmt: skip


def test_cli_chunk_writes_a_traceable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_id = load_register(REGISTER_PATH).ingestible()[0].id
    _prepare(tmp_path, source_id)
    assert main(_args(tmp_path, source_id)) == EXIT_OK
    assert capsys.readouterr().out.startswith("CHUNKED:")
    (file,) = (tmp_path / "out" / source_id).glob("*.jsonl")
    assert {c.source_id for c in read_chunks(file)} == {source_id}


def test_cli_chunk_needs_cleaning_first(tmp_path: Path) -> None:
    source_id = load_register(REGISTER_PATH).ingestible()[0].id
    _prepare(tmp_path, source_id, clean=False)
    assert main(_args(tmp_path, source_id)) == EXIT_FETCH_FAILED


def test_cli_chunk_needs_a_fetch_first(tmp_path: Path) -> None:
    source_id = load_register(REGISTER_PATH).ingestible()[0].id
    assert main(_args(tmp_path, source_id)) == EXIT_FETCH_FAILED


def test_cli_chunk_refuses_a_pending_source(tmp_path: Path) -> None:
    pending_id = load_register(REGISTER_PATH).pending[0].id
    assert main(_args(tmp_path, pending_id)) == EXIT_REFUSED
    assert not (tmp_path / "out").exists()


# -- real corpus (local only) --------------------------------------------------------------


def test_every_locally_cleaned_page_chunks_cleanly() -> None:
    """Runs only on a machine that has run `clean`; CI has no data and skips this."""
    from bfs_reg_copilot.ingest import read_cleaned

    cleaned_root = ROOT / "data" / "cleaned"
    files = sorted(cleaned_root.rglob("*.json")) if cleaned_root.exists() else []
    if not files:
        pytest.skip("no local cleaned data")
    for file in files:
        doc = read_cleaned(file)
        _check_invariants(doc, chunk_document(doc), ChunkingConfig().max_chars)
