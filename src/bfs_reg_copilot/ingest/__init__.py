"""Ingestion: fetching, storing, cleaning and chunking sources that the register allows."""

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
    "USER_AGENT",
    "FetchError",
    "FetchRefused",
    "FetchResult",
    "PoliteFetcher",
    "RawRecord",
    "RawStore",
    "RawStoreError",
    "SaveResult",
    "require_ingestible",
]
