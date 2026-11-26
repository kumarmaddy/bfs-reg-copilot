"""An upper-bound probe, not a retriever to ship: give the generator the gold supporting chunks.

If the generator still fails when the right chunks are in front of it, better retrieval or a
reranker cannot help that question. Gold chunks come first, then the normal retriever's hits fill
the context up to k (never fewer than every gold chunk). The order favours the model, so a result
here is a ceiling, not a forecast. Dev questions only (ADR-0014: the hold-out gold is never used
to build a context).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bfs_reg_copilot.eval.gold import AnswerableItem, GoldSet, Split
from bfs_reg_copilot.retrieve.types import Hit, Retriever


def gold_context_map(gold: GoldSet) -> dict[str, tuple[str, ...]]:
    """Question text -> its gold supporting chunk ids, for dev answerable items."""
    return {
        i.question: tuple(i.supporting_chunks)
        for i in gold.items
        if isinstance(i, AnswerableItem) and i.split == Split.DEV
    }


class GoldContextRetriever:
    def __init__(self, inner: Retriever, wanted: Mapping[str, Sequence[str]]) -> None:
        self._inner = inner
        self._wanted = wanted
        self.name = f"gold-context+{inner.name}"
        self.is_test_double = inner.is_test_double

    def retrieve(self, question: str, k: int) -> list[Hit]:
        gold_ids = list(dict.fromkeys(self._wanted.get(question, ())))
        if not gold_ids:
            return self._inner.retrieve(question, k)
        fill = [
            h
            for h in self._inner.retrieve(question, k + len(gold_ids))
            if h.chunk_id not in gold_ids
        ]
        hits = [Hit(c, 1.0) for c in gold_ids]
        return hits + fill[: max(0, k - len(gold_ids))]
