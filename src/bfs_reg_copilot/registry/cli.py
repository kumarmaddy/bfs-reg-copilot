"""Command line interface: ``reg-register validate|summary [PATH]``."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import yaml

from bfs_reg_copilot.registry.loader import load_register

DEFAULT_PATH = Path("data/sources/register.yaml")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reg-register", description="Validate the source and licence register."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("validate", "check every rule; non-zero exit on failure"),
        ("summary", "print counts by pack and ingest status"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    path: Path = args.path
    try:
        register = load_register(path)
    except OSError as exc:
        print(f"UNREADABLE: {path}\n{exc}")
        return EXIT_UNREADABLE
    except (ValueError, yaml.YAMLError) as exc:  # pydantic's ValidationError is a ValueError
        print(f"INVALID: {path}\n{exc}")
        return EXIT_INVALID

    if args.command == "validate":
        print(
            f"OK: {path} - {len(register.sources)} sources "
            f"({len(register.ingestible())} ingestible), {len(register.pending)} pending"
        )
        return EXIT_OK

    by_pack: Counter[str] = Counter()
    blocked: list[str] = []
    for source in register.sources:
        by_pack[f"{source.pack.value}:{'ingest' if source.ingest_allowed else 'blocked'}"] += 1
        if not source.ingest_allowed:
            blocked.append(f"  - {source.id}: {source.blocking_reason}")
    for key in sorted(by_pack):
        print(f"{key:<16}{by_pack[key]}")
    print(f"pending         {len(register.pending)}")
    if blocked:
        print("blocked sources:")
        print("\n".join(blocked))
    return EXIT_OK
