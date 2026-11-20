# ADR-0013: Airflow orchestrates a thin DAG over tested plain-Python stages

- Status: Accepted
- Date: 2026-11-19
- Deciders: Project owner

## Context

Phase 1 needs the corpus refreshed on a schedule: fetch, clean, chunk, check. The stages already
exist as plain Python (slices 1.1 to 1.5). Airflow is the orchestration tool this project set out
to learn, and later phases (embedding refresh, evaluation runs) will need the same pattern.
Airflow does not run on native Windows, and it pins many dependencies.

## Decision

- The stages live in `bfs_reg_copilot.ingest.pipeline` and are tested without Airflow. The DAG
  (`dags/regcopilot_ingest.py`) only decides when and in what order they run.
- Shape: `fetch_all` (one task) then `clean` and `chunk` (one mapped task per source) then `dq`
  then `verdict`.
- **One fetch task, not one per source.** Fetching must keep a 2 second gap between requests to a
  host (ADR-0009). That gap is kept by one fetcher object. Separate tasks would each start their
  own clock and could hit a host back to back.
- **`verdict` depends on every other task.** Airflow judges a run by its last tasks. Without
  `verdict`, a run where a fetch failed but the data-quality task still ran would be shown green.
  This was found by running the DAG, not by reading it.
- Later tasks use `trigger_rule="all_done"` so one bad source does not stop the others.
- No retries (ADR-0009), `max_active_runs=1` (no two runs fetching at once), weekly schedule,
  `catchup=False`.
- Airflow 3.4.0 is installed in its own environment with the project's official constraints file.
  It is **not** added to `pyproject.toml` or `uv.lock`, so the Windows toolchain and CI stay light.
- The project's dependencies (pydantic, httpx, beautifulsoup4, PyYAML) are compatible with
  Airflow 3.4.0's constraints, so the project installs into the Airflow environment unchanged.

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| GitHub Actions scheduled workflow or cron | Simpler and enough for seven pages. Not chosen because the goal includes learning Airflow and later phases need DAG features. Remains the fallback if Airflow becomes a burden |
| A task per source for fetching | Breaks the polite gap between requests |
| Airflow in `pyproject.toml` | Does not install on Windows and bloats the lock file |
| Retries on fetch | Hides real failures and adds load on public servers; revisit with backoff |

## Consequences

- Normal CI (no Airflow) skips `tests/test_dag.py`. Changes to `dags/` must be checked by running
  those tests in the Airflow environment, with `BFS_AIRFLOW_E2E=1` for the full run.
- A fresh clone has no corpus, so the first scheduled run fetches everything.
- Running Airflow needs Linux: a Codespace or WSL2 (docs/10-orchestration.md).

## Revisit when

The DAG grows beyond ingestion, a task needs retries with backoff, or the Airflow environment
costs more effort than it teaches.
