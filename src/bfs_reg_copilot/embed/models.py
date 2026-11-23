"""The embedding models we can use, and how each wants its text formatted.

Documents are embedded as `heading path + newline + text` (`Chunk.contextualised`), so a chunk
about "Scope" still carries the name of its guideline. Only some models want an instruction in
front of the *query*; getting this wrong quietly lowers retrieval quality, so it lives here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from bfs_reg_copilot.store.db import EMBEDDING_DIMS

QWEN3_TASK: Final = "Given a regulatory question, retrieve the passages that answer it"


@dataclass(frozen=True)
class EmbeddingModel:
    name: str  # the Ollama model name; also the `model` key in chunk_embeddings
    dims: int
    query_format: Callable[[str], str]


def _plain(query: str) -> str:
    return query


def _qwen3_query(query: str) -> str:
    # Qwen3-Embedding's documented query format; documents get no instruction (unverified here:
    # the model card is the source, and the comparison below is the real test).
    return f"Instruct: {QWEN3_TASK}\nQuery: {query}"


BGE_M3: Final = EmbeddingModel("bge-m3", EMBEDDING_DIMS, _plain)
QWEN3_06B: Final = EmbeddingModel("qwen3-embedding:0.6b", EMBEDDING_DIMS, _qwen3_query)

MODELS: Final = {m.name: m for m in (BGE_M3, QWEN3_06B)}


def get_model(name: str) -> EmbeddingModel:
    if name not in MODELS:
        raise KeyError(f"unknown embedding model {name!r}; known: {', '.join(sorted(MODELS))}")
    return MODELS[name]


def document_text(section_path: tuple[str, ...] | list[str], text: str) -> str:
    """Same shape as Chunk.contextualised(), rebuilt from database columns."""
    return " > ".join(section_path) + "\n" + text
