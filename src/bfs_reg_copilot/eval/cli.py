"""Command line for the gold set. Works on local files only; no network."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from bfs_reg_copilot.eval.gold import (
    GoldError,
    check_against_chunks,
    check_composition,
    load_gold,
    summarise,
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2
EXIT_CHUNK_MISMATCH = 3

DEFAULT_GOLD = Path("eval/gold/gold-v1.yaml")
DEFAULT_CHUNK_DIR = Path("data/curated")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bfs_reg_copilot.eval", description="Check the gold set."
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD, help="path to the gold YAML")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary", help="print counts by kind, split and source")
    validate = sub.add_parser(
        "validate",
        help="check structure and size rules; with chunks present, check every chunk id too",
    )
    validate.add_argument("--chunk-dir", type=Path, default=DEFAULT_CHUNK_DIR, help="chunk root")
    validate.add_argument(
        "--require-chunks", action="store_true", help="fail if the stored chunks are missing"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        gold = load_gold(args.gold)
    except GoldError as exc:
        print(f"ERROR {exc}")
        return EXIT_UNREADABLE if "cannot read" in str(exc) else EXIT_INVALID
    if args.command == "summary":
        print("\n".join(summarise(gold)))
        return EXIT_OK
    problems = check_composition(gold)
    if problems:
        print("\n".join(f"ERROR {p}" for p in problems))
        return EXIT_INVALID
    if args.chunk_dir.is_dir():
        mismatches = check_against_chunks(gold, args.chunk_dir)
        if mismatches:
            print("\n".join(f"ERROR {p}" for p in mismatches))
            return EXIT_CHUNK_MISMATCH
        print(f"OK  {len(gold.items)} items; every supporting chunk id found in {args.chunk_dir}")
    elif args.require_chunks:
        print(f"ERROR no chunks under {args.chunk_dir}")
        return EXIT_CHUNK_MISMATCH
    else:
        print(f"OK  {len(gold.items)} items; chunk ids not checked (no {args.chunk_dir})")
    return EXIT_OK
