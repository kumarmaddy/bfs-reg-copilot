"""Ingestion: fetching, storing, cleaning and chunking sources that the register allows."""

from bfs_reg_copilot.ingest.fetcher import (
    USER_AGENT,
    FetchError,
    FetchRefused,
    FetchResult,
    PoliteFetcher,
    require_ingestible,
)

__all__ = [
    "USER_AGENT",
    "FetchError",
    "FetchRefused",
    "FetchResult",
    "PoliteFetcher",
    "require_ingestible",
]
