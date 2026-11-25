"""Command line for the database: `migrate`, `status`, `load`, `embed`, `compare`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from pg8000.exceptions import DatabaseError, InterfaceError

from bfs_reg_copilot.embed.compare import dev_items, evaluate_model, missing_support, render
from bfs_reg_copilot.embed.indexer import index_model
from bfs_reg_copilot.embed.models import MODELS, get_model
from bfs_reg_copilot.embed.ollama import EmbedError, OllamaEmbedder
from bfs_reg_copilot.eval.gold import GoldError, load_gold
from bfs_reg_copilot.store.db import Conn, connect, database_url, describe
from bfs_reg_copilot.store.loader import (
    counts,
    current_chunk_files,
    embedded_by_model,
    load_source,
)
from bfs_reg_copilot.store.migrate import MigrationError, applied_versions, apply_pending, discover

EXIT_OK = 0
EXIT_UNREACHABLE = 1
EXIT_MIGRATION = 2
EXIT_NOTHING_TO_LOAD = 3
EXIT_EMBED_FAILED = 4
EXIT_GOLD_MISMATCH = 5

DEFAULT_CURATED_DIR = Path("data/curated")
DEFAULT_GOLD = Path("eval/gold/gold-v2.yaml")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bfs_reg_copilot.store",
        description="Create the schema, load chunks, embed them. URL from BFS_DATABASE_URL.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending migrations")
    sub.add_parser("status", help="show applied migrations, chunk counts and embeddings")
    load = sub.add_parser("load", help="load the current chunk file of each source")
    load.add_argument("--curated-dir", type=Path, default=DEFAULT_CURATED_DIR)
    load.add_argument("--source", help="load only this source id")
    embed = sub.add_parser("embed", help="embed current chunks that lack a vector for a model")
    embed.add_argument("--model", required=True, choices=sorted(MODELS))
    embed.add_argument("--batch-size", type=int, default=16)
    compare = sub.add_parser("compare", help="compare models on dev-split retrieval (hit@k)")
    compare.add_argument("--models", nargs="+", default=sorted(MODELS), choices=sorted(MODELS))
    compare.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
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
                _status(conn)
            elif args.command == "load":
                return _load(conn, args.curated_dir, args.source)
            elif args.command == "embed":
                return _embed(conn, args.model, args.batch_size)
            else:
                return _compare(conn, args.models, args.gold)
        except MigrationError as exc:
            print(f"migration problem: {exc}")
            return EXIT_MIGRATION
    return EXIT_OK


def _status(conn: Conn) -> None:
    versions = applied_versions(conn)
    applied = ", ".join(versions) or "none"
    print(f"database {_safe_target()}; migrations applied: {applied}")
    if not versions:
        return
    rows = counts(conn)
    for source, total, _ in rows:
        print(f"  {source}: {total} current chunks")
    total_chunks = sum(t for _, t, _ in rows)
    print(f"  total: {total_chunks} current chunks")
    for model, n in embedded_by_model(conn):
        print(f"  embedded with {model}: {n}/{total_chunks}")


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


def _embed(conn: Conn, model_name: str, batch_size: int) -> int:
    embedder = OllamaEmbedder(get_model(model_name))

    def progress(done: int, total: int) -> None:
        print(f"  {done}/{total}", flush=True)

    try:
        result = index_model(conn, embedder, batch_size, progress)
    except EmbedError as exc:
        print(f"embedding failed: {exc}")
        print(f"is Ollama running and is the model pulled? try: ollama pull {model_name}")
        return EXIT_EMBED_FAILED
    print(
        f"{result.model}: embedded {result.embedded} chunks "
        f"({result.already_done} already done) in {result.seconds:.0f}s"
    )
    return EXIT_OK


def _compare(conn: Conn, model_names: Sequence[str], gold_path: Path) -> int:
    try:
        items = dev_items(load_gold(gold_path))
    except GoldError as exc:
        print(exc)
        return EXIT_GOLD_MISMATCH
    absent = missing_support(conn, items)
    if absent:
        print(f"database lacks the supporting sections of {len(absent)} items: {absent[:5]}")
        print("the gold set was written against a different page version, or chunks are not loaded")
        return EXIT_GOLD_MISMATCH
    total = sum(t for _, t, _ in counts(conn))
    have = dict(embedded_by_model(conn))
    for name in model_names:
        if have.get(name, 0) != total:
            print(
                f"{name} has {have.get(name, 0)}/{total} chunks embedded; run: embed --model {name}"
            )
            return EXIT_GOLD_MISMATCH
    results = []
    try:
        for name in model_names:
            results.append(evaluate_model(conn, OllamaEmbedder(get_model(name)), items))
    except EmbedError as exc:
        print(f"embedding failed: {exc}")
        return EXIT_EMBED_FAILED
    print(render(results))
    return EXIT_OK
