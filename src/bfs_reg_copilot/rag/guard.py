"""The output guard: checks an answer after the model wrote it, before anyone relies on it.

Two deterministic checks, no model and no network:

1. **Uncited.** A non-refusal must cite at least one chunk that was really retrieved. Otherwise
   nothing it says can be verified, so it is withheld.
2. **Instruction leak.** An answer that repeats a run of eight consecutive words from any prompt
   version's rules is withheld. The baseline's rule 5 asks the model not to reveal its rules;
   this checks that it did not, whatever the model says about itself.

A withheld answer becomes a refusal with a fixed sentence and a reason in `PipelineAnswer.guard`,
so the caller never sees the original text, and a run can count what was blocked and why. The
guard is off unless asked for (`eval run --guard`), because the baseline is the measured starting
point and every safeguard is judged against it (ADR-0018 and the output-guard ADR).

This is a net under the model, not a security boundary. It does not judge whether an answer is
true (that is faithfulness, M6) and it cannot see an instruction leaked in other words.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol

from bfs_reg_copilot.eval.types import GUARD_LEAK, GUARD_UNCITED, PipelineAnswer
from bfs_reg_copilot.gateway.types import Usage
from bfs_reg_copilot.rag.output import MALFORMED
from bfs_reg_copilot.rag.prompt import SYSTEMS

GUARD_VERSION: Final = "v1"
LEAK_WORDS: Final = 8  # in 329 stored answers this flags the one real leak and nothing else
UNCITED: Final = GUARD_UNCITED
LEAK: Final = GUARD_LEAK
UNCITED_TEXT: Final = "This answer was withheld because it could not be tied to a retrieved source."
LEAK_TEXT: Final = "This answer was withheld because it repeated the assistant's own instructions."

_WORD = re.compile(r"[a-z0-9]+")
Run = tuple[str, ...]


def word_runs(text: str, size: int = LEAK_WORDS) -> frozenset[Run]:
    """Every run of `size` consecutive words, lower-cased, ignoring punctuation and spacing."""
    words = _WORD.findall(text.lower())
    return frozenset(tuple(words[i : i + size]) for i in range(len(words) - size + 1))


def instruction_runs(texts: Iterable[str] | None = None, size: int = LEAK_WORDS) -> frozenset[Run]:
    """The runs that must not appear in an answer: by default the rules of every prompt version."""
    runs: set[Run] = set()
    for text in SYSTEMS.values() if texts is None else texts:
        runs |= word_runs(text, size)
    return frozenset(runs)


def repeats_instructions(text: str, runs: frozenset[Run], size: int = LEAK_WORDS) -> bool:
    return not runs.isdisjoint(word_runs(text, size))


def has_verified_citation(answer: PipelineAnswer) -> bool:
    """At least one cited chunk is one the model was actually given. A made-up handle is mapped to
    an `UNKNOWN:` id that is never in the retrieved list, so it cannot count."""
    retrieved = set(answer.retrieved_chunks)
    return any(chunk_id in retrieved for chunk_id in answer.cited_chunks)


def check(answer: PipelineAnswer, runs: frozenset[Run]) -> str:
    """Why the answer must be withheld (`LEAK`, `UNCITED`), or an empty string if it may pass."""
    if answer.text.startswith(MALFORMED):
        return ""  # unusable output is already a failed answer and is counted by the pipeline
    if repeats_instructions(answer.text, runs):
        return LEAK
    if not answer.refused and not has_verified_citation(answer):
        return UNCITED
    return ""


def withhold(answer: PipelineAnswer, reason: str) -> PipelineAnswer:
    """The refusal that replaces a blocked answer. Its citations are dropped with its text."""
    text = LEAK_TEXT if reason == LEAK else UNCITED_TEXT
    return PipelineAnswer(
        text=text, refused=True, retrieved_chunks=answer.retrieved_chunks, guard=reason
    )


@dataclass
class GuardCounts:
    uncited: int = 0
    instruction_leak: int = 0

    @property
    def blocked(self) -> int:
        return self.uncited + self.instruction_leak


class _Inner(Protocol):
    name: str
    is_test_double: bool
    malformed: int

    @property
    def usage(self) -> Usage: ...

    def check_ready(self) -> None: ...

    def describe(self) -> dict[str, str]: ...

    def answer(self, question: str) -> PipelineAnswer: ...


class GuardedPipeline:
    """Wraps a pipeline and applies the guard to every answer. Same name, so run folders and
    comparisons line up with the unguarded run; the settings say `guard` was on."""

    def __init__(self, inner: _Inner, runs: frozenset[Run] | None = None) -> None:
        self._inner = inner
        self._runs = instruction_runs() if runs is None else runs
        self.counts = GuardCounts()
        self.name = inner.name
        self.is_test_double = inner.is_test_double

    @property
    def malformed(self) -> int:
        return self._inner.malformed

    @property
    def usage(self) -> Usage:
        return self._inner.usage

    def check_ready(self) -> None:
        self._inner.check_ready()

    def describe(self) -> dict[str, str]:
        return {
            **self._inner.describe(),
            "guard": GUARD_VERSION,
            "guard_leak_words": str(LEAK_WORDS),
        }

    def answer(self, question: str) -> PipelineAnswer:
        answer = self._inner.answer(question)
        reason = check(answer, self._runs)
        if not reason:
            return answer
        if reason == LEAK:
            self.counts.instruction_leak += 1
        else:
            self.counts.uncited += 1
        return withhold(answer, reason)
