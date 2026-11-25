"""The API's request and response shapes. Citations carry their lineage (metric M9)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

MAX_QUESTION_CHARS = 2000

Outcome = Literal["answered", "refused", "uncited"]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS)
    ]


class Citation(BaseModel):
    """Where a cited passage came from, precisely enough to find it again."""

    chunk_id: str
    source_id: str
    section_path: list[str]
    page_title: str
    url: str
    retrieved_at: datetime
    date_modified: str | None  # the publisher's own page date, when the page states one
    raw_sha256: str  # fingerprint of the exact page version that was retrieved


class AskResponse(BaseModel):
    request_id: str
    outcome: Outcome
    answer: str
    citations: list[Citation]
    # Citations the model gave that do not match any retrieved passage. They are not shown.
    unverified_citations: int
    latency_ms: int


class ErrorResponse(BaseModel):
    request_id: str
    error: Literal["busy", "dependency_unavailable", "unusable_output", "internal"]
    detail: str
