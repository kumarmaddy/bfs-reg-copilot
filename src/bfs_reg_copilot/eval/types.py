"""What a pipeline returns and what a run records. The harness only needs this contract."""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from bfs_reg_copilot.eval.gold import Split

# Why the output guard withheld an answer (`PipelineAnswer.guard`). Defined here so the report
# can count them without depending on the generator.
GUARD_UNCITED: Final = "uncited"
GUARD_LEAK: Final = "instruction_leak"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PipelineAnswer(_Frozen):
    """One answer. `retrieved_chunks` is ranked, best first; `cited_chunks` are chunk ids.
    `guard` is empty unless the output guard withheld the model's answer, then it says why."""

    text: str
    refused: bool
    cited_chunks: tuple[str, ...] = ()
    retrieved_chunks: tuple[str, ...] = ()
    guard: str = ""


class Pipeline(Protocol):
    """Anything that can answer a question. Real pipelines arrive in later slices."""

    name: str
    is_test_double: bool

    def describe(self) -> dict[str, str]:
        """Settings worth recording with a run (models, k, prompt version, ...)."""
        ...

    def answer(self, question: str) -> PipelineAnswer: ...


class RunRecord(_Frozen):
    item_id: str
    kind: Literal["answerable", "refusal", "adversarial"]
    split: Split
    question: str
    answer: PipelineAnswer | None
    error: str = ""
    latency_s: float


class RunMeta(_Frozen):
    run_id: str
    started_at: datetime
    finished_at: datetime
    split: Split
    pipeline: str
    is_test_double: bool
    settings: dict[str, str]
    gold_sha256: str
    gold_version: int
    git_commit: str
    n_items: int
    skipped: tuple[str, ...] = ()
