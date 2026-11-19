"""Tests for the data-quality checks. Each check is shown to catch the fault it exists for."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from bfs_reg_copilot.ingest import (
    CLEANER_VERSION,
    Chunk,
    ChunkingConfig,
    CleanedDocument,
    DqConfig,
    FetchResult,
    Finding,
    RawStore,
    Severity,
    chunk_document,
    clean_record,
    run_dq,
    write_chunks,
    write_cleaned,
)
from bfs_reg_copilot.ingest.cli import EXIT_DQ_FAILED, EXIT_OK, main
from bfs_reg_copilot.ingest.dq import (
    check_chunk_integrity,
    check_chunk_lineage,
    check_governance_leaks,
    check_page_coverage,
    check_repo_hygiene,
)
from bfs_reg_copilot.registry import Register, Source, load_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "data" / "sources" / "register.yaml"
RETRIEVED = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
SMALL = ChunkingConfig(max_chars=200, overlap_chars=40)
SMALL_DQ = DqConfig(max_chars=200)


def _paragraphs(count: int, start: int = 0) -> str:
    return "".join(
        f"<p>Paragraph {i} explains a requirement in plain words so that it has some length.</p>"
        for i in range(start, start + count)
    )


PAGE = (
    f"<html><body><main><h1>Title</h1>{_paragraphs(6)}"
    f"<h2>Part</h2>{_paragraphs(30, start=6)}</main></body></html>"
)


@pytest.fixture(scope="module")
def register() -> Register:
    return load_register(REGISTER_PATH)


@pytest.fixture
def source(register: Register) -> Source:
    return register.ingestible()[0]


@dataclass
class Pipeline:
    raw: Path
    cleaned: Path
    curated: Path
    store: RawStore
    source: Source
    doc: CleanedDocument
    chunks: tuple[Chunk, ...]


def _build(
    tmp_path: Path, source: Source, html: str = PAGE, config: ChunkingConfig | None = None
) -> Pipeline:
    raw, cleaned, curated = tmp_path / "raw", tmp_path / "cleaned", tmp_path / "curated"
    store = RawStore(raw)
    store.save(
        FetchResult(
            source_id=source.id,
            requested_url=str(source.url),
            final_url=str(source.url),
            status_code=200,
            content_type="text/html",
            body=html.encode(),
            retrieved_at=RETRIEVED,
            etag=None,
            last_modified=None,
        )
    )
    record = store.latest(source.id)
    assert record is not None
    doc = clean_record(store, record)
    write_cleaned(cleaned, doc)
    chunks = chunk_document(doc, config)
    write_chunks(curated, chunks, CLEANER_VERSION)
    return Pipeline(raw, cleaned, curated, store, source, doc, chunks)


def _run(p: Pipeline, register: Register, **kwargs: object) -> list[tuple[str, Severity]]:
    report = run_dq(
        register,
        raw_root=p.raw,
        cleaned_root=p.cleaned,
        curated_root=p.curated,
        now=NOW,
        **kwargs,  # type: ignore[arg-type]
    )
    return [(f.code, f.severity) for f in report.findings if f.source_id in (p.source.id, None)]


def _codes(findings: Sequence[Finding]) -> set[str]:
    return {f.code for f in findings}


# -- the happy path ---------------------------------------------------------------------------


def test_a_clean_pipeline_has_no_findings(
    tmp_path: Path, register: Register, source: Source
) -> None:
    pipeline = _build(tmp_path, source)
    report = run_dq(
        register, raw_root=pipeline.raw, cleaned_root=pipeline.cleaned,
        curated_root=pipeline.curated, now=NOW,
    )  # fmt: skip
    assert report.errors == []
    assert pipeline.source.id in report.chunks_checked
    # every other allowed source simply has not been fetched in this temp folder
    assert {f.code for f in report.warnings} == {"DQ-13"}
    assert report.ok()
    assert not report.ok(strict=True)


# -- DQ-01 to DQ-04: lineage -----------------------------------------------------------------


def test_dq01_chunk_naming_another_source(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source)
    bad = tuple(c.model_copy(update={"source_id": "A-OSFI-B10"}) for c in p.chunks)
    assert "DQ-01" in _codes(
        check_chunk_lineage(source, p.store.records(source.id), bad, NOW, DqConfig())
    )


def test_dq01_chunks_for_a_blocked_source(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source)
    blocked = source.model_copy(update={"ingest_allowed": False})
    found = check_chunk_lineage(blocked, p.store.records(source.id), p.chunks, NOW, DqConfig())
    assert "DQ-01" in _codes(found)


def test_dq02_chunk_without_a_stored_retrieval(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source)
    assert "DQ-02" in _codes(check_chunk_lineage(source, [], p.chunks, NOW, DqConfig()))
    moved = tuple(
        c.model_copy(update={"retrieved_at": RETRIEVED + timedelta(days=1)}) for c in p.chunks
    )
    assert "DQ-02" in _codes(
        check_chunk_lineage(source, p.store.records(source.id), moved, NOW, DqConfig())
    )


def test_dq02_tampered_raw_page_is_reported_by_the_run(
    tmp_path: Path, register: Register, source: Source
) -> None:
    p = _build(tmp_path, source)
    record = p.store.latest(source.id)
    assert record is not None
    blob = p.store.blob_path(record)
    blob.chmod(0o600)
    blob.write_bytes(b"edited by hand")
    assert ("DQ-02", Severity.ERROR) in _run(p, register)


@pytest.mark.parametrize("url", ["http://example.com/x", "https://elsewhere.example.org/x"])
def test_dq03_final_url_must_be_https_on_the_registered_host(
    tmp_path: Path, source: Source, url: str
) -> None:
    p = _build(tmp_path, source)
    bad = tuple(c.model_copy(update={"final_url": url}) for c in p.chunks)
    assert "DQ-03" in _codes(
        check_chunk_lineage(source, p.store.records(source.id), bad, NOW, DqConfig())
    )


def test_dq04_retrieval_time_rules(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source)
    records = p.store.records(source.id)

    def run(when: datetime, now: datetime = NOW) -> list[tuple[str, Severity]]:
        chunks = tuple(c.model_copy(update={"retrieved_at": when}) for c in p.chunks)
        records_for = [r.model_copy(update={"retrieved_at": when}) for r in records]
        found = check_chunk_lineage(source, records_for, chunks, now, DqConfig())
        return [(f.code, f.severity) for f in found]

    assert ("DQ-04", Severity.ERROR) in run(NOW + timedelta(days=1))  # future
    assert ("DQ-04", Severity.ERROR) in run(
        datetime(2026, 11, 19, 9, 0, tzinfo=timezone(timedelta(hours=5)))
    )
    assert ("DQ-04", Severity.WARNING) in run(
        RETRIEVED, now=RETRIEVED + timedelta(days=400)
    )  # stale
    assert run(RETRIEVED) == []


# -- DQ-05 to DQ-12: content ------------------------------------------------------------------


def _integrity(p: Pipeline, chunks: tuple[Chunk, ...]) -> list[tuple[str, Severity]]:
    found = check_chunk_integrity(p.source.id, p.doc, chunks, SMALL_DQ)
    return [(f.code, f.severity) for f in found]


def test_integrity_passes_on_untouched_chunks(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source, config=SMALL)
    assert len(p.chunks) > 10
    assert _integrity(p, p.chunks) == []


def test_dq05_altered_text_or_path(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source, config=SMALL)
    edited = (p.chunks[0].model_copy(update={"text": p.chunks[0].text + " x"}), *p.chunks[1:])
    assert ("DQ-05", Severity.ERROR) in _integrity(p, edited)
    repathed = (p.chunks[0].model_copy(update={"section_path": ("Other",)}), *p.chunks[1:])
    assert ("DQ-05", Severity.ERROR) in _integrity(p, repathed)


def test_dq06_duplicate_ids_oversize_and_numbering(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source, config=SMALL)
    dup = (*p.chunks, p.chunks[0])
    assert ("DQ-06", Severity.ERROR) in _integrity(p, dup)
    big = DqConfig(max_chars=50)
    assert "DQ-06" in _codes(check_chunk_integrity(source.id, p.doc, p.chunks, big))
    skewed = (p.chunks[0].model_copy(update={"chunk_count": 99}), *p.chunks[1:])
    assert ("DQ-06", Severity.ERROR) in _integrity(p, skewed)


def test_dq07_page_chrome_in_text_is_a_warning(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source, config=SMALL)
    first = p.chunks[0]
    polluted = (
        first.model_copy(update={"text": "Report a problem or mistake on this page"}),
        *p.chunks[1:],
    )
    assert ("DQ-07", Severity.WARNING) in _integrity(p, polluted)


def test_dq08_lost_text(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source, config=SMALL)
    middle = len(p.chunks) // 2
    missing = p.chunks[:middle] + p.chunks[middle + 1 :]
    assert ("DQ-08", Severity.ERROR) in _integrity(p, missing)


def test_dq09_page_coverage(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source)
    html = PAGE.encode()
    assert check_page_coverage(source.id, html, p.doc, DqConfig()) == []
    half = p.doc.model_copy(update={"sections": p.doc.sections[:1]})
    assert _codes(check_page_coverage(source.id, html, half, DqConfig())) == {"DQ-09"}
    assert _codes(check_page_coverage(source.id, b"<html></html>", p.doc, DqConfig())) == {"DQ-09"}


def test_dq10_identical_chunks_are_a_warning(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source, config=SMALL)
    twin = p.chunks[2].model_copy(update={"chunk_id": "x", "text": p.chunks[1].text})
    assert ("DQ-10", Severity.WARNING) in _integrity(p, (*p.chunks, twin))


@pytest.mark.parametrize(
    ("text", "severity"),
    [
        ("bad � char", Severity.ERROR),
        ("bad \x00 char", Severity.ERROR),
        ("cafÃ© text", Severity.WARNING),
    ],
)
def test_dq11_bad_characters(tmp_path: Path, source: Source, text: str, severity: Severity) -> None:
    p = _build(tmp_path, source, config=SMALL)
    bad = (p.chunks[0].model_copy(update={"text": text}), *p.chunks[1:])
    assert ("DQ-11", severity) in _integrity(p, bad)


def test_dq12_empty_and_tiny_sources(tmp_path: Path, source: Source) -> None:
    p = _build(tmp_path, source)
    assert _codes(check_chunk_integrity(source.id, p.doc, (), DqConfig())) == {"DQ-12"}
    tiny = _build(tmp_path / "tiny", source, "<main><h1>T</h1><p>Short.</p></main>")
    found = check_chunk_integrity(source.id, tiny.doc, tiny.chunks, DqConfig())
    assert [(f.code, f.severity) for f in found] == [("DQ-12", Severity.WARNING)]


# -- DQ-13 to DQ-15: the run and the repository ------------------------------------------------


def test_dq13_fetched_but_not_chunked(tmp_path: Path, register: Register, source: Source) -> None:
    p = _build(tmp_path, source)
    for file in p.curated.rglob("*.jsonl"):
        file.unlink()
    assert ("DQ-13", Severity.WARNING) in _run(p, register)


def test_dq14_data_for_sources_the_register_has_not_cleared(
    tmp_path: Path, register: Register, source: Source
) -> None:
    p = _build(tmp_path, source)
    pending = register.pending[0].id
    (p.curated / pending).mkdir()
    (p.raw / "A-NOPE-NOTHING").mkdir()
    found = check_governance_leaks(register, p.raw, p.cleaned, p.curated)
    assert {(f.code, f.source_id) for f in found} == {
        ("DQ-14", pending),
        ("DQ-14", "A-NOPE-NOTHING"),
    }


def test_dq15_gitignore_must_list_every_corpus_folder(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("data/raw/\ndata/cleaned/\n", encoding="utf-8")
    messages = [f.message for f in check_repo_hygiene(tmp_path)]
    assert any("data/curated/" in m for m in messages)
    assert any("data/embeddings/" in m for m in messages)
    assert not any("data/raw/" in m for m in messages)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_dq15_tracked_corpus_files_are_errors(tmp_path: Path) -> None:
    ignore = "data/raw/\ndata/cleaned/\ndata/curated/\ndata/embeddings/\n"
    (tmp_path / ".gitignore").write_text(ignore, encoding="utf-8")
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(tmp_path), "init", "-q"], check=True)  # noqa: S603
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "sources").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "leak.txt").write_text("corpus", encoding="utf-8")
    (tmp_path / "data" / "sources" / "register.yaml").write_text("ok", encoding="utf-8")
    args = [git, "-C", str(tmp_path), "add", "-f", "data"]
    subprocess.run(args, check=True)  # noqa: S603
    messages = [f.message for f in check_repo_hygiene(tmp_path)]
    assert messages == ["data/raw/leak.txt is tracked by git"]


# -- command line ----------------------------------------------------------------------------


def _cli(p: Pipeline, *extra: str) -> int:
    args = ["--register", str(REGISTER_PATH), "dq", "--repo-root", str(ROOT)]
    args += [
        "--raw-dir",
        str(p.raw),
        "--cleaned-dir",
        str(p.cleaned),
        "--chunk-dir",
        str(p.curated),
    ]
    return main([*args, *extra])


def test_cli_dq_passes_with_only_warnings(
    tmp_path: Path, source: Source, capsys: pytest.CaptureFixture[str]
) -> None:
    p = _build(tmp_path, source)
    assert _cli(p) == EXIT_OK
    out = capsys.readouterr().out
    assert f"CHECKED  {source.id}" in out
    assert "0 error(s)" in out


def test_cli_dq_strict_fails_on_warnings(tmp_path: Path, source: Source) -> None:
    assert _cli(_build(tmp_path, source), "--strict") == EXIT_DQ_FAILED


def test_cli_dq_fails_on_errors(tmp_path: Path, register: Register, source: Source) -> None:
    p = _build(tmp_path, source)
    (p.curated / register.pending[0].id).mkdir()
    assert _cli(p) == EXIT_DQ_FAILED


# -- real corpus (local only) ------------------------------------------------------------------


def test_the_local_corpus_passes_every_error_check() -> None:
    """Runs only where data has been ingested; CI has none and skips this."""
    if not (ROOT / "data" / "raw").exists():
        pytest.skip("no local raw data")
    report = run_dq(
        load_register(REGISTER_PATH),
        raw_root=ROOT / "data" / "raw",
        cleaned_root=ROOT / "data" / "cleaned",
        curated_root=ROOT / "data" / "curated",
        repo_root=ROOT,
    )
    assert [f.line() for f in report.errors] == []
