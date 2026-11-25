"""The HTTP layer. Thin on purpose: validation, request ids, error shapes and logging only."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bfs_reg_copilot.api.schemas import AskRequest, AskResponse, ErrorResponse
from bfs_reg_copilot.api.service import AnswerService, ServiceError, timed

log = logging.getLogger("bfs_reg_copilot.api")


def _error(request_id: str, status: int, kind: str, detail: str) -> JSONResponse:
    body = ErrorResponse.model_validate({"request_id": request_id, "error": kind, "detail": detail})
    headers = {"X-Request-ID": request_id}
    if status == 503:
        headers["Retry-After"] = "5"
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def create_app(service: AnswerService) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        service.close()

    app = FastAPI(
        title="BFS regulatory copilot",
        version="0.1.0",
        description=(
            "Baseline research assistant over public Canadian financial-regulation sources. "
            "Answers are model output: check them against the cited passage."
        ),
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness only: the process is up. Does not touch the database or the model."""
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> JSONResponse:
        """Readiness: the database and the model can be reached."""
        request_id = uuid.uuid4().hex
        try:
            service.ready()
        except ServiceError as exc:
            return _error(request_id, exc.status, exc.kind, exc.detail)
        return JSONResponse({"status": "ready"})

    @app.post("/ask", response_model=AskResponse, responses={502: {"model": ErrorResponse}})
    def ask(body: AskRequest) -> JSONResponse:
        # The id is always generated here; a client-supplied one could forge log lines.
        request_id = uuid.uuid4().hex
        try:
            result, latency_ms = timed(lambda: service.ask(body.question))
        except ServiceError as exc:
            log.info("ask request_id=%s error=%s", request_id, exc.kind)
            return _error(request_id, exc.status, exc.kind, exc.detail)
        except Exception:
            log.exception("ask request_id=%s unexpected failure", request_id)
            return _error(request_id, 500, "internal", "Unexpected error.")
        # The question text is deliberately not logged: questions can hold client details.
        log.info(
            "ask request_id=%s outcome=%s citations=%d unverified=%d latency_ms=%d "
            "question_chars=%d",
            request_id,
            result.outcome,
            len(result.citations),
            result.unverified,
            latency_ms,
            len(body.question),
        )
        response = AskResponse(
            request_id=request_id,
            outcome=result.outcome,
            answer=result.answer,
            citations=result.citations,
            unverified_citations=result.unverified,
            latency_ms=latency_ms,
        )
        return JSONResponse(response.model_dump(mode="json"), headers={"X-Request-ID": request_id})

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = uuid.uuid4().hex
        log.error("unhandled %s request_id=%s", type(exc).__name__, request_id)
        return _error(request_id, 500, "internal", "Unexpected error.")

    return app
