"""The structured answer the model must return, and how it is mapped back to chunk ids."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, ValidationError

from bfs_reg_copilot.eval.types import PipelineAnswer
from bfs_reg_copilot.rag.prompt import ContextChunk, handle

MALFORMED: Final = "[malformed model output] "
UNKNOWN: Final = "UNKNOWN:"


class ModelAnswer(BaseModel):
    """Field order matters: the model writes the answer before it lists what it relied on."""

    model_config = ConfigDict(extra="forbid")

    refused: bool
    answer: str
    citations: list[str]


def answer_schema() -> dict[str, Any]:
    return ModelAnswer.model_json_schema()


def _normalise(raw: str) -> str:
    return raw.strip().strip("[]()<>\"' ").upper()


def to_pipeline_answer(raw: str, chunks: Sequence[ContextChunk]) -> tuple[PipelineAnswer, bool]:
    """(answer, was_malformed). Unusable output is a failed answer, not an exception: it must count
    against the system in the metrics, and one bad reply must not stop a run."""
    retrieved = tuple(c.chunk_id for c in chunks)
    try:
        parsed = ModelAnswer.model_validate_json(raw)
    except ValidationError:
        text = MALFORMED + " ".join(raw.split())[:400]
        return PipelineAnswer(text=text, refused=False, retrieved_chunks=retrieved), True
    if parsed.refused:
        return PipelineAnswer(text=parsed.answer, refused=True, retrieved_chunks=retrieved), False
    by_handle = {handle(i): c.chunk_id for i, c in enumerate(chunks, start=1)}
    cited: list[str] = []
    for citation in parsed.citations:
        chunk_id = by_handle.get(_normalise(citation), f"{UNKNOWN}{citation.strip()[:40]}")
        if chunk_id not in cited:
            cited.append(chunk_id)
    return (
        PipelineAnswer(
            text=parsed.answer, refused=False, cited_chunks=tuple(cited), retrieved_chunks=retrieved
        ),
        False,
    )
