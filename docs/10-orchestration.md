# 10. Running the ingest DAG (Airflow)

The DAG `regcopilot_ingest` runs the whole Phase 1 pipeline: fetch, clean, chunk, quality checks.
Design reasons are in ADR-0013. The stages themselves also run without Airflow:

```
uv run python -m bfs_reg_copilot.ingest fetch <source_id>   # then clean, chunk, dq
```

Airflow needs Linux. Use a **GitHub Codespace** (nothing to install locally) or **WSL2**. Airflow is
kept out of `pyproject.toml` on purpose. These steps were run successfully in a Codespace on
2026-11-20.

## One-time setup (Codespace or WSL2 Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y python3.12-venv
python3.12 -m venv .venv-airflow
AIRFLOW_VERSION=3.4.0
CONSTRAINTS="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt"
.venv-airflow/bin/pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "$CONSTRAINTS"
.venv-airflow/bin/pip install -e . pytest --constraint "$CONSTRAINTS"
```

The install takes several minutes. In WSL2, clone the repository inside the Linux home folder (for
example `~/dev`), not under `/mnt/c`. Files on the Windows drive are slow and their permissions
confuse tools.

## Every session

```bash
source .venv-airflow/bin/activate
export AIRFLOW_HOME="$PWD/.airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
airflow db migrate
airflow dags reserialize            # registers the DAG in Airflow's database
airflow dags list                   # regcopilot_ingest should appear (paused is normal)
airflow dags list-import-errors     # "No data found" is the good answer
```

`airflow dags list` only shows DAGs already registered in the database, so it is empty until
`airflow dags reserialize` (or Airflow's background DAG processor) has run.

## Check the DAG

```bash
# structure only, quick: 4 passed, 2 skipped
python -m pytest tests/test_dag.py -q

# the whole DAG with a fake web server (no network): 6 passed in about 40 seconds.
# Run this after changing anything in dags/
BFS_AIRFLOW_E2E=1 python -m pytest tests/test_dag.py -q
```

## Run it for real

```bash
airflow dags test regcopilot_ingest
python -m bfs_reg_copilot.ingest dq
```

This runs every task once in one process, against the real sites. It keeps the 2 second gap between
requests. The first run in a fresh clone fetches all 7 sources as `new` and took about 30 seconds.
A fetch that fails or is refused turns the run red, and the other sources are still processed.
`data/` is git-ignored, so `git status` stays clean.

For the web interface and scheduler, run `airflow standalone` and open the forwarded port 8080.
Keep the port **private** (the Codespaces default); the login password is printed in the terminal.

## Things that can go wrong

| Symptom | Likely cause |
|---|---|
| `airflow dags list` says "No data found" | The DAG is not registered yet: run `airflow dags reserialize` |
| DAG still missing after that | Import error: run `airflow dags list-import-errors` |
| `ModuleNotFoundError: bfs_reg_copilot` | The project was not installed into `.venv-airflow` (last setup line) |
| `ensurepip is not available` | Install the `python3.12-venv` package (first setup line) |
| `uv` times out downloading packages in a Codespace, while `curl` works | Seen on 2026-11-20. Use `pip` as above. `uv venv --seed` also fails, because it downloads pip through `uv` |
| Cannot paste into the Codespace in Firefox | Use Edge or Chrome and allow clipboard access, or connect from desktop VS Code |
| Run is green but a task is red | Should not happen: `verdict` is the last task. If it does, the dependencies in the DAG were changed |
| Two runs fetch at once | `max_active_runs` was raised; keep it at 1 |
