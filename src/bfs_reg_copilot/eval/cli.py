"""Command line for the gold set and the scoring harness.

Only the `baseline` pipeline needs the local database and the local model server; everything else
reads local files."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from bfs_reg_copilot.eval.compare import CompareError, Rule, compare_runs, render
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
    carry_grades,
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
from bfs_reg_copilot.eval.types import Pipeline, RunRecord
from bfs_reg_copilot.rag.factory import DEFAULT_GENERATOR

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2
EXIT_CHUNK_MISMATCH = 3
EXIT_HOLDOUT_REFUSED = 4

BASELINE = "baseline"
DEFAULT_GOLD = Path("eval/gold/gold-v2.yaml")
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
        choices=[*sorted(DOUBLES), BASELINE],
        help="a test double, or `baseline` (needs the database and Ollama)",
    )
    run.add_argument("--model", default=DEFAULT_GENERATOR, help="generator for `baseline`")
    run.add_argument("--k", type=int, default=5, help="chunks given to the generator")
    run.add_argument(
        "--prompt-version",
        default="v1",
        choices=["v1", "v2"],
        help="system prompt for `baseline` (v1 is the measured baseline)",
    )
    run.add_argument("--split", choices=[s.value for s in Split], default=Split.DEV.value)
    run.add_argument("--items", default="", help="only these item ids, comma-separated")
    run.add_argument(
        "--gold-context",
        action="store_true",
        help="ceiling probe: give the generator the gold supporting chunks (dev only)",
    )
    run.add_argument(
        "--max-answer-tokens",
        type=int,
        default=None,
        help="answer budget; default 512. A reasoning model spends it on thinking first",
    )
    run.add_argument(
        "--no-think",
        action="store_true",
        help="ask a reasoning model not to think first (recorded in the run's settings)",
    )
    run.add_argument("--limit", type=int, default=None, help="at most N items per kind (smoke)")
    run.add_argument("--out-dir", type=Path, default=DEFAULT_RUNS_DIR, help="where runs are stored")
    run.add_argument("--repo-root", type=Path, default=Path("."), help="repo root (git commit)")
    run.add_argument("--confirm-holdout", action="store_true", help="needed for --split holdout")
    run.add_argument("--reason", default="", help="why the hold-out is being run (logged)")
    run.add_argument("--holdout-log", type=Path, default=DEFAULT_HOLDOUT_LOG)
    sheet = sub.add_parser("grade-sheet", help="write a CSV of answers for a person to grade")
    sheet.add_argument("run_dir", type=Path)
    sheet.add_argument("--out", type=Path, default=None, help="default: <run_dir>/grades.csv")
    sheet.add_argument(
        "--carry-from",
        type=Path,
        default=None,
        help="an earlier run folder; with --carry-grades, copy grades of unchanged answers",
    )
    sheet.add_argument(
        "--carry-grades", type=Path, default=None, help="the grades file of --carry-from"
    )
    flips = sub.add_parser(
        "flips", help="compare two graded runs question by question against a decision rule"
    )
    flips.add_argument("before", type=Path, help="run folder of the earlier version")
    flips.add_argument("after", type=Path, help="run folder of the changed version")
    flips.add_argument("--grades-before", type=Path, required=True)
    flips.add_argument("--grades-after", type=Path, required=True)
    defaults = Rule()
    flips.add_argument("--min-fixed", type=int, default=defaults.min_fixed)
    flips.add_argument("--max-broken", type=int, default=defaults.max_broken)
    flips.add_argument("--max-refusal-rise", type=int, default=defaults.max_refusal_rise)
    flips.add_argument("--max-p95", type=float, default=defaults.max_p95_s)
    context = sub.add_parser(
        "context",
        help="show the text the model received for failing questions and which key points it holds",
    )
    context.add_argument("run_dir", type=Path)
    context.add_argument("--grades", type=Path, default=None, help="default: <run_dir>/grades.csv")
    context.add_argument(
        "--items", default="", help="comma-separated item ids (default: every question that failed)"
    )
    context.add_argument(
        "--out", type=Path, default=None, help="default: <run_dir>/context-report.md"
    )
    audit = sub.add_parser(
        "chunk-audit",
        help="count low-value context slots and cut lists (read-only; needs the database)",
    )
    audit.add_argument("run_dir", type=Path)
    audit.add_argument("--grades", type=Path, default=None, help="default: <run_dir>/grades.csv")
    review = sub.add_parser(
        "rubric-review",
        help="write a sheet with each key point next to the gold source text (needs the database)",
    )
    review.add_argument("--items", default="", help="comma-separated item ids (default: six)")
    review.add_argument("--out", type=Path, default=Path("eval/runs/rubric-review.md"))
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
    if args.gold_context and (args.pipeline != BASELINE or split != Split.DEV):
        print("ERROR --gold-context works only with `--pipeline baseline` on the dev split")
        return EXIT_INVALID
    if args.pipeline == BASELINE:
        return _run_baseline(gold, args, split)
    return _finish_run(gold, args, split, DOUBLES[args.pipeline](gold))


def _run_baseline(gold: GoldSet, args: argparse.Namespace, split: Split) -> int:
    from contextlib import closing

    from pg8000.exceptions import DatabaseError, InterfaceError

    from bfs_reg_copilot.gateway.types import GatewayError
    from bfs_reg_copilot.rag.factory import build_baseline
    from bfs_reg_copilot.rag.pipeline import MAX_ANSWER_TOKENS
    from bfs_reg_copilot.retrieve.gold_context import gold_context_map
    from bfs_reg_copilot.store.db import connect, database_url, describe
    from bfs_reg_copilot.store.loader import counts, embedded_by_model

    try:
        conn = connect()
    except (OSError, InterfaceError, DatabaseError) as exc:
        print(f"ERROR cannot connect to {describe(database_url())}: {type(exc).__name__}: {exc}")
        return EXIT_UNREADABLE
    with closing(conn):
        total = sum(t for _, t, _ in counts(conn))
        have = dict(embedded_by_model(conn)).get("bge-m3", 0)
        if not total or have != total:
            print(f"ERROR the database has {have}/{total} chunks embedded with bge-m3")
            return EXIT_UNREADABLE
        try:
            pipeline = build_baseline(
                conn,
                args.model,
                args.k,
                args.prompt_version,
                gold_context_map(gold) if args.gold_context else None,
                False if args.no_think else None,
                args.max_answer_tokens or MAX_ANSWER_TOKENS,
            )
            pipeline.check_ready()
        except GatewayError as exc:
            print(f"ERROR {exc}")
            return EXIT_UNREADABLE
        code = _finish_run(gold, args, split, pipeline, progress=_print_progress)
        print(f"malformed model outputs: {pipeline.malformed}")
        usage = pipeline._gateway.usage
        print(
            f"model calls: {usage.calls}, prompt tokens {usage.prompt_tokens}, "
            f"completion tokens {usage.completion_tokens}, model time {usage.seconds:.0f}s"
        )
        return code


def _context(gold: GoldSet, args: argparse.Namespace, records: list[RunRecord]) -> int:
    from contextlib import closing

    from pg8000.exceptions import DatabaseError, InterfaceError

    from bfs_reg_copilot.eval.context import failing_items, needed_chunk_ids
    from bfs_reg_copilot.eval.context import render_report as render_context
    from bfs_reg_copilot.rag.pipeline import DbChunkSource
    from bfs_reg_copilot.store.db import connect, database_url, describe

    grades_path = args.grades or args.run_dir / "grades.csv"
    if not grades_path.exists():
        raise GradingError(f"grades file not found: {grades_path}")
    grades = read_grades(grades_path, gold)
    wanted = [i.strip() for i in args.items.split(",") if i.strip()]
    item_ids = wanted or failing_items(gold, records, grades)
    known = {r.item_id for r in records}
    unknown = [i for i in item_ids if i not in known]
    if unknown:
        raise GradingError(f"not in this run: {', '.join(unknown)}")
    try:
        conn = connect()
    except (OSError, InterfaceError, DatabaseError) as exc:
        print(f"ERROR cannot connect to {describe(database_url())}: {type(exc).__name__}: {exc}")
        return EXIT_UNREADABLE
    with closing(conn):
        chunk_ids = needed_chunk_ids(gold, records, item_ids)
        texts = {c.chunk_id: c.text for c in DbChunkSource(conn).fetch(chunk_ids)}
    report, summary = render_context(gold, records, grades, item_ids, texts)
    out = args.out or args.run_dir / "context-report.md"
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"wrote {len(summary)} questions to {out} (corpus text: keep it out of git)")
    return EXIT_OK


def _rubric_review(gold: GoldSet, args: argparse.Namespace) -> int:
    from contextlib import closing

    from pg8000.exceptions import DatabaseError, InterfaceError

    from bfs_reg_copilot.eval.gold import AnswerableItem
    from bfs_reg_copilot.eval.rubric_review import DEFAULT_ITEMS, render_sheet
    from bfs_reg_copilot.rag.pipeline import DbChunkSource
    from bfs_reg_copilot.store.db import connect, database_url, describe

    wanted = [i.strip() for i in args.items.split(",") if i.strip()] or list(DEFAULT_ITEMS)
    items = {i.id: i for i in gold.items if isinstance(i, AnswerableItem)}
    unknown = [i for i in wanted if i not in items]
    if unknown:
        print(f"ERROR not answerable items in the gold set: {', '.join(unknown)}")
        return EXIT_INVALID
    try:
        conn = connect()
    except (OSError, InterfaceError, DatabaseError) as exc:
        print(f"ERROR cannot connect to {describe(database_url())}: {type(exc).__name__}: {exc}")
        return EXIT_UNREADABLE
    with closing(conn):
        ids = [c for i in wanted for c in items[i].supporting_chunks]
        texts = {c.chunk_id: c.text for c in DbChunkSource(conn).fetch(ids)}
    args.out.write_text("\n".join(render_sheet(gold, wanted, texts)) + "\n", encoding="utf-8")
    print(f"wrote {len(wanted)} questions to {args.out} (corpus text: keep it out of git)")
    return EXIT_OK


def _chunk_audit(gold: GoldSet, args: argparse.Namespace, records: list[RunRecord]) -> int:
    from contextlib import closing

    from pg8000.exceptions import DatabaseError, InterfaceError

    from bfs_reg_copilot.eval.chunk_audit import (
        ChunkRow,
        audit_run,
        cut_list_chunks,
        list_cut_boundaries,
        summarise_audit,
    )
    from bfs_reg_copilot.store.db import connect, database_url, describe

    grades_path = args.grades or args.run_dir / "grades.csv"
    grades = read_grades(grades_path, gold) if grades_path.exists() else Grades()
    try:
        conn = connect()
    except (OSError, InterfaceError, DatabaseError) as exc:
        print(f"ERROR cannot connect to {describe(database_url())}: {type(exc).__name__}: {exc}")
        return EXIT_UNREADABLE
    with closing(conn):
        cur = conn.cursor()
        cur.execute(
            "SELECT chunk_id, source_id, section_index, chunk_index, chunk_count, text "
            "FROM chunks WHERE superseded_at IS NULL"
        )
        rows = {
            str(r[0]): ChunkRow(str(r[0]), str(r[1]), int(r[2]), int(r[3]), int(r[4]), str(r[5]))
            for r in cur.fetchall()
        }
        conn.rollback()
    every = list(rows.values())
    cut = cut_list_chunks(every)
    boundaries = sum(1 for r in every if r.chunk_index + 1 < r.chunk_count)
    corpus_cut = len(list_cut_boundaries(every))
    audits = audit_run(gold, records, grades, rows, cut)
    print("\n".join(summarise_audit(audits, corpus_cut, boundaries)))
    return EXIT_OK


def _flips(gold: GoldSet, args: argparse.Namespace) -> int:
    runs = []
    for folder, grades_path in ((args.before, args.grades_before), (args.after, args.grades_after)):
        if not grades_path.exists():
            raise GradingError(f"grades file not found: {grades_path}")
        meta, records = read_run(folder)
        runs.append((meta, records, read_grades(grades_path, gold)))
    rule = Rule(
        min_fixed=args.min_fixed,
        max_broken=args.max_broken,
        max_refusal_rise=args.max_refusal_rise,
        max_p95_s=args.max_p95,
    )
    try:
        comparison = compare_runs(gold, runs[0], runs[1])
    except CompareError as exc:
        print(f"ERROR {exc}")
        return EXIT_UNREADABLE
    print("\n".join(render(comparison, rule)))
    return EXIT_OK


def _print_progress(done: int, total: int, item_id: str) -> None:
    print(f"  {done}/{total} {item_id}", flush=True)


def _finish_run(
    gold: GoldSet,
    args: argparse.Namespace,
    split: Split,
    pipeline: Pipeline,
    progress: Callable[[int, int, str], None] | None = None,
) -> int:
    meta, records = run_eval(
        gold,
        pipeline,
        split,
        gold_hash=gold_sha256(args.gold),
        commit=git_commit(args.repo_root),
        limit=args.limit,
        only=[i.strip() for i in args.items.split(",") if i.strip()] or None,
        progress=progress,
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
        if args.command == "flips":
            return _flips(gold, args)
        if args.command == "rubric-review":
            return _rubric_review(gold, args)
        meta, records = read_run(args.run_dir)
        if args.command == "context":
            return _context(gold, args, records)
        if args.command == "chunk-audit":
            return _chunk_audit(gold, args, records)
        if args.command == "grade-sheet":
            out = args.out or args.run_dir / "grades.csv"
            count = write_grading_sheet(out, gold, records)
            print(f"wrote {count} rows to {out}; fill points_hit / verdict, then run score")
            if (args.carry_from is None) != (args.carry_grades is None):
                raise GradingError("--carry-from and --carry-grades must be given together")
            if args.carry_from is not None:
                old_meta, old_records = read_run(args.carry_from)
                if old_meta.gold_sha256 != meta.gold_sha256:
                    print(
                        "NOTE the earlier run was recorded under a different gold file. Carried "
                        "grades are only as valid as the grades file: use the one that matches "
                        "the gold file in use now."
                    )
                carried, todo = carry_grades(
                    out, records, old_records, args.carry_grades, old_meta.run_id
                )
                print(
                    f"carried {carried} grades from {old_meta.run_id}; {todo} still need a person"
                )
            return EXIT_OK
        grades_path = args.grades or args.run_dir / "grades.csv"
        if args.grades is not None and not grades_path.exists():
            # An explicit path that is missing must not silently score as "no grades".
            raise GradingError(f"grades file not found: {grades_path}")
        grades = read_grades(grades_path, gold) if grades_path.exists() else Grades()
        print("\n".join(render_report(build_report(gold, meta, records, grades))))
        return EXIT_OK
    except (GradingError, OSError, ValueError) as exc:
        print(f"ERROR {exc}")
        return EXIT_UNREADABLE
