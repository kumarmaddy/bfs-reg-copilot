"""Run the ingest DAG once, in-process, with the network replaced by a fake web server.

Used by tests/test_dag.py (when BFS_AIRFLOW_E2E=1) and runnable by hand inside the Airflow
environment:  python scripts/airflow_e2e.py ok|fail

`fail` makes the first registered source answer HTTP 503, to prove that one bad source fails the
run without stopping the others. The last line printed is JSON: the run state and each task state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from airflow.dag_processing.dagbag import DagBag

from bfs_reg_copilot.ingest import PoliteFetcher
from bfs_reg_copilot.ingest.pipeline import fetch_sources as real_fetch_sources

DAGS = Path(__file__).resolve().parents[1] / "dags"
PAGE = (
    b"<html><body><main><h1>T</h1>"
    + b"".join(b"<p>Paragraph %d has a few plain words in it.</p>" % i for i in range(100))
    + b"</main></body></html>"
)


def main(mode: str) -> None:
    bag = DagBag(dag_folder=str(DAGS))
    if bag.import_errors:
        raise SystemExit(f"DAG import errors: {bag.import_errors}")
    dag = bag.dags["regcopilot_ingest"]
    namespace = dag.task_dict["fetch_all"].python_callable.__globals__
    bad_path = urlsplit(str(namespace["REGISTER"].ingestible()[0].url)).path

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if mode == "fail" and request.url.path == bad_path:
            return httpx.Response(503)
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})

    def offline_fetch(register, source_ids, raw_dir):  # type: ignore[no-untyped-def]
        client = httpx.Client(transport=httpx.MockTransport(handler))
        fetcher = PoliteFetcher(register, client=client, sleep=lambda _seconds: None)
        return real_fetch_sources(register, source_ids, raw_dir, fetcher=fetcher)

    namespace["fetch_sources"] = offline_fetch
    run = dag.test()
    tasks = {f"{ti.task_id}[{ti.map_index}]": str(ti.state) for ti in run.get_task_instances()}
    print(json.dumps({"state": str(run.state), "tasks": tasks}))


if __name__ == "__main__":
    main(sys.argv[1])
