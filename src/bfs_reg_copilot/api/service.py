"""Turns a question into an API result: runs the pipeline, then resolves citations to lineage.

One request at a time. The baseline holds a single database connection and a single local model,
and neither is safe to share between threads, so requests queue on a lock and give up after a
timeout instead of piling up. Throughput is a Phase 4 concern (metric M3).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from bfs_reg_copilot.api.schemas import Citation, Outcome
from bfs_reg_copilot.eval.types import PipelineAnswer
from bfs_reg_copilot.rag.output import MALFORMED, UNKNOWN

log = logging.getLogger("bfs_reg_copilot.api")


class ServiceError(Exception):
    """A failure the API reports with a fixed, safe message. Never carries internals."""

    def __init__(self, kind: str, status: int, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.status = status
        self.detail = detail


class AnsweringPipeline(Protocol):
    def answer(self, question: str) -> PipelineAnswer: ...
    def check_ready(self) -> None: ...


class ProvenanceSource(Protocol):
    def lookup(self, chunk_ids: Sequence[str]) -> dict[str, Citation]:
        """Lineage for the ids that exist; ids that do not exist are left out."""
        ...


@dataclass
class Backend:
    """Everything one request needs. Rebuilt after a dependency failure (a dropped connection)."""

    pipeline: AnsweringPipeline
    provenance: ProvenanceSource
    close: Callable[[], None]


@dataclass(frozen=True)
class AskResult:
    outcome: Outcome
    answer: str
    citations: list[Citation]
    unverified: int


# What a caller sees when the model's reply could not be used. The raw reply is never returned.
_UNUSABLE = "The model's reply could not be used. Try again or rephrase the question."


class AnswerService:
    def __init__(
        self,
        factory: Callable[[], Backend],
        dependency_errors: tuple[type[Exception], ...],
        lock_timeout_s: float = 60.0,
    ) -> None:
        self._factory = factory
        self._dependency_errors = dependency_errors
        self._lock_timeout_s = lock_timeout_s
        self._lock = threading.Lock()
        self._backend: Backend | None = None

    def _acquire(self) -> None:
        if not self._lock.acquire(timeout=self._lock_timeout_s):
            raise ServiceError("busy", 503, "The service is handling another question. Try again.")

    def _backend_or_build(self) -> Backend:
        if self._backend is None:
            self._backend = self._factory()
        return self._backend

    def _reset(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            try:
                backend.close()
            except Exception:
                log.warning("closing a failed backend raised", exc_info=True)

    def close(self) -> None:
        with self._lock:
            self._reset()

    def ready(self) -> None:
        """Raises ServiceError(503) unless the database and the model are reachable."""
        self._acquire()
        try:
            self._backend_or_build().pipeline.check_ready()
        except self._dependency_errors as exc:
            self._reset()
            log.warning("not ready: %s", type(exc).__name__)
            raise ServiceError(
                "dependency_unavailable", 503, "A dependency is unavailable."
            ) from exc
        finally:
            self._lock.release()

    def ask(self, question: str) -> AskResult:
        self._acquire()
        try:
            backend = self._backend_or_build()
            answer = backend.pipeline.answer(question)
            return self._to_result(answer, backend.provenance)
        except self._dependency_errors as exc:
            self._reset()  # the next request starts from a fresh connection
            log.warning("dependency failed: %s", type(exc).__name__)
            raise ServiceError(
                "dependency_unavailable", 503, "A dependency is unavailable."
            ) from exc
        finally:
            self._lock.release()

    @staticmethod
    def _to_result(answer: PipelineAnswer, provenance: ProvenanceSource) -> AskResult:
        if answer.text.startswith(MALFORMED):
            raise ServiceError("unusable_output", 502, _UNUSABLE)
        if answer.refused:
            return AskResult("refused", answer.text, [], 0)
        real = [c for c in answer.cited_chunks if not c.startswith(UNKNOWN)]
        found = provenance.lookup(real)
        citations = [found[c] for c in real if c in found]
        unverified = len(answer.cited_chunks) - len(citations)
        outcome: Outcome = "answered" if citations else "uncited"
        return AskResult(outcome, answer.text, citations, unverified)


def timed(fn: Callable[[], AskResult]) -> tuple[AskResult, int]:
    start = time.monotonic()
    result = fn()
    return result, int((time.monotonic() - start) * 1000)
