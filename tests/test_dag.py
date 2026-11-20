"""Tests for the Airflow DAG file. They need Airflow, so they are skipped without it.

Airflow does not run on native Windows, so on a Windows machine these are skipped. They run in a
Linux environment with Airflow installed (see docs/10-orchestration.md). The structure test is
quick; the end-to-end test runs the whole DAG and needs BFS_AIRFLOW_E2E=1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Keep Airflow's files out of the developer's home folder.
os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="airflow-tests-"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
dagbag_module = pytest.importorskip("airflow.dag_processing.dagbag")

ROOT = Path(__file__).resolve().parents[1]
DAGS = ROOT / "dags"
RUNNER = ROOT / "scripts" / "airflow_e2e.py"


def _dag() -> object:
    bag = dagbag_module.DagBag(dag_folder=str(DAGS))
    assert bag.import_errors == {}
    return bag.dags["regcopilot_ingest"]


def test_the_dag_parses_without_errors() -> None:
    assert _dag() is not None


def test_the_dag_has_the_designed_shape() -> None:
    dag = _dag()
    tasks = dag.task_dict  # type: ignore[attr-defined]
    assert set(tasks) == {"fetch_all", "clean", "chunk", "dq", "verdict"}
    assert tasks["fetch_all"].upstream_task_ids == set()
    assert tasks["clean"].upstream_task_ids == {"fetch_all"}
    assert tasks["chunk"].upstream_task_ids == {"clean"}
    assert tasks["dq"].upstream_task_ids == {"chunk"}
    # The last task waits for everything, or a failed fetch would leave the run green.
    assert tasks["verdict"].upstream_task_ids == {"fetch_all", "clean", "chunk", "dq"}


def test_fetching_is_one_sequential_task_and_the_rest_fan_out() -> None:
    tasks = _dag().task_dict  # type: ignore[attr-defined]
    assert not tasks["fetch_all"].is_mapped  # one task keeps the polite gap between requests
    assert tasks["clean"].is_mapped
    assert tasks["chunk"].is_mapped


def test_the_dag_settings_that_protect_the_publishers() -> None:
    dag = _dag()
    assert dag.max_active_runs == 1  # type: ignore[attr-defined]
    assert dag.catchup is False  # type: ignore[attr-defined]
    for task in dag.tasks:  # type: ignore[attr-defined]
        assert task.retries == 0


def _run(mode: str, tmp_path: Path) -> dict[str, object]:
    env = {
        **os.environ,
        "AIRFLOW_HOME": str(tmp_path / "airflow"),
        "AIRFLOW__CORE__DAGS_FOLDER": str(DAGS),
        "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
        "BFS_DATA_DIR": str(tmp_path / "data"),
    }
    airflow = Path(sys.executable).parent / "airflow"
    subprocess.run([str(airflow), "db", "migrate"], env=env, check=True, capture_output=True)  # noqa: S603
    done = subprocess.run(  # noqa: S603
        [sys.executable, str(RUNNER), mode], env=env, check=True, capture_output=True, text=True
    )
    last_line = done.stdout.strip().splitlines()[-1]
    return json.loads(last_line)  # type: ignore[no-any-return]


@pytest.mark.skipif(os.environ.get("BFS_AIRFLOW_E2E") != "1", reason="set BFS_AIRFLOW_E2E=1")
def test_end_to_end_success(tmp_path: Path) -> None:
    result = _run("ok", tmp_path)
    assert result["state"] == "success"
    assert set(result["tasks"].values()) == {"success"}  # type: ignore[attr-defined]
    assert list((tmp_path / "data" / "curated").rglob("*.jsonl"))


@pytest.mark.skipif(os.environ.get("BFS_AIRFLOW_E2E") != "1", reason="set BFS_AIRFLOW_E2E=1")
def test_end_to_end_one_failed_fetch_fails_the_run_but_not_the_other_sources(
    tmp_path: Path,
) -> None:
    result = _run("fail", tmp_path)
    tasks: dict[str, str] = result["tasks"]  # type: ignore[assignment]
    assert result["state"] == "failed"
    assert tasks["fetch_all[-1]"] == "failed"
    assert tasks["verdict[-1]"] == "upstream_failed"
    # the sources that did fetch were still cleaned and chunked
    assert sum(state == "success" for key, state in tasks.items() if key.startswith("chunk")) >= 1
