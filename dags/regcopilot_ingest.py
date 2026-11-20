"""Airflow DAG: refresh the regulatory corpus (fetch, clean, chunk, check).

This file decides *when* and *in what order* the stages run. What each stage does lives in
`bfs_reg_copilot.ingest.pipeline`, which is tested without Airflow (ADR-0013).

Shape::

    fetch_all  ->  clean (one task per source)  ->  chunk (one per source)  ->  dq  ->  verdict

Design points that are easy to break:

* `fetch_all` is ONE task that fetches the sources one after another through one fetcher. That is
  what keeps the 2 second gap between requests to the same host. A task per source would start a
  new fetcher (and a new clock) each time and could hit a host back to back (ADR-0009).
* `max_active_runs=1` stops two runs from fetching at the same time.
* No retries: a failure is shown, not hidden (ADR-0009). Re-run the DAG to try again.
* Later tasks use `trigger_rule="all_done"`, so one source failing to fetch does not stop the
  others from being cleaned and checked.
* `verdict` is the last task. It depends on EVERY other task and uses the default rule, so it only
  runs when all of them succeeded (a rule looks only at direct upstream tasks). Airflow
  judges a whole run by its last tasks, so without it a run with a failed fetch would still be
  shown as green.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from airflow.sdk import dag, task

from bfs_reg_copilot.ingest import run_dq
from bfs_reg_copilot.ingest.pipeline import (
    DataDirs,
    chunk_source,
    clean_source,
    fetch_sources,
)
from bfs_reg_copilot.registry import load_register

log = logging.getLogger(__name__)

REPO_ROOT = Path(os.environ.get("BFS_REPO_ROOT", Path(__file__).resolve().parents[1]))
DATA_ROOT = Path(os.environ.get("BFS_DATA_DIR", REPO_ROOT / "data"))
REGISTER = load_register(REPO_ROOT / "data" / "sources" / "register.yaml")
DIRS = DataDirs.under(DATA_ROOT)
# Read once, when Airflow parses this file. A broken register fails the parse loudly.
SOURCE_IDS = [source.id for source in REGISTER.ingestible()]


@dag(
    dag_id="regcopilot_ingest",
    description="Fetch, clean, chunk and quality-check the registered regulatory sources",
    schedule="@weekly",  # guidance changes rarely; weekly is plenty and polite
    start_date=datetime(2026, 11, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},
    tags=["regcopilot", "phase-1"],
)
def regcopilot_ingest() -> None:
    @task
    def fetch_all() -> list[dict[str, Any]]:
        outcomes = fetch_sources(REGISTER, SOURCE_IDS, DIRS.raw)
        summary: list[dict[str, Any]] = []
        for outcome in outcomes:
            if outcome.saved is None:
                log.error("fetch failed for %s: %s", outcome.source_id, outcome.error)
                summary.append({"source_id": outcome.source_id, "status": "failed"})
            else:
                state = "new" if outcome.saved.is_new_content else "unchanged"
                log.info("fetched %s (%s)", outcome.source_id, state)
                summary.append(
                    {
                        "source_id": outcome.source_id,
                        "status": state,
                        "sha256": outcome.saved.record.sha256,
                    }
                )
        failed = [o.source_id for o in outcomes if not o.ok]
        if failed:  # every source was attempted before we raise
            raise RuntimeError(f"fetch failed for: {', '.join(failed)}")
        return summary

    @task(trigger_rule="all_done")
    def clean(source_id: str) -> str:
        result = clean_source(REGISTER, source_id, DIRS)
        log.info("cleaned %s: %d sections", source_id, result.sections)
        return str(result.path)

    @task(trigger_rule="all_done")
    def chunk(source_id: str) -> str:
        result = chunk_source(REGISTER, source_id, DIRS)
        log.info("chunked %s: %d chunks", source_id, result.chunks)
        return str(result.path)

    @task(trigger_rule="all_done")
    def dq() -> None:
        report = run_dq(
            REGISTER,
            raw_root=DIRS.raw,
            cleaned_root=DIRS.cleaned,
            curated_root=DIRS.curated,
            repo_root=REPO_ROOT,
        )
        for finding in report.findings:
            log.warning(finding.line())
        log.info(
            "data quality: %d error(s), %d warning(s)", len(report.errors), len(report.warnings)
        )
        if report.errors:
            raise RuntimeError(f"data-quality errors: {len(report.errors)}")

    @task
    def verdict() -> None:
        """Runs only if every task before it succeeded; otherwise the run is shown as failed."""

    fetched = fetch_all()
    cleaned = clean.expand(source_id=SOURCE_IDS)
    chunked = chunk.expand(source_id=SOURCE_IDS)
    checked = dq()
    fetched >> cleaned >> chunked >> checked
    [fetched, cleaned, chunked, checked] >> verdict()


regcopilot_ingest()
