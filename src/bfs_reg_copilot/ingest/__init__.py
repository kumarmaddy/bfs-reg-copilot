"""Ingestion: fetching, storing, cleaning and chunking sources that the register allows."""

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
    "CLEANER_VERSION",
    "USER_AGENT",
    "CleanedDocument",
    "CleanedPage",
    "CleaningError",
    "FetchError",
    "FetchRefused",
    "FetchResult",
    "PoliteFetcher",
    "RawRecord",
    "RawStore",
    "RawStoreError",
    "SaveResult",
    "Section",
    "clean_html",
    "clean_record",
    "read_cleaned",
    "require_ingestible",
    "write_cleaned",
]
