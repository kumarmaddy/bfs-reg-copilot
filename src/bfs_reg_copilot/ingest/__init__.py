"""Ingestion: fetching, storing, cleaning and chunking sources that the register allows."""

from bfs_reg_copilot.ingest.chunk_store import read_chunks, write_chunks
from bfs_reg_copilot.ingest.chunking import (
    CHUNKER_VERSION,
    Chunk,
    ChunkingConfig,
    chunk_document,
)
from bfs_reg_copilot.ingest.clean import (
    CLEANER_VERSION,
    CleanedPage,
    CleaningError,
    Section,
    clean_html,
)
from bfs_reg_copilot.ingest.cleaned_store import (
    CleanedDocument,
    clean_record,
    read_cleaned,
    write_cleaned,
)
from bfs_reg_copilot.ingest.dq import DqConfig, DqReport, Finding, Severity, run_dq
from bfs_reg_copilot.ingest.fetcher import (
    USER_AGENT,
    FetchError,
    FetchRefused,
    FetchResult,
    PoliteFetcher,
    require_ingestible,
)
from bfs_reg_copilot.ingest.store import RawRecord, RawStore, RawStoreError, SaveResult

__all__ = [
    "CHUNKER_VERSION",
    "CLEANER_VERSION",
    "USER_AGENT",
    "Chunk",
    "ChunkingConfig",
    "CleanedDocument",
    "CleanedPage",
    "CleaningError",
    "DqConfig",
    "DqReport",
    "FetchError",
    "FetchRefused",
    "FetchResult",
    "Finding",
    "PoliteFetcher",
    "RawRecord",
    "RawStore",
    "RawStoreError",
    "SaveResult",
    "Section",
    "Severity",
    "chunk_document",
    "clean_html",
    "clean_record",
    "read_chunks",
    "read_cleaned",
    "require_ingestible",
    "run_dq",
    "write_chunks",
    "write_cleaned",
]
