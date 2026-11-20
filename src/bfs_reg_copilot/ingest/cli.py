"""Command line for ingestion. Only `fetch` uses the network; the rest work on local files."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import yaml

from bfs_reg_copilot.ingest.clean import CleaningError
from bfs_reg_copilot.ingest.dq import run_dq
from bfs_reg_copilot.ingest.fetcher import FetchRefused, require_ingestible
from bfs_reg_copilot.ingest.pipeline import (
    DataDirs,
    PipelineError,
    chunk_source,
    clean_source,
    fetch_sources,
)
from bfs_reg_copilot.ingest.store import RawStoreError
from bfs_reg_copilot.registry import Register, load_register

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2
EXIT_REFUSED = 3
EXIT_FETCH_FAILED = 4
EXIT_DQ_FAILED = 5

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
    dq = sub.add_parser("dq", help="run the data-quality checks; exit 5 if any ERROR")
    dq.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    dq.add_argument("--repo-root", type=Path, default=Path("."), help="repo root (git checks)")
    dq.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="raw store root")
    dq.add_argument("--cleaned-dir", type=Path, default=DEFAULT_CLEANED_DIR, help="cleaned root")
    dq.add_argument("--chunk-dir", type=Path, default=DEFAULT_CHUNK_DIR, help="chunk root")
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

    if args.command == "dq":
        return _dq(register, args)

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
    outcome = fetch_sources(register, [source_id], raw_dir)[0]
    if outcome.saved is None:
        print(f"{'REFUSED' if outcome.refused else 'FAILED'}: {outcome.error}")
        return EXIT_REFUSED if outcome.refused else EXIT_FETCH_FAILED
    saved = outcome.saved
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
    dirs = DataDirs(raw_dir, out_dir, out_dir)
    try:
        summary = clean_source(register, source_id, dirs)
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    except (PipelineError, RawStoreError, CleaningError) as exc:
        print(f"FAILED: {exc}")
        return EXIT_FETCH_FAILED
    print(
        f"CLEANED: {source_id}  {summary.sections} sections  {summary.chars} chars  "
        f"-> {summary.path}"
    )
    return EXIT_OK


def _chunk(
    register: Register, source_id: str, raw_dir: Path, cleaned_dir: Path, out_dir: Path
) -> int:
    try:
        summary = chunk_source(register, source_id, DataDirs(raw_dir, cleaned_dir, out_dir))
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    except (PipelineError, RawStoreError) as exc:
        print(f"FAILED: {exc}")
        return EXIT_FETCH_FAILED
    print(
        f"CHUNKED: {source_id}  {summary.chunks} chunks  longest {summary.longest} chars  "
        f"-> {summary.path}"
    )
    return EXIT_OK


def _dq(register: Register, args: argparse.Namespace) -> int:
    report = run_dq(
        register,
        raw_root=args.raw_dir,
        cleaned_root=args.cleaned_dir,
        curated_root=args.chunk_dir,
        repo_root=args.repo_root,
    )
    for source_id, count in report.chunks_checked.items():
        print(f"CHECKED  {source_id}  {count} chunks")
    for finding in report.findings:
        print(finding.line())
    print(f"DQ: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return EXIT_OK if report.ok(strict=args.strict) else EXIT_DQ_FAILED
