"""Link cleaned text back to the raw retrieval it came from, and store it (git-ignored).

<root>/<source_id>/<raw_sha256>.v<cleaner_version>.json
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict

from bfs_reg_copilot.ingest.clean import CLEANER_VERSION, Section, clean_html
from bfs_reg_copilot.ingest.store import RawRecord, RawStore


class CleanedDocument(BaseModel):
    """Cleaned text plus the lineage needed to trace any later chunk to the register."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    raw_sha256: str
    retrieved_at: AwareDatetime
    final_url: str
    cleaner_version: str
    page_title: str
    date_modified: str | None
    sections: tuple[Section, ...]


def clean_record(store: RawStore, record: RawRecord) -> CleanedDocument:
    """Read a stored page (hash-checked) and clean it."""
    page = clean_html(store.read_body(record))
    return CleanedDocument(
        source_id=record.source_id,
        raw_sha256=record.sha256,
        retrieved_at=record.retrieved_at,
        final_url=record.final_url,
        cleaner_version=CLEANER_VERSION,
        page_title=page.page_title,
        date_modified=page.date_modified,
        sections=page.sections,
    )


def cleaned_path(root: Path, doc: CleanedDocument) -> Path:
    return root / doc.source_id / f"{doc.raw_sha256}.v{doc.cleaner_version}.json"


def write_cleaned(root: Path, doc: CleanedDocument) -> Path:
    target = cleaned_path(root, doc)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(doc.model_dump_json(indent=2))
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def read_cleaned(path: Path) -> CleanedDocument:
    return CleanedDocument.model_validate_json(path.read_text(encoding="utf-8"))
