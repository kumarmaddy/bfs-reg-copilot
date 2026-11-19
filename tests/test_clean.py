"""Tests for cleaning. Fixtures are small invented pages; no publisher text is committed."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bfs_reg_copilot.ingest import (
    CLEANER_VERSION,
    CleaningError,
    FetchResult,
    RawStore,
    RawStoreError,
    clean_html,
    clean_record,
    read_cleaned,
    write_cleaned,
)
from bfs_reg_copilot.ingest.cleaned_store import cleaned_path
from bfs_reg_copilot.ingest.cli import (
    EXIT_FETCH_FAILED,
    EXIT_OK,
    EXIT_REFUSED,
    main,
)
from bfs_reg_copilot.registry import load_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "data" / "sources" / "register.yaml"

PAGE = """<html><head><title>Sample Guideline - Example Agency</title>
<script>var secret = "tracking";</script></head><body>
<nav><ul><li><a href="/">Home menu</a></li></ul></nav>
<main>
<h1 id="wb-cont">Sample Guideline</h1>
<p>Intro paragraph.</p>
<h2>In this guidance</h2>
<ul><li><a href="#s1">1. Governance</a></li></ul>
<h2 id="s1">1. Governance</h2>
<p>Boards must <strong>oversee</strong> risk.<br>Second line.</p>
<h3>1.1 Roles</h3>
<ul><li>Board<ul><li>Chair</li><li>Members</li></ul></li><li>Management</li></ul>
<h2>In this section</h2>
<ul><li><a href="#s2">2.1 Reporting</a></li></ul>
<h3>1.2 Reporting</h3>
<table><caption>Deadlines</caption>
<tr><th>Item</th><th>Days</th></tr><tr><td>Report</td><td>30</td></tr></table>
<details><summary>More detail</summary><p>Hidden detail text.</p></details>
<h2>2. Empty parent</h2>
<h3>2.1 Child</h3>
<p>Child&nbsp;text   with   spaces.</p>
<form><label>Your email</label><input type="text"></form>
<div class="pagedetails"><button>Report a problem</button>
<dl id="wb-dtmd"><dt>Date modified:</dt><dd><time>2025-05-22</time></dd></dl></div>
</main>
<footer><p>Footer junk</p></footer></body></html>"""


def _by_heading(html: str = PAGE) -> dict[str, str]:
    return {s.heading: s.text for s in clean_html(html).sections}


def test_sections_follow_headings_with_breadcrumb_paths() -> None:
    page = clean_html(PAGE)
    paths = {s.heading: s.path for s in page.sections}
    assert paths["1. Governance"] == ("Sample Guideline", "1. Governance")
    assert paths["1.1 Roles"] == ("Sample Guideline", "1. Governance", "1.1 Roles")
    assert [s.index for s in page.sections] == list(range(len(page.sections)))
    assert page.page_title == "Sample Guideline - Example Agency"


def test_anchor_ids_are_kept() -> None:
    anchors = {s.heading: s.anchor for s in clean_html(PAGE).sections}
    assert anchors["1. Governance"] == "s1"
    assert anchors["1.1 Roles"] is None


def test_page_chrome_is_dropped() -> None:
    everything = "\n".join(_by_heading().values())
    for junk in ("tracking", "Home menu", "Footer junk", "Your email", "Report a problem"):
        assert junk not in everything


def test_navigation_link_lists_are_dropped_and_do_not_break_the_path() -> None:
    page = clean_html(PAGE)
    assert not any("In this" in s.heading for s in page.sections)
    reporting = next(s for s in page.sections if s.heading == "1.2 Reporting")
    assert reporting.path == ("Sample Guideline", "1. Governance", "1.2 Reporting")
    assert "2.1 Reporting" not in "\n".join(s.text for s in page.sections)


def test_inline_markup_does_not_split_words_and_br_is_a_newline() -> None:
    assert _by_heading()["1. Governance"] == "Boards must oversee risk.\nSecond line."


def test_nested_lists_are_indented() -> None:
    assert _by_heading()["1.1 Roles"] == "- Board\n  - Chair\n  - Members\n- Management"


def test_table_rows_become_pipe_separated_lines() -> None:
    text = _by_heading()["1.2 Reporting"]
    assert "Deadlines" in text
    assert "Item | Days" in text
    assert "Report | 30" in text


def test_details_summary_and_body_are_kept() -> None:
    text = _by_heading()["1.2 Reporting"]
    assert "More detail" in text
    assert "Hidden detail text." in text


def test_whitespace_and_nbsp_are_normalised() -> None:
    assert _by_heading()["2.1 Child"] == "Child text with spaces."


def test_heading_without_body_is_omitted_but_stays_in_child_paths() -> None:
    page = clean_html(PAGE)
    assert not any(s.heading == "2. Empty parent" for s in page.sections)
    child = next(s for s in page.sections if s.heading == "2.1 Child")
    assert child.path[-2:] == ("2. Empty parent", "2.1 Child")


def test_date_modified_is_metadata_not_text() -> None:
    page = clean_html(PAGE)
    assert page.date_modified == "2025-05-22"
    assert "2025-05-22" not in "\n".join(s.text for s in page.sections)


def test_page_without_main_is_rejected() -> None:
    with pytest.raises(CleaningError, match="main"):
        clean_html("<html><body><p>hi</p></body></html>")


def test_page_without_text_is_rejected() -> None:
    with pytest.raises(CleaningError, match="no text"):
        clean_html("<html><body><main><h1>Title only</h1></main></body></html>")


def test_bytes_input_is_accepted() -> None:
    assert clean_html(PAGE.encode("utf-8")).sections


# -- lineage -------------------------------------------------------------------------------


def _store_page(root: Path, source_id: str = "A-OSFI-E21") -> tuple[RawStore, FetchResult]:
    result = FetchResult(
        source_id=source_id,
        requested_url="https://example.gc.ca/p",
        final_url="https://example.gc.ca/p",
        status_code=200,
        content_type="text/html",
        body=PAGE.encode("utf-8"),
        retrieved_at=datetime(2026, 11, 19, 9, 0, tzinfo=UTC),
        etag=None,
        last_modified=None,
    )
    store = RawStore(root)
    store.save(result)
    return store, result


def test_cleaned_document_carries_its_lineage(tmp_path: Path) -> None:
    store, result = _store_page(tmp_path / "raw")
    record = store.latest(result.source_id)
    assert record is not None
    doc = clean_record(store, record)
    assert doc.source_id == "A-OSFI-E21"
    assert doc.raw_sha256 == record.sha256
    assert doc.retrieved_at == result.retrieved_at
    assert doc.final_url == result.final_url
    assert doc.cleaner_version == CLEANER_VERSION


def test_cleaned_document_round_trips_through_disk(tmp_path: Path) -> None:
    store, result = _store_page(tmp_path / "raw")
    record = store.latest(result.source_id)
    assert record is not None
    doc = clean_record(store, record)
    path = write_cleaned(tmp_path / "cleaned", doc)
    assert path == cleaned_path(tmp_path / "cleaned", doc)
    assert path.name == f"{record.sha256}.v{CLEANER_VERSION}.json"
    assert read_cleaned(path) == doc
    assert list(path.parent.glob("*.tmp")) == []


def test_cleaning_refuses_a_tampered_raw_blob(tmp_path: Path) -> None:
    store, result = _store_page(tmp_path / "raw")
    record = store.latest(result.source_id)
    assert record is not None
    store.blob_path(record).write_bytes(b"<main><h1>x</h1><p>forged</p></main>")
    with pytest.raises(RawStoreError, match="hash"):
        clean_record(store, record)


# -- command line --------------------------------------------------------------------------


def _ingestible_id() -> str:
    return load_register(REGISTER_PATH).ingestible()[0].id


def test_cli_clean_writes_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source_id = _ingestible_id()
    _store_page(tmp_path / "raw", source_id)
    args = ["--register", str(REGISTER_PATH), "clean", source_id]
    args += ["--raw-dir", str(tmp_path / "raw"), "--out-dir", str(tmp_path / "out")]
    assert main(args) == EXIT_OK
    assert capsys.readouterr().out.startswith("CLEANED:")
    assert len(list((tmp_path / "out" / source_id).glob("*.json"))) == 1


def test_cli_clean_without_a_stored_fetch_fails(tmp_path: Path) -> None:
    args = ["--register", str(REGISTER_PATH), "clean", _ingestible_id()]
    args += ["--raw-dir", str(tmp_path / "raw"), "--out-dir", str(tmp_path / "out")]
    assert main(args) == EXIT_FETCH_FAILED


def test_cli_clean_refuses_a_pending_source(tmp_path: Path) -> None:
    pending_id = load_register(REGISTER_PATH).pending[0].id
    args = ["--register", str(REGISTER_PATH), "clean", pending_id]
    args += ["--raw-dir", str(tmp_path / "raw"), "--out-dir", str(tmp_path / "out")]
    assert main(args) == EXIT_REFUSED
    assert not (tmp_path / "out").exists()


# -- real corpus (local only) --------------------------------------------------------------


def test_every_locally_stored_page_cleans_into_traceable_sections() -> None:
    """Runs only on a machine that has fetched pages; CI has none and skips this."""
    raw_root = ROOT / "data" / "raw"
    if not raw_root.exists():
        pytest.skip("no local raw data")
    store = RawStore(raw_root)
    checked = 0
    for folder in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        record = store.latest(folder.name)
        if record is None:
            continue
        doc = clean_record(store, record)
        assert doc.sections, folder.name
        assert all(s.path and s.path[-1] == s.heading and s.text for s in doc.sections)
        assert "Report a problem" not in "\n".join(s.text for s in doc.sections)
        checked += 1
    if checked == 0:
        pytest.skip("no local raw data")
