"""Command line for the gold set and the scoring harness. Local files only; no network."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from bfs_reg_copilot.eval.fakes import DOUBLES
from bfs_reg_copilot.eval.gold import (
    GoldError,
    GoldSet,
    Split,
    check_against_chunks,
    check_composition,
    load_gold,
    summarise,
)
from bfs_reg_copilot.eval.grading import (
    Grades,
    GradingError,
    read_grades,
    write_grading_sheet,
)
from bfs_reg_copilot.eval.report import build_report, render_report
from bfs_reg_copilot.eval.runner import (
    HoldoutRefused,
    git_commit,
    gold_sha256,
    log_holdout_use,
    read_run,
    require_holdout_confirmation,
    run_eval,
    write_run,
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2
EXIT_CHUNK_MISMATCH = 3
EXIT_HOLDOUT_REFUSED = 4

DEFAULT_GOLD = Path("eval/gold/gold-v1.yaml")
DEFAULT_CHUNK_DIR = Path("data/curated")
DEFAULT_RUNS_DIR = Path("eval/runs")
DEFAULT_HOLDOUT_LOG = Path("eval/holdout-log.jsonl")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bfs_reg_copilot.eval", description="Check the gold set and score runs."
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
    run = sub.add_parser("run", help="run a pipeline over one split and store the answers")
    run.add_argument(
        "--pipeline",
        required=True,
        choices=sorted(DOUBLES),
        help="test doubles only for now; real pipelines arrive in later slices",
    )
    run.add_argument("--split", choices=[s.value for s in Split], default=Split.DEV.value)
    run.add_argument("--limit", type=int, default=None, help="at most N items per kind (smoke)")
    run.add_argument("--out-dir", type=Path, default=DEFAULT_RUNS_DIR, help="where runs are stored")
    run.add_argument("--repo-root", type=Path, default=Path("."), help="repo root (git commit)")
    run.add_argument("--confirm-holdout", action="store_true", help="needed for --split holdout")
    run.add_argument("--reason", default="", help="why the hold-out is being run (logged)")
    run.add_argument("--holdout-log", type=Path, default=DEFAULT_HOLDOUT_LOG)
    sheet = sub.add_parser("grade-sheet", help="write a CSV of answers for a person to grade")
    sheet.add_argument("run_dir", type=Path)
    sheet.add_argument("--out", type=Path, default=None, help="default: <run_dir>/grades.csv")
    score = sub.add_parser("score", help="print M1, M2, M4, M5 and M8 for a stored run")
    score.add_argument("run_dir", type=Path)
    score.add_argument("--grades", type=Path, default=None, help="default: <run_dir>/grades.csv")
    return parser


def _validate(gold: GoldSet, chunk_dir: Path, require_chunks: bool) -> int:
    problems = check_composition(gold)
    if problems:
        print("\n".join(f"ERROR {p}" for p in problems))
        return EXIT_INVALID
    if chunk_dir.is_dir():
        mismatches = check_against_chunks(gold, chunk_dir)
        if mismatches:
            print("\n".join(f"ERROR {p}" for p in mismatches))
            return EXIT_CHUNK_MISMATCH
        print(f"OK  {len(gold.items)} items; every supporting chunk id found in {chunk_dir}")
    elif require_chunks:
        print(f"ERROR no chunks under {chunk_dir}")
        return EXIT_CHUNK_MISMATCH
    else:
        print(f"OK  {len(gold.items)} items; chunk ids not checked (no {chunk_dir})")
    return EXIT_OK


def _run(gold: GoldSet, args: argparse.Namespace) -> int:
    split = Split(args.split)
    try:
        require_holdout_confirmation(split, confirmed=args.confirm_holdout, reason=args.reason)
    except HoldoutRefused as exc:
        print(f"ERROR {exc}")
        return EXIT_HOLDOUT_REFUSED
    pipeline = DOUBLES[args.pipeline](gold)
    meta, records = run_eval(
        gold,
        pipeline,
        split,
        gold_hash=gold_sha256(args.gold),
        commit=git_commit(args.repo_root),
        limit=args.limit,
    )
    run_dir = write_run(args.out_dir, meta, records)
    if split == Split.HOLDOUT:
        log_holdout_use(args.holdout_log, meta, args.reason)
    print(f"stored {meta.n_items} answers in {run_dir}")
    print("\n".join(render_report(build_report(gold, meta, records, Grades()))))
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        gold = load_gold(args.gold)
    except GoldError as exc:
        print(f"ERROR {exc}")
        return EXIT_UNREADABLE if "cannot read" in str(exc) else EXIT_INVALID
    try:
        if args.command == "summary":
            print("\n".join(summarise(gold)))
            return EXIT_OK
        if args.command == "validate":
            return _validate(gold, args.chunk_dir, args.require_chunks)
        if args.command == "run":
            return _run(gold, args)
        meta, records = read_run(args.run_dir)
        if args.command == "grade-sheet":
            out = args.out or args.run_dir / "grades.csv"
            count = write_grading_sheet(out, gold, records)
            print(f"wrote {count} rows to {out}; fill points_hit / verdict, then run score")
            return EXIT_OK
        grades_path = args.grades or args.run_dir / "grades.csv"
        grades = read_grades(grades_path, gold) if grades_path.exists() else Grades()
        print("\n".join(render_report(build_report(gold, meta, records, grades))))
        return EXIT_OK
    except (GradingError, OSError, ValueError) as exc:
        print(f"ERROR {exc}")
        return EXIT_UNREADABLE
