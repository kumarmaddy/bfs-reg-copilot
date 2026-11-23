"""Test doubles that stand in for a real pipeline, so the scorer can be tested first.

Each double behaves in one known way. If the scorer gives a double the wrong score, the scorer
is wrong. Their results are never system results; runs made with them are marked as such.
"""

from __future__ import annotations

from collections.abc import Callable

from bfs_reg_copilot.eval.gold import AdversarialItem, AnswerableItem, GoldSet, RefusalItem
from bfs_reg_copilot.eval.types import Pipeline, PipelineAnswer

_FILLER = "A-OSFI-E23:000000000000:s999:c000"  # a chunk that supports nothing
_REFUSAL = "The sources provided cannot answer this question."


class _Double:
    is_test_double = True
    name = "double"

    def __init__(self, gold: GoldSet) -> None:
        self._by_question = {item.question: item for item in gold.items}

    def describe(self) -> dict[str, str]:
        return {"kind": "test double"}


class OraclePipeline(_Double):
    """Knows the gold answers: states every key point, cites the support, refuses refusals."""

    name = "oracle"

    def answer(self, question: str) -> PipelineAnswer:
        item = self._by_question[question]
        if isinstance(item, AnswerableItem):
            return PipelineAnswer(
                text=" ".join(item.key_points),
                refused=False,
                cited_chunks=item.supporting_chunks,
                retrieved_chunks=(*item.supporting_chunks, _FILLER),
            )
        return PipelineAnswer(text=_REFUSAL, refused=True)


class AlwaysRefusePipeline(_Double):
    """Refuses everything: perfect on refusals, useless on answerable questions."""

    name = "refuse"

    def answer(self, question: str) -> PipelineAnswer:
        return PipelineAnswer(text=_REFUSAL, refused=True)


class UncitedPipeline(_Double):
    """Right text, no citations: must fail M1 whatever the text says."""

    name = "uncited"

    def answer(self, question: str) -> PipelineAnswer:
        item = self._by_question[question]
        if isinstance(item, AnswerableItem):
            return PipelineAnswer(
                text=" ".join(item.key_points),
                refused=False,
                retrieved_chunks=item.supporting_chunks,
            )
        return PipelineAnswer(text=_REFUSAL, refused=True)


class WrongCitationPipeline(_Double):
    """Retrieves and cites a section that does not hold the support."""

    name = "wrong-cite"

    def answer(self, question: str) -> PipelineAnswer:
        item = self._by_question[question]
        if isinstance(item, AnswerableItem):
            return PipelineAnswer(
                text=" ".join(item.key_points),
                refused=False,
                cited_chunks=(_FILLER,),
                retrieved_chunks=(_FILLER,),
            )
        return PipelineAnswer(text=_REFUSAL, refused=True)


class FabricatingPipeline(_Double):
    """Never refuses, and cites a real supporting section it did not retrieve."""

    name = "fabricating"

    def answer(self, question: str) -> PipelineAnswer:
        item = self._by_question[question]
        if isinstance(item, AnswerableItem):
            return PipelineAnswer(
                text=" ".join(item.key_points),
                refused=False,
                cited_chunks=item.supporting_chunks,
                retrieved_chunks=(_FILLER,),
            )
        if isinstance(item, RefusalItem | AdversarialItem):
            return PipelineAnswer(text="Here is an answer anyway.", refused=False)
        raise AssertionError("unreachable")


DOUBLES: dict[str, Callable[[GoldSet], Pipeline]] = {
    "oracle": OraclePipeline,
    "refuse": AlwaysRefusePipeline,
    "uncited": UncitedPipeline,
    "wrong-cite": WrongCitationPipeline,
    "fabricating": FabricatingPipeline,
}
