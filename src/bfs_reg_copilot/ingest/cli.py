"""Command line for ingestion. Only `fetch` uses the network; the rest work on local files."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import yaml

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
from bfs_reg_copilot.ingest.store import RawStore, RawStoreError
from bfs_reg_copilot.registry import Register, load_register

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2
EXIT_REFUSED = 3
EXIT_FETCH_FAILED = 4

DEFAULT_PATH = Path("data/sources/register.yaml")
DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_CLEANED_DIR = Path("data/cleaned")
DEFAULT_CHUNK_DIR = Path("data/curated")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bfs_reg_copilot.ingest",
        description="Ask the source register what may be ingested.",
    )
    parser.add_argument("--register", type=Path, default=DEFAULT_PATH, help="path to register.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show every source and whether it may be ingested")
    check = sub.add_parser("check", help="exit 0 if the source may be ingested, 3 if refused")
    check.add_argument("source_id")
    fetch = sub.add_parser("fetch", help="fetch one allowed source and store the raw bytes")
    fetch.add_argument("source_id")
    fetch.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="raw store root")
    clean = sub.add_parser("clean", help="clean the latest stored fetch of one source")
    clean.add_argument("source_id")
    clean.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="raw store root")
    clean.add_argument("--out-dir", type=Path, default=DEFAULT_CLEANED_DIR, help="cleaned root")
    chunk = sub.add_parser("chunk", help="chunk the latest cleaned page of one source")
    chunk.add_argument("source_id")
    chunk.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="raw store root")
    chunk.add_argument("--cleaned-dir", type=Path, default=DEFAULT_CLEANED_DIR, help="cleaned root")
    chunk.add_argument("--out-dir", type=Path, default=DEFAULT_CHUNK_DIR, help="chunk root")
    return parser


def _status_lines(register: Register) -> list[str]:
    lines = [f"ALLOWED  {s.id}  {s.title}" for s in register.sources if s.ingest_allowed]
    lines += [
        f"BLOCKED  {s.id}  {s.blocking_reason.strip()}"
        for s in register.sources
        if not s.ingest_allowed
    ]
    lines += [f"PENDING  {p.id}  {p.title}" for p in register.pending]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    path: Path = args.register
    try:
        register = load_register(path)
    except OSError as exc:
        print(f"UNREADABLE: {path}\n{exc}")
        return EXIT_UNREADABLE
    except (ValueError, yaml.YAMLError) as exc:  # pydantic's ValidationError is a ValueError
        print(f"INVALID: {path}\n{exc}")
        return EXIT_INVALID

    if args.command == "list":
        print("\n".join(_status_lines(register)))
        return EXIT_OK

    if args.command == "chunk":
        return _chunk(register, args.source_id, args.raw_dir, args.cleaned_dir, args.out_dir)

    if args.command == "clean":
        return _clean(register, args.source_id, args.raw_dir, args.out_dir)

    if args.command == "fetch":
        return _fetch(register, args.source_id, args.raw_dir)

    try:
        source = require_ingestible(register, args.source_id)
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    print(f"ALLOWED: {source.id}  {source.url}")
    return EXIT_OK


def _fetch(register: Register, source_id: str, raw_dir: Path) -> int:
    try:
        with PoliteFetcher(register) as fetcher:
            result = fetcher.fetch(source_id)
        saved = RawStore(raw_dir).save(result)
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    except (FetchError, RawStoreError) as exc:
        print(f"FAILED: {exc}")
        return EXIT_FETCH_FAILED
    record = saved.record
    if saved.repaired:
        state = "REPAIRED a damaged stored copy"
    else:
        state = "new content" if saved.is_new_content else "unchanged since an earlier fetch"
    print(
        f"STORED: {record.source_id}  sha256={record.sha256[:12]}  {record.size_bytes} bytes  "
        f"{state}  retrieved {record.retrieved_at.isoformat()}"
    )
    return EXIT_OK


def _clean(register: Register, source_id: str, raw_dir: Path, out_dir: Path) -> int:
    try:
        require_ingestible(register, source_id)
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    try:
        store = RawStore(raw_dir)
        record = store.latest(source_id)
        if record is None:
            print(f"FAILED: nothing stored for {source_id}; run fetch first")
            return EXIT_FETCH_FAILED
        doc = clean_record(store, record)
        path = write_cleaned(out_dir, doc)
    except (RawStoreError, CleaningError) as exc:
        print(f"FAILED: {exc}")
        return EXIT_FETCH_FAILED
    chars = sum(len(s.text) for s in doc.sections)
    print(f"CLEANED: {source_id}  {len(doc.sections)} sections  {chars} chars  -> {path}")
    return EXIT_OK


def _chunk(
    register: Register, source_id: str, raw_dir: Path, cleaned_dir: Path, out_dir: Path
) -> int:
    try:
        require_ingestible(register, source_id)
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    record = RawStore(raw_dir).latest(source_id)
    if record is None:
        print(f"FAILED: nothing stored for {source_id}; run fetch first")
        return EXIT_FETCH_FAILED
    source_file = cleaned_file(cleaned_dir, source_id, record.sha256)
    if not source_file.exists():
        print(f"FAILED: no cleaned page for the latest fetch of {source_id}; run clean first")
        return EXIT_FETCH_FAILED
    doc = read_cleaned(source_file)
    chunks = chunk_document(doc)
    path = write_chunks(out_dir, chunks, doc.cleaner_version)
    longest = max(len(c.text) for c in chunks)
    print(f"CHUNKED: {source_id}  {len(chunks)} chunks  longest {longest} chars  -> {path}")
    return EXIT_OK
