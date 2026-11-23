"""Helpers shared by the database tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from bfs_reg_copilot.ingest.chunking import Chunk
from bfs_reg_copilot.store.db import EMBEDDING_DIMS

ADMIN_URL = os.environ.get("BFS_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not ADMIN_URL, reason="set BFS_TEST_DATABASE_URL to run")

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

INSERT_ONE = (
    "INSERT INTO chunk_embeddings (chunk_id, model, embedding) VALUES (%s, 'm', %s::vector)"
)


def with_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


def vec(first: float, size: int = EMBEDDING_DIMS) -> str:
    return "[" + ",".join([str(first)] + ["0"] * (size - 1)) + "]"


def make_chunk(
    source: str = "S-TEST",
    sha: str = "a" * 64,
    n: int = 1,
    text: str = "Banks must assess model risk.",
    retrieved_at: datetime = T0,
) -> Chunk:
    return Chunk(
        chunk_id=f"{source}:{sha[:12]}:s001:c{n:03d}",
        source_id=source,
        raw_sha256=sha,
        retrieved_at=retrieved_at,
        final_url="https://example.test/page",
        page_title="Test page",
        date_modified=None,
        section_index=1,
        section_heading="Scope",
        section_path=("Test page", "Scope"),
        anchor=None,
        chunk_index=n - 1,
        chunk_count=2,
        section_start=0,
        section_end=len(text),
        text=text,
    )
