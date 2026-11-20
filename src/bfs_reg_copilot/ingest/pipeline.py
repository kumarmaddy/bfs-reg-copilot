"""The pipeline stages as plain functions, shared by the command line and the Airflow DAG.

Keeping the logic here means the DAG file stays a thin wrapper: it decides *when* and *in what
order* stages run, never *what* they do. Everything here runs and is tested without Airflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bfs_reg_copilot.ingest.chunk_store import write_chunks
from bfs_reg_copilot.ingest.chunking import chunk_document
from bfs_reg_copilot.ingest.clean import CleaningError
from bfs_reg_copilot.ingest.cleaned_store import (
    clean_record,
    cleaned_file,
    read_cleaned,
    write_cleaned,
)
from bfs_reg_copilot.ingest.fetcher import (
    FetchError,
    FetchRefused,
    PoliteFetcher,
    require_ingestible,
)
from bfs_reg_copilot.ingest.store import RawStore, RawStoreError, SaveResult
from bfs_reg_copilot.registry import Register


class PipelineError(Exception):
    """A stage cannot run because an earlier stage has not produced its input."""


@dataclass(frozen=True)
class DataDirs:
    raw: Path
    cleaned: Path
    curated: Path

    @classmethod
    def under(cls, root: Path) -> DataDirs:
        return cls(raw=root / "raw", cleaned=root / "cleaned", curated=root / "curated")


@dataclass(frozen=True)
class FetchOutcome:
    """The result of fetching one source. Failures are recorded, not raised, so one bad source
    does not stop the others from being fetched."""

    source_id: str
    saved: SaveResult | None = None
    error: str | None = None
    refused: bool = False

    @property
    def ok(self) -> bool:
        return self.saved is not None


@dataclass(frozen=True)
class CleanSummary:
    path: Path
    sections: int
    chars: int


@dataclass(frozen=True)
class ChunkSummary:
    path: Path
    chunks: int
    longest: int


def fetch_sources(
    register: Register,
    source_ids: Sequence[str],
    raw_dir: Path,
    *,
    fetcher: PoliteFetcher | None = None,
) -> list[FetchOutcome]:
    """Fetch and store each source, one after another, through one fetcher.

    One fetcher for the whole batch matters: it keeps the 2 second gap between requests to the
    same host. Separate fetchers (for example one per Airflow task) would each start their own
    clock and could hit a host back to back.
    """
    store = RawStore(raw_dir)
    own = fetcher is None
    active = fetcher or PoliteFetcher(register)
    outcomes: list[FetchOutcome] = []
    try:
        for source_id in source_ids:
            try:
                outcomes.append(FetchOutcome(source_id, saved=store.save(active.fetch(source_id))))
            except FetchRefused as exc:
                outcomes.append(FetchOutcome(source_id, error=str(exc), refused=True))
            except (FetchError, RawStoreError) as exc:
                outcomes.append(FetchOutcome(source_id, error=str(exc)))
    finally:
        if own:
            active.close()
    return outcomes


def clean_source(register: Register, source_id: str, dirs: DataDirs) -> CleanSummary:
    """Clean the latest stored page of one source. Raises FetchRefused, PipelineError,
    RawStoreError or CleaningError."""
    require_ingestible(register, source_id)
    store = RawStore(dirs.raw)
    record = store.latest(source_id)
    if record is None:
        raise PipelineError(f"nothing stored for {source_id}; run fetch first")
    doc = clean_record(store, record)
    path = write_cleaned(dirs.cleaned, doc)
    return CleanSummary(path, len(doc.sections), sum(len(s.text) for s in doc.sections))


def chunk_source(register: Register, source_id: str, dirs: DataDirs) -> ChunkSummary:
    """Chunk the cleaned page that belongs to the latest fetch of one source."""
    require_ingestible(register, source_id)
    record = RawStore(dirs.raw).latest(source_id)
    if record is None:
        raise PipelineError(f"nothing stored for {source_id}; run fetch first")
    cleaned = cleaned_file(dirs.cleaned, source_id, record.sha256)
    if not cleaned.exists():
        raise PipelineError(f"no cleaned page for the latest fetch of {source_id}; run clean first")
    doc = read_cleaned(cleaned)
    chunks = chunk_document(doc)
    path = write_chunks(dirs.curated, chunks, doc.cleaner_version)
    return ChunkSummary(path, len(chunks), max(len(c.text) for c in chunks))


__all__ = [
    "ChunkSummary",
    "CleanSummary",
    "CleaningError",
    "DataDirs",
    "FetchOutcome",
    "PipelineError",
    "chunk_source",
    "clean_source",
    "fetch_sources",
]
