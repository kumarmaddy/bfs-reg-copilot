"""Embeddings from a local Ollama server (POST /api/embed). Nothing leaves the machine."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, Final, Protocol

import httpx

from bfs_reg_copilot.embed.models import EmbeddingModel

DEFAULT_HOST: Final = "http://127.0.0.1:11434"


class EmbedError(Exception):
    pass


class Embedder(Protocol):
    model: EmbeddingModel
    is_test_double: bool

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]: ...


def ollama_host() -> str:
    host = os.environ.get("OLLAMA_HOST", DEFAULT_HOST)
    return host if host.startswith("http") else f"http://{host}"


class OllamaEmbedder:
    is_test_double = False

    def __init__(
        self, model: EmbeddingModel, host: str | None = None, client: httpx.Client | None = None
    ) -> None:
        self.model = model
        self._url = (host or ollama_host()).rstrip("/") + "/api/embed"
        self._client = client or httpx.Client(timeout=300.0)

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.post(
                self._url, json={"model": self.model.name, "input": list(texts), "truncate": False}
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbedError(f"embedding request to {self._url} failed: {exc}") from exc
        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbedError(
                f"expected {len(texts)} embeddings, got {body.get('embeddings')!r:.80}"
            )
        for vector in vectors:
            if len(vector) != self.model.dims:
                raise EmbedError(
                    f"{self.model.name} returned {len(vector)} dimensions, "
                    f"expected {self.model.dims}"
                )
        return [[float(x) for x in v] for v in vectors]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]:
        return self._embed([self.model.query_format(q) for q in queries])
