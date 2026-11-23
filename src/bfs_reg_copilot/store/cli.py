"""Command line for the database: `migrate`, `status`, `load`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from pg8000.exceptions import DatabaseError, InterfaceError

from bfs_reg_copilot.store.db import Conn, connect, database_url, describe
from bfs_reg_copilot.store.loader import counts, current_chunk_files, load_source
from bfs_reg_copilot.store.migrate import MigrationError, applied_versions, apply_pending, discover

EXIT_OK = 0
EXIT_UNREACHABLE = 1
EXIT_MIGRATION = 2
EXIT_NOTHING_TO_LOAD = 3

DEFAULT_CURATED_DIR = Path("data/curated")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bfs_reg_copilot.store",
        description="Create the schema and load chunks. URL from BFS_DATABASE_URL.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending migrations")
    sub.add_parser("status", help="show applied migrations and chunk counts")
    load = sub.add_parser("load", help="load the current chunk file of each source")
    load.add_argument("--curated-dir", type=Path, default=DEFAULT_CURATED_DIR)
    load.add_argument("--source", help="load only this source id")
    return parser


def _safe_target() -> str:
    return describe(database_url())


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        conn = connect()
    except (OSError, InterfaceError, DatabaseError) as exc:
        print(f"cannot connect to {_safe_target()}: {type(exc).__name__}: {exc}")
        print("is the database running? try: docker compose up -d")
        return EXIT_UNREACHABLE
    with closing(conn):
        try:
            if args.command == "migrate":
                done = apply_pending(conn, discover())
                print(f"applied: {', '.join(done)}" if done else "already up to date")
            elif args.command == "status":
                versions = applied_versions(conn)
                applied = ", ".join(versions) or "none"
                print(f"database {_safe_target()}; migrations applied: {applied}")
                if versions:
                    for source, total, embedded in counts(conn):
                        print(f"  {source}: {total} current chunks, {embedded} embedded")
            else:
                return _load(conn, args.curated_dir, args.source)
        except MigrationError as exc:
            print(f"migration problem: {exc}")
            return EXIT_MIGRATION
    return EXIT_OK


def _load(conn: Conn, root: Path, only: str | None) -> int:
    files = current_chunk_files(root, only)
    if not files:
        print(f"no chunk files under {root}" + (f" for {only}" if only else ""))
        return EXIT_NOTHING_TO_LOAD
    for source, path in files.items():
        r = load_source(conn, source, path)
        print(
            f"{source}: {r.inserted} new, {r.unchanged} unchanged, {r.changed} changed, "
            f"{r.superseded} superseded"
        )
    return EXIT_OK
