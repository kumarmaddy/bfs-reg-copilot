"""Raw storage: keep exactly what was fetched, with a content hash and retrieval time.

Layout under the raw root (git-ignored, ADR-0007)::

    <root>/<source_id>/blobs/<sha256>.bin   the bytes as received, named by their hash
    <root>/<source_id>/manifest.jsonl       one line per retrieval, append-only

Identical content fetched twice shares one blob but gets two manifest lines, so we can say both
"this is what the page said" and "we checked on these dates and it had not changed".
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict

from bfs_reg_copilot.ingest.fetcher import FetchResult

_SOURCE_ID = re.compile(r"^[A-D](-[A-Z0-9]+)+$")


class RawStoreError(Exception):
    """The store is damaged or was asked to do something unsafe."""


class RawRecord(BaseModel):
    """One retrieval event. This is the lineage anchor that later stages point back to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    retrieved_at: AwareDatetime
    sha256: str
    size_bytes: int
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class SaveResult:
    record: RawRecord
    is_new_content: bool
    repaired: bool = False  # a stored copy existed but did not match its hash, so it was replaced


class RawStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _dir(self, source_id: str) -> Path:
        # The id becomes a folder name, so it must be a well-formed register id and nothing else.
        if not _SOURCE_ID.fullmatch(source_id):
            raise RawStoreError(f"not a valid source id: {source_id!r}")
        return self._root / source_id

    def blob_path(self, record: RawRecord) -> Path:
        return self._dir(record.source_id) / "blobs" / f"{record.sha256}.bin"

    def save(self, result: FetchResult) -> SaveResult:
        folder = self._dir(result.source_id)
        digest = hashlib.sha256(result.body).hexdigest()
        record = RawRecord(
            source_id=result.source_id,
            requested_url=result.requested_url,
            final_url=result.final_url,
            status_code=result.status_code,
            content_type=result.content_type,
            retrieved_at=result.retrieved_at,
            sha256=digest,
            size_bytes=len(result.body),
            etag=result.etag,
            last_modified=result.last_modified,
        )
        blob = self.blob_path(record)
        existed = blob.exists()
        # A copy that exists but fails its own hash is replaced, never trusted as "unchanged".
        repaired = existed and hashlib.sha256(blob.read_bytes()).hexdigest() != digest
        is_new = not existed
        if is_new or repaired:
            blob.parent.mkdir(parents=True, exist_ok=True)
            self._write_atomically(blob, result.body)
        # The manifest line is written only after the blob is safely on disk.
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(record.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return SaveResult(record=record, is_new_content=is_new, repaired=repaired)

    def records(self, source_id: str) -> list[RawRecord]:
        manifest = self._dir(source_id) / "manifest.jsonl"
        if not manifest.exists():
            return []
        lines = manifest.read_text(encoding="utf-8").splitlines()
        return [RawRecord.model_validate_json(line) for line in lines if line.strip()]

    def latest(self, source_id: str) -> RawRecord | None:
        found = self.records(source_id)
        return found[-1] if found else None

    def read_body(self, record: RawRecord) -> bytes:
        """Return the stored bytes, refusing to hand back anything that fails its hash."""
        path = self.blob_path(record)
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise RawStoreError(f"blob missing for {record.source_id}: {path}") from exc
        if hashlib.sha256(body).hexdigest() != record.sha256:
            raise RawStoreError(f"blob does not match its recorded hash: {path}")
        return body

    @staticmethod
    def _write_atomically(target: Path, body: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                target.chmod(
                    stat.S_IWRITE | stat.S_IREAD
                )  # Windows cannot replace a read-only file
            os.replace(tmp_name, target)
            # Stored pages are evidence. Read-only keeps an editor from quietly changing them.
            target.chmod(stat.S_IREAD)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
