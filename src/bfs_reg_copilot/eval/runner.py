"""Run a pipeline over one split of the gold set and store what it said.

Dev runs are free. A hold-out run needs an explicit confirmation and a reason, and is appended to
`eval/holdout-log.jsonl` (ADR-0014): the seal is enforced here, not left to memory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from bfs_reg_copilot.eval.gold import AdversarialItem, GoldSet, Split
from bfs_reg_copilot.eval.types import Pipeline, PipelineAnswer, RunMeta, RunRecord

KINDS = ("answerable", "refusal", "adversarial")
ERROR_LIMIT = 300


class HoldoutRefused(Exception):
    """A hold-out run was requested without confirmation or a reason."""


def gold_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit(repo_root: Path) -> str:
    """The commit the run was made from; `+dirty` if the tree had uncommitted changes."""
    git = shutil.which("git")
    if git is None or not (repo_root / ".git").exists():
        return "unknown"
    try:
        head = subprocess.run(  # noqa: S603 - fixed arguments, no user input
            [git, "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(  # noqa: S603 - fixed arguments, no user input
            [git, "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{head}+dirty" if status else head


def require_holdout_confirmation(split: Split, *, confirmed: bool, reason: str) -> None:
    if split == Split.HOLDOUT and (not confirmed or not reason.strip()):
        raise HoldoutRefused(
            "the hold-out is sealed: pass --confirm-holdout and --reason to run it (ADR-0014)"
        )


def select_items(gold: GoldSet, split: Split, limit: int | None) -> tuple[list[str], list[str]]:
    """Ids to run and ids skipped (items that cannot be run yet). `limit` is per kind, by id."""
    chosen: list[str] = []
    skipped: list[str] = []
    for kind in KINDS:
        items = sorted((i for i in gold.of_kind(kind) if i.split == split), key=lambda i: i.id)
        runnable = []
        for item in items:
            if isinstance(item, AdversarialItem) and not item.scored:
                skipped.append(item.id)
            else:
                runnable.append(item.id)
        chosen += runnable[:limit] if limit is not None else runnable
    return chosen, skipped


def run_eval(
    gold: GoldSet,
    pipeline: Pipeline,
    split: Split,
    *,
    gold_hash: str,
    commit: str,
    limit: int | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[RunMeta, list[RunRecord]]:
    started = clock()
    ids, skipped = select_items(gold, split, limit)
    by_id = {i.id: i for i in gold.items}
    records: list[RunRecord] = []
    for item_id in ids:
        item = by_id[item_id]
        began = time.perf_counter()
        answer: PipelineAnswer | None = None
        error = ""
        try:
            answer = pipeline.answer(item.question)
        except Exception as exc:  # one bad answer must not stop the whole run
            error = f"{type(exc).__name__}: {exc}"[:ERROR_LIMIT]
        records.append(
            RunRecord(
                item_id=item_id,
                kind=item.kind,
                split=item.split,
                question=item.question,
                answer=answer,
                error=error,
                latency_s=time.perf_counter() - began,
            )
        )
    finished = clock()
    meta = RunMeta(
        run_id=f"{started:%Y%m%dT%H%M%SZ}-{pipeline.name}-{split.value}",
        started_at=started,
        finished_at=finished,
        split=split,
        pipeline=pipeline.name,
        is_test_double=pipeline.is_test_double,
        settings=pipeline.describe(),
        gold_sha256=gold_hash,
        gold_version=gold.version,
        git_commit=commit,
        n_items=len(records),
        skipped=tuple(skipped),
    )
    return meta, records


def write_run(out_dir: Path, meta: RunMeta, records: list[RunRecord]) -> Path:
    run_dir = out_dir / meta.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
    with (run_dir / "answers.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")
    return run_dir


def read_run(run_dir: Path) -> tuple[RunMeta, list[RunRecord]]:
    meta = RunMeta.model_validate_json((run_dir / "meta.json").read_text(encoding="utf-8"))
    lines = (run_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines()
    return meta, [RunRecord.model_validate_json(line) for line in lines if line.strip()]


def log_holdout_use(log_path: Path, meta: RunMeta, reason: str) -> None:
    """Append-only record that the hold-out was run, when, by which pipeline and why."""
    entry = {
        "at": meta.finished_at.isoformat(),
        "run_id": meta.run_id,
        "pipeline": meta.pipeline,
        "git_commit": meta.git_commit,
        "reason": reason.strip(),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry) + "\n")
