"""The API layer, tested with a fake pipeline: no database, no model, no network."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bfs_reg_copilot.api.__main__ import EXIT_REFUSED, is_loopback, main
from bfs_reg_copilot.api.app import create_app
from bfs_reg_copilot.api.backend import DbProvenanceSource
from bfs_reg_copilot.api.schemas import MAX_QUESTION_CHARS, Citation
from bfs_reg_copilot.api.service import AnswerService, Backend
from bfs_reg_copilot.eval.types import PipelineAnswer
from bfs_reg_copilot.gateway.types import GatewayError
from bfs_reg_copilot.ingest.chunk_store import write_chunks
from bfs_reg_copilot.rag.output import MALFORMED, UNKNOWN
from bfs_reg_copilot.store.db import Conn
from bfs_reg_copilot.store.loader import load_source
from dbhelpers import make_chunk, needs_db

CHUNK_A = "A-OSFI-E23:aaaaaaaaaaaa:s001:c001"
CHUNK_B = "A-OSFI-E23:aaaaaaaaaaaa:s002:c001"
SECRET_QUESTION = "Does Acme Bank account 12345 breach E-23?"  # noqa: S105


def _citation(chunk_id: str) -> Citation:
    return Citation(
        chunk_id=chunk_id,
        source_id="A-OSFI-E23",
        section_path=["E-23", "Scope"],
        page_title="Guideline E-23",
        url="https://example.test/e23",
        retrieved_at=datetime(2026, 11, 1, tzinfo=UTC),
        date_modified="2025-09-11",
        raw_sha256="a" * 64,
    )


class FakeProvenance:
    def __init__(self, known: Sequence[str]) -> None:
        self._known = set(known)

    def lookup(self, chunk_ids: Sequence[str]) -> dict[str, Citation]:
        return {c: _citation(c) for c in chunk_ids if c in self._known}


class FakePipeline:
    def __init__(self, answer: PipelineAnswer | Exception) -> None:
        self.result = answer
        self.asked: list[str] = []
        self.gate: threading.Event | None = None
        self.entered = threading.Event()
        self.ready_error: Exception | None = None

    def answer(self, question: str) -> PipelineAnswer:
        self.asked.append(question)
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def check_ready(self) -> None:
        if self.ready_error is not None:
            raise self.ready_error


def _answer(
    text: str = "An answer.", cited: Sequence[str] = (CHUNK_A,), refused: bool = False
) -> PipelineAnswer:
    return PipelineAnswer(
        text=text, refused=refused, cited_chunks=tuple(cited), retrieved_chunks=(CHUNK_A, CHUNK_B)
    )


class Harness:
    def __init__(self, pipeline: FakePipeline, known: Sequence[str], lock_timeout_s: float = 5.0):
        self.pipeline = pipeline
        self.builds = 0
        self.closes = 0

        def factory() -> Backend:
            self.builds += 1
            return Backend(pipeline, FakeProvenance(known), self._close)

        self.service = AnswerService(factory, (GatewayError,), lock_timeout_s=lock_timeout_s)
        self.client = TestClient(create_app(self.service), raise_server_exceptions=False)

    def _close(self) -> None:
        self.closes += 1


def _harness(
    answer: PipelineAnswer | Exception, known: Sequence[str] = (CHUNK_A, CHUNK_B)
) -> Harness:
    return Harness(FakePipeline(answer), known)


def test_a_cited_answer_carries_lineage() -> None:
    h = _harness(_answer())
    body = h.client.post("/ask", json={"question": "When does E-23 apply?"}).json()
    assert body["outcome"] == "answered"
    assert body["unverified_citations"] == 0
    (citation,) = body["citations"]
    assert citation["chunk_id"] == CHUNK_A
    assert citation["raw_sha256"] == "a" * 64
    assert citation["retrieved_at"].startswith("2026-11-01")
    assert citation["date_modified"] == "2025-09-11"


def test_a_refusal_has_no_citations() -> None:
    h = _harness(_answer("The sources do not say.", cited=(), refused=True))
    body = h.client.post("/ask", json={"question": "q"}).json()
    assert (body["outcome"], body["citations"]) == ("refused", [])


def test_invented_citations_are_dropped_and_counted() -> None:
    h = _harness(_answer(cited=(CHUNK_A, f"{UNKNOWN}S9", CHUNK_B)), known=(CHUNK_A,))
    body = h.client.post("/ask", json={"question": "q"}).json()
    assert [c["chunk_id"] for c in body["citations"]] == [CHUNK_A]
    assert body["unverified_citations"] == 2  # one invented handle, one id the database lacks
    assert body["outcome"] == "answered"


def test_an_answer_with_no_usable_citation_is_flagged_uncited() -> None:
    h = _harness(_answer(cited=(f"{UNKNOWN}S9",)))
    body = h.client.post("/ask", json={"question": "q"}).json()
    assert body["outcome"] == "uncited"
    assert body["citations"] == []


def test_malformed_model_output_is_a_502_and_the_raw_reply_is_not_returned() -> None:
    h = _harness(PipelineAnswer(text=MALFORMED + "garbage the model wrote", refused=False))
    response = h.client.post("/ask", json={"question": "q"})
    assert response.status_code == 502
    assert response.json()["error"] == "unusable_output"
    assert "garbage" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "x" * (MAX_QUESTION_CHARS + 1)},
        {"question": "q", "k": 50},  # extra fields are refused, not ignored
        {"question": 5},
    ],
)
def test_bad_requests_are_422_and_never_reach_the_pipeline(payload: dict[str, object]) -> None:
    h = _harness(_answer())
    assert h.client.post("/ask", json=payload).status_code == 422
    assert h.pipeline.asked == []


def test_the_question_is_trimmed() -> None:
    h = _harness(_answer())
    h.client.post("/ask", json={"question": "  hello  "})
    assert h.pipeline.asked == ["hello"]


def test_dependency_failure_is_503_with_no_internals_and_the_next_call_rebuilds() -> None:
    h = _harness(GatewayError("cannot reach Ollama at http://127.0.0.1:11434: secret detail"))
    response = h.client.post("/ask", json={"question": "q"})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert "secret" not in response.text
    assert "11434" not in response.text
    assert response.json()["error"] == "dependency_unavailable"
    assert (h.builds, h.closes) == (1, 1)
    h.pipeline.result = _answer()
    assert h.client.post("/ask", json={"question": "q"}).status_code == 200
    assert h.builds == 2  # a fresh backend, so a dropped connection heals itself


def test_a_bug_in_our_own_code_is_a_500_not_a_retry_hint() -> None:
    h = _harness(RuntimeError("boom with /internal/path"))
    response = h.client.post("/ask", json={"question": "q"})
    assert response.status_code == 500
    assert response.json()["error"] == "internal"
    assert "boom" not in response.text


def test_a_second_caller_gets_503_busy_instead_of_queueing_forever() -> None:
    pipeline = FakePipeline(_answer())
    pipeline.gate = threading.Event()
    h = Harness(pipeline, (CHUNK_A,), lock_timeout_s=0.05)
    first: list[int] = []
    worker = threading.Thread(
        target=lambda: first.append(h.client.post("/ask", json={"question": "q"}).status_code)
    )
    worker.start()
    assert pipeline.entered.wait(timeout=5)
    second = h.client.post("/ask", json={"question": "q2"})
    assert second.status_code == 503
    assert second.json()["error"] == "busy"
    pipeline.gate.set()
    worker.join(timeout=5)
    assert first == [200]


def test_health_does_not_touch_dependencies() -> None:
    h = _harness(_answer())
    assert h.client.get("/health").json() == {"status": "ok"}
    assert h.builds == 0


def test_ready_reflects_the_dependencies() -> None:
    h = _harness(_answer())
    assert h.client.get("/ready").status_code == 200
    h.pipeline.ready_error = GatewayError("model not installed")
    response = h.client.get("/ready")
    assert response.status_code == 503
    assert "model not installed" not in response.text


def test_request_ids_are_generated_not_taken_from_the_client() -> None:
    h = _harness(_answer())
    response = h.client.post(
        "/ask", json={"question": "q"}, headers={"X-Request-ID": "forged\nlog line"}
    )
    request_id = response.json()["request_id"]
    assert request_id != "forged\nlog line"
    assert response.headers["X-Request-ID"] == request_id
    assert len(request_id) == 32


def test_logs_never_contain_the_question(caplog: pytest.LogCaptureFixture) -> None:
    h = _harness(_answer())
    with caplog.at_level(logging.INFO, logger="bfs_reg_copilot.api"):
        h.client.post("/ask", json={"question": SECRET_QUESTION})
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "outcome=answered" in text
    assert f"question_chars={len(SECRET_QUESTION)}" in text
    assert "Acme" not in text
    assert "12345" not in text


def test_the_server_refuses_a_non_local_address_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--host", "0.0.0.0"]) == EXIT_REFUSED  # noqa: S104
    assert "no authentication" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("host", "local"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("0.0.0.0", False),  # noqa: S104
        ("10.0.0.5", False),
    ],
)
def test_loopback_detection(host: str, local: bool) -> None:
    assert is_loopback(host) is local


# --- database needed ---------------------------------------------------------------------------


@needs_db
def test_db_provenance_returns_lineage_for_existing_ids_only(
    migrated: Conn, tmp_path: Path
) -> None:
    chunk = make_chunk(source="A-TEST", n=1)
    load_source(migrated, "A-TEST", write_chunks(tmp_path, (chunk,), "1"))
    found = DbProvenanceSource(migrated).lookup([chunk.chunk_id, "A-TEST:nope:s001:c001"])
    assert set(found) == {chunk.chunk_id}
    citation = found[chunk.chunk_id]
    assert citation.raw_sha256 == chunk.raw_sha256
    assert citation.url == chunk.final_url
    assert citation.section_path == list(chunk.section_path)
    assert citation.retrieved_at == chunk.retrieved_at
    assert DbProvenanceSource(migrated).lookup([]) == {}
