"""Assemble the real baseline pipeline from the local database and local models."""

from __future__ import annotations

from bfs_reg_copilot.embed.models import BGE_M3
from bfs_reg_copilot.embed.ollama import OllamaEmbedder
from bfs_reg_copilot.gateway.ollama import OllamaGateway
from bfs_reg_copilot.rag.pipeline import DbChunkSource, RagPipeline
from bfs_reg_copilot.retrieve.retrievers import DenseRetriever
from bfs_reg_copilot.store.db import Conn

DEFAULT_GENERATOR = "qwen2.5:7b"


def build_baseline(conn: Conn, model: str = DEFAULT_GENERATOR, k: int = 5) -> RagPipeline:
    retriever = DenseRetriever(conn, OllamaEmbedder(BGE_M3))
    return RagPipeline(retriever, DbChunkSource(conn), OllamaGateway(model), k)
