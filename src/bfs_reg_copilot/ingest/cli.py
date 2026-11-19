"""Command line for the ingestion gate. Slice 1.1 offers `list` and `check`; no network calls."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import yaml

from bfs_reg_copilot.ingest.fetcher import FetchRefused, require_ingestible
from bfs_reg_copilot.registry import Register, load_register

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2
EXIT_REFUSED = 3

DEFAULT_PATH = Path("data/sources/register.yaml")


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

    try:
        source = require_ingestible(register, args.source_id)
    except FetchRefused as exc:
        print(f"REFUSED: {exc}")
        return EXIT_REFUSED
    print(f"ALLOWED: {source.id}  {source.url}")
    return EXIT_OK
