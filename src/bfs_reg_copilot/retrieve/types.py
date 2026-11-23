"""What every retriever returns, so the generator and the evaluator do not care which one ran."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    score: float  # meaning depends on the retriever; only the order is comparable across them


class Retriever(Protocol):
    name: str
    is_test_double: bool

    def retrieve(self, question: str, k: int) -> list[Hit]:
        """The k best chunks for the question, best first. Only current chunks."""
        ...
