# 10. Running the ingest DAG (Airflow)

The DAG `regcopilot_ingest` runs the whole Phase 1 pipeline: fetch, clean, chunk, quality checks.
Design reasons are in ADR-0013. The stages themselves also run without Airflow:

```
uv run python -m bfs_reg_copilot.ingest fetch <source_id>   # then clean, chunk, dq
```

Airflow needs Linux. Use a **GitHub Codespace** (recommended: nothing to install locally) or
**WSL2**. Airflow is kept out of `pyproject.toml` on purpose.

## One-time setup (Codespace or WSL2 Ubuntu)

```bash
pip install uv                      # if uv is not already installed
uv sync                             # the project's own environment
uv venv .venv-airflow --python 3.12
AIRFLOW_VERSION=3.4.0
CONSTRAINTS="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt"
uv pip install --python .venv-airflow/bin/python "apache-airflow==${AIRFLOW_VERSION}" --constraint "$CONSTRAINTS"
uv pip install --python .venv-airflow/bin/python -e . pytest --constraint "$CONSTRAINTS"
```

In WSL2, clone the repository inside the Linux home folder (for example `~/dev`), not under
`/mnt/c`. Files on the Windows drive are slow and their permissions confuse tools.

## Every session

```bash
source .venv-airflow/bin/activate
export AIRFLOW_HOME="$PWD/.airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
airflow db migrate
airflow dags list                   # regcopilot_ingest should appear
```

## Check the DAG

```bash
# structure only, quick
python -m pytest tests/test_dag.py -q

# the whole DAG with a fake web server (no network); run this after changing dags/
BFS_AIRFLOW_E2E=1 python -m pytest tests/test_dag.py -q
```

## Run it for real

```bash
airflow dags test regcopilot_ingest
```

This runs every task once in one process, against the real sites. It keeps the 2 second gap between
requests, so expect a few minutes. Afterwards run `python -m bfs_reg_copilot.ingest dq` and look at
`data/` (git-ignored). A fetch that fails or is refused turns the run red, and the other sources
are still processed.

For the web interface and scheduler, run `airflow standalone` and open the forwarded port 8080.
Keep the port **private** (the Codespaces default); the login password is printed in the terminal.

## Things that can go wrong

| Symptom | Likely cause |
|---|---|
| DAG missing from `airflow dags list` | Import error: run `airflow dags list-import-errors` |
| `ModuleNotFoundError: bfs_reg_copilot` | The project was not installed into `.venv-airflow` (last setup line) |
| Run is green but a task is red | Should not happen: `verdict` is the last task. If it does, the dependencies in the DAG were changed |
| Two runs fetch at once | `max_active_runs` was raised; keep it at 1 |
