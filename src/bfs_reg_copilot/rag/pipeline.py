"""The baseline pipeline: retrieve, build the prompt, call the model, check the reply.

No tuning and no safeguards beyond the prompt: this is the measured starting point. Everything
added later (a score floor for refusals, reranking, citation repair) is judged against it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bfs_reg_copilot.eval.types import PipelineAnswer
from bfs_reg_copilot.gateway.types import LLMGateway, Usage
from bfs_reg_copilot.rag.output import answer_schema, to_pipeline_answer
from bfs_reg_copilot.rag.prompt import PROMPT_VERSION, ContextChunk, build_messages
from bfs_reg_copilot.retrieve.types import Retriever
from bfs_reg_copilot.store.db import Conn

DEFAULT_K = 5
MAX_ANSWER_TOKENS = 512


class ChunkSource(Protocol):
    def fetch(self, chunk_ids: Sequence[str]) -> list[ContextChunk]:
        """The chunks for these ids, in the same order; ids that no longer exist are skipped."""
        ...


class DbChunkSource:
    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def fetch(self, chunk_ids: Sequence[str]) -> list[ContextChunk]:
        if not chunk_ids:
            return []
        cur = self._conn.cursor()
        cur.execute(
            "SELECT chunk_id, section_path, text FROM chunks WHERE chunk_id = ANY(%s)",
            (list(chunk_ids),),
        )
        found = {str(i): ContextChunk(str(i), tuple(p), str(t)) for i, p, t in cur.fetchall()}
        self._conn.rollback()  # end the read transaction; this object only reads
        return [found[i] for i in chunk_ids if i in found]


class RagPipeline:
    name = "baseline"

    def __init__(
        self,
        retriever: Retriever,
        chunks: ChunkSource,
        gateway: LLMGateway,
        k: int = DEFAULT_K,
    ) -> None:
        self._retriever = retriever
        self._chunks = chunks
        self._gateway = gateway
        self._k = k
        self.is_test_double = retriever.is_test_double or gateway.is_test_double
        self.malformed = 0

    @property
    def usage(self) -> Usage:
        return self._gateway.usage

    def check_ready(self) -> None:
        self._gateway.check_ready()

    def describe(self) -> dict[str, str]:
        return {
            **self._gateway.describe(),
            "retriever": self._retriever.name,
            "k": str(self._k),
            "prompt_version": PROMPT_VERSION,
            "max_answer_tokens": str(MAX_ANSWER_TOKENS),
        }

    def answer(self, question: str) -> PipelineAnswer:
        hits = self._retriever.retrieve(question, self._k)
        context = self._chunks.fetch([h.chunk_id for h in hits])
        completion = self._gateway.complete(
            build_messages(question, context),
            schema=answer_schema(),
            max_tokens=MAX_ANSWER_TOKENS,
        )
        answer, malformed = to_pipeline_answer(completion.text, context)
        self.malformed += malformed
        return answer
