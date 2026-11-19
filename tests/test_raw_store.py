"""Tests for raw storage. Everything happens in pytest's temp folders."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bfs_reg_copilot.ingest import FetchResult, RawStore, RawStoreError

SOURCE_ID = "A-OSFI-E23"
ROOT = Path(__file__).resolve().parents[1]


def _result(body: bytes = b"<html>v1</html>", when: datetime | None = None) -> FetchResult:
    return FetchResult(
        source_id=SOURCE_ID,
        requested_url="https://example.gc.ca/a",
        final_url="https://example.gc.ca/a",
        status_code=200,
        content_type="text/html",
        body=body,
        retrieved_at=when or datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        etag=None,
        last_modified=None,
    )


def test_save_records_hash_size_and_time(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    saved = store.save(_result())
    assert saved.is_new_content
    assert saved.record.sha256 == hashlib.sha256(b"<html>v1</html>").hexdigest()
    assert saved.record.size_bytes == len(b"<html>v1</html>")
    assert saved.record.retrieved_at == datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    assert store.read_body(saved.record) == b"<html>v1</html>"


def test_same_content_twice_shares_one_blob_but_two_records(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    first = store.save(_result())
    second = store.save(_result(when=datetime(2026, 12, 1, tzinfo=UTC)))
    assert first.is_new_content
    assert not second.is_new_content
    assert len(list((tmp_path / SOURCE_ID / "blobs").glob("*.bin"))) == 1
    assert len(store.records(SOURCE_ID)) == 2


def test_changed_content_is_kept_alongside_the_old(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    old = store.save(_result(b"v1")).record
    new = store.save(_result(b"v2", datetime(2026, 12, 1, tzinfo=UTC))).record
    assert old.sha256 != new.sha256
    assert store.read_body(old) == b"v1"
    assert store.read_body(new) == b"v2"
    assert store.latest(SOURCE_ID) == new


def test_unknown_source_has_no_records(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    assert store.records(SOURCE_ID) == []
    assert store.latest(SOURCE_ID) is None


def test_manifest_is_one_json_object_per_line(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.save(_result())
    store.save(_result(when=datetime(2026, 12, 1, tzinfo=UTC) + timedelta(seconds=1)))
    lines = (tmp_path / SOURCE_ID / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["source_id"] == SOURCE_ID for line in lines)


def test_tampered_blob_is_detected(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    record = store.save(_result()).record
    store.blob_path(record).write_bytes(b"something else")
    with pytest.raises(RawStoreError, match="hash"):
        store.read_body(record)


def test_missing_blob_is_detected(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    record = store.save(_result()).record
    store.blob_path(record).unlink()
    with pytest.raises(RawStoreError, match="missing"):
        store.read_body(record)


@pytest.mark.parametrize("bad_id", ["../evil", "A-OSFI/../x", "a-lower", "", "A", "A-OSFI E23"])
def test_source_id_cannot_escape_the_store(tmp_path: Path, bad_id: str) -> None:
    bad = FetchResult(**{**_result().__dict__, "source_id": bad_id})
    with pytest.raises(RawStoreError, match="valid source id"):
        RawStore(tmp_path).save(bad)
    assert list(tmp_path.iterdir()) == []


def test_no_temp_files_are_left_behind(tmp_path: Path) -> None:
    RawStore(tmp_path).save(_result())
    assert list(tmp_path.rglob("*.tmp")) == []


def test_raw_folder_is_git_ignored() -> None:
    """ADR-0007: corpus text must never be committable."""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/raw/" in lines
