"""Tests for the shared pipeline stages (what the DAG calls). No network, no Airflow."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from bfs_reg_copilot.ingest import FetchRefused, PoliteFetcher, RawStore, RawStoreError
from bfs_reg_copilot.ingest.pipeline import (
    DataDirs,
    PipelineError,
    chunk_source,
    clean_source,
    fetch_sources,
)
from bfs_reg_copilot.registry import Register, Source, load_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "data" / "sources" / "register.yaml"
PAGE = (
    b"<html><head><title>T</title></head><body><main><h1>Title</h1>"
    + b"".join(b"<p>Paragraph %d has a few plain words in it.</p>" % i for i in range(100))
    + b"</main></body></html>"
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(scope="module")
def register() -> Register:
    return load_register(REGISTER_PATH)


def _same_host_pair(register: Register) -> tuple[Source, Source]:
    by_host: dict[str | None, list[Source]] = defaultdict(list)
    for source in register.ingestible():
        by_host[urlsplit(str(source.url)).hostname].append(source)
    group = next(g for g in by_host.values() if len(g) >= 2)
    return group[0], group[1]


def _fetcher(
    register: Register, *, fail_paths: frozenset[str] = frozenset()
) -> tuple[PoliteFetcher, FakeClock, list[str]]:
    clock = FakeClock()
    requested: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path in fail_paths:
            return httpx.Response(503)
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    fetcher = PoliteFetcher(register, client=client, sleep=clock.sleep, monotonic=clock.monotonic)
    return fetcher, clock, requested


def test_data_dirs_under_a_root(tmp_path: Path) -> None:
    dirs = DataDirs.under(tmp_path)
    assert (dirs.raw, dirs.cleaned, dirs.curated) == (
        tmp_path / "raw",
        tmp_path / "cleaned",
        tmp_path / "curated",
    )


# -- fetch_sources ----------------------------------------------------------------------------


def test_one_fetcher_spaces_requests_across_sources_on_the_same_host(
    tmp_path: Path, register: Register
) -> None:
    first, second = _same_host_pair(register)
    fetcher, clock, _ = _fetcher(register)
    outcomes = fetch_sources(register, [first.id, second.id], tmp_path / "raw", fetcher=fetcher)
    assert [o.ok for o in outcomes] == [True, True]
    # robots.txt, page 1, then page 2 only after the polite gap
    assert clock.sleeps == pytest.approx([2.0, 2.0])


def test_a_failing_source_does_not_stop_the_rest(tmp_path: Path, register: Register) -> None:
    first, second = _same_host_pair(register)
    bad_path = urlsplit(str(first.url)).path
    fetcher, _, _ = _fetcher(register, fail_paths=frozenset({bad_path}))
    outcomes = fetch_sources(register, [first.id, second.id], tmp_path / "raw", fetcher=fetcher)
    assert [o.ok for o in outcomes] == [False, True]
    assert outcomes[0].error is not None
    assert "503" in outcomes[0].error
    assert not outcomes[0].refused
    store = RawStore(tmp_path / "raw")
    assert store.latest(first.id) is None
    assert store.latest(second.id) is not None


def test_a_refused_source_is_recorded_as_refused_with_no_request(
    tmp_path: Path, register: Register
) -> None:
    fetcher, _, requested = _fetcher(register)
    pending = register.pending[0].id
    (outcome,) = fetch_sources(register, [pending], tmp_path / "raw", fetcher=fetcher)
    assert outcome.refused
    assert not outcome.ok
    assert requested == []
    assert not (tmp_path / "raw").exists()


def test_the_default_fetcher_is_created_and_closed_by_the_function(
    tmp_path: Path, register: Register
) -> None:
    # Only refusals are used here, so no network call can happen.
    pending = register.pending[0].id
    assert fetch_sources(register, [pending], tmp_path / "raw")[0].refused


# -- clean_source and chunk_source ------------------------------------------------------------


def _fetched(tmp_path: Path, register: Register) -> tuple[Source, DataDirs]:
    source = register.ingestible()[0]
    dirs = DataDirs.under(tmp_path)
    fetcher, _, _ = _fetcher(register)
    (outcome,) = fetch_sources(register, [source.id], dirs.raw, fetcher=fetcher)
    assert outcome.ok
    return source, dirs


def test_clean_then_chunk_produce_files(tmp_path: Path, register: Register) -> None:
    source, dirs = _fetched(tmp_path, register)
    cleaned = clean_source(register, source.id, dirs)
    assert cleaned.path.exists()
    assert cleaned.sections == 1
    chunks = chunk_source(register, source.id, dirs)
    assert chunks.path.exists()
    assert chunks.chunks >= 2
    assert chunks.longest <= 1800


def test_stages_are_repeatable(tmp_path: Path, register: Register) -> None:
    source, dirs = _fetched(tmp_path, register)
    first = clean_source(register, source.id, dirs)
    assert clean_source(register, source.id, dirs) == first
    chunk_source(register, source.id, dirs)
    assert chunk_source(register, source.id, dirs).chunks >= 2


def test_clean_needs_a_fetch_first(tmp_path: Path, register: Register) -> None:
    with pytest.raises(PipelineError, match="run fetch first"):
        clean_source(register, register.ingestible()[0].id, DataDirs.under(tmp_path))


def test_chunk_needs_a_fetch_and_then_a_clean(tmp_path: Path, register: Register) -> None:
    source = register.ingestible()[0]
    dirs = DataDirs.under(tmp_path)
    with pytest.raises(PipelineError, match="run fetch first"):
        chunk_source(register, source.id, dirs)
    fetcher, _, _ = _fetcher(register)
    fetch_sources(register, [source.id], dirs.raw, fetcher=fetcher)
    with pytest.raises(PipelineError, match="run clean first"):
        chunk_source(register, source.id, dirs)


def test_stages_refuse_sources_the_register_has_not_cleared(
    tmp_path: Path, register: Register
) -> None:
    pending = register.pending[0].id
    dirs = DataDirs.under(tmp_path)
    with pytest.raises(FetchRefused):
        clean_source(register, pending, dirs)
    with pytest.raises(FetchRefused):
        chunk_source(register, pending, dirs)


def test_clean_refuses_a_tampered_stored_page(tmp_path: Path, register: Register) -> None:
    source, dirs = _fetched(tmp_path, register)
    store = RawStore(dirs.raw)
    record = store.latest(source.id)
    assert record is not None
    blob = store.blob_path(record)
    blob.chmod(0o600)
    blob.write_bytes(b"edited by hand")
    with pytest.raises(RawStoreError, match="hash"):
        clean_source(register, source.id, dirs)
