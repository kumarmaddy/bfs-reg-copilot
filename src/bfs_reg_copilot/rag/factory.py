"""Assemble the real baseline pipeline from the local database and local models."""

from __future__ import annotations

from bfs_reg_copilot.embed.models import BGE_M3
from bfs_reg_copilot.embed.ollama import OllamaEmbedder
from bfs_reg_copilot.gateway.ollama import OllamaGateway
from bfs_reg_copilot.rag.pipeline import DbChunkSource, RagPipeline
from bfs_reg_copilot.rag.prompt import PROMPT_VERSION
from bfs_reg_copilot.retrieve.retrievers import DenseRetriever
from bfs_reg_copilot.store.db import Conn
from bfs_reg_copilot.store.loader import corpus_fingerprint

DEFAULT_GENERATOR = "qwen2.5:7b"


def build_baseline(
    conn: Conn,
    model: str = DEFAULT_GENERATOR,
    k: int = 5,
    prompt_version: str = PROMPT_VERSION,
) -> RagPipeline:
    embedder = OllamaEmbedder(BGE_M3)
    retriever = DenseRetriever(conn, embedder)
    # Recorded with every run so a re-pulled model or a re-loaded corpus cannot go unnoticed.
    provenance = {
        "embedding_model": BGE_M3.name,
        "embedding_model_digest": embedder.model_digest(),
        "corpus_fingerprint": corpus_fingerprint(conn),
    }
    return RagPipeline(
        retriever, DbChunkSource(conn), OllamaGateway(model), k, provenance, prompt_version
    )
