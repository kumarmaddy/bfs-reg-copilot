"""Command line: `compare` retrievers on the dev questions; `ask` shows chunks for one question."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import closing

from pg8000.exceptions import DatabaseError, InterfaceError

from bfs_reg_copilot.embed.compare import dev_items, missing_support
from bfs_reg_copilot.embed.models import MODELS, get_model
from bfs_reg_copilot.embed.ollama import EmbedError, OllamaEmbedder
from bfs_reg_copilot.eval.gold import GoldError, load_gold
from bfs_reg_copilot.retrieve.evaluate import evaluate_retriever, render_comparison
from bfs_reg_copilot.retrieve.retrievers import make_retrievers
from bfs_reg_copilot.retrieve.types import Retriever
from bfs_reg_copilot.store.cli import DEFAULT_GOLD
from bfs_reg_copilot.store.db import Conn, connect, database_url, describe
from bfs_reg_copilot.store.loader import counts, embedded_by_model

EXIT_OK = 0
EXIT_UNREACHABLE = 1
EXIT_NOT_READY = 2
EXIT_EMBED_FAILED = 4
DEFAULT_MODEL = "bge-m3"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bfs_reg_copilot.retrieve", description="Try the retrievers."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("compare", help="dense vs keyword vs hybrid on the dev questions")
    ask = sub.add_parser("ask", help="show the chunks a retriever returns for one question")
    ask.add_argument("question")
    ask.add_argument("--retriever", default="dense", choices=["dense", "fulltext", "hybrid"])
    ask.add_argument("--k", type=int, default=5)
    return parser


def _ready(conn: Conn, model: str) -> str | None:
    total = sum(t for _, t, _ in counts(conn))
    have = dict(embedded_by_model(conn)).get(model, 0)
    if total == 0 or have != total:
        return f"{model} has {have}/{total} chunks embedded; run the store load and embed commands"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        conn = connect()
    except (OSError, InterfaceError, DatabaseError) as exc:
        print(f"cannot connect to {describe(database_url())}: {type(exc).__name__}: {exc}")
        return EXIT_UNREACHABLE
    with closing(conn):
        problem = _ready(conn, args.model)
        if problem:
            print(problem)
            return EXIT_NOT_READY
        retrievers = make_retrievers(conn, OllamaEmbedder(get_model(args.model)))
        try:
            if args.command == "compare":
                return _compare(conn, retrievers)
            return _ask(conn, retrievers[args.retriever], args.question, args.k)
        except EmbedError as exc:
            print(f"embedding failed: {exc}")
            return EXIT_EMBED_FAILED


def _compare(conn: Conn, retrievers: dict[str, Retriever]) -> int:
    try:
        items = dev_items(load_gold(DEFAULT_GOLD))
    except GoldError as exc:
        print(exc)
        return EXIT_NOT_READY
    absent = missing_support(conn, items)
    if absent:
        print(f"database lacks the supporting sections of {len(absent)} items: {absent[:5]}")
        return EXIT_NOT_READY
    results = [evaluate_retriever(r, items) for r in retrievers.values()]
    print(render_comparison(results))
    return EXIT_OK


def _ask(conn: Conn, retriever: Retriever, question: str, k: int) -> int:
    hits = retriever.retrieve(question, k)
    cur = conn.cursor()
    for rank, hit in enumerate(hits, start=1):
        cur.execute("SELECT section_path, text FROM chunks WHERE chunk_id = %s", (hit.chunk_id,))
        row = cur.fetchone()
        path, text = (row[0], row[1]) if row else ([], "")
        snippet = " ".join(str(text).split())[:160]
        print(f"{rank}. {hit.chunk_id}  score {hit.score:.4f}")
        print(f"   {' > '.join(path[-2:])}")
        print(f"   {snippet}...")
    return EXIT_OK
