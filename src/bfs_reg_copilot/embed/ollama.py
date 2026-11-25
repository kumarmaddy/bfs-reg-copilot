"""Embeddings from a local Ollama server (POST /api/embed). Nothing leaves the machine."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
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
        self,
        model: EmbeddingModel,
        host: str | None = None,
        client: httpx.Client | None = None,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._retries = retries
        self._sleep = sleep
        self._host = (host or ollama_host()).rstrip("/")
        self._digest: str | None = None
        self._url = (host or ollama_host()).rstrip("/") + "/api/embed"
        self._client = client or httpx.Client(timeout=300.0)

    def model_digest(self) -> str:
        """The exact embedding model build (first 12 characters), so a run can be tied to it.
        'unknown' if Ollama will not say. Looked up once."""
        if self._digest is None:
            try:
                response = self._client.get(f"{self._host}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                names = (self.model.name, f"{self.model.name}:latest")
                match: dict[str, Any] = next((m for m in models if m.get("name") in names), {})
                self._digest = str(match.get("digest", "unknown"))[:12]
            except (httpx.HTTPError, ValueError):
                self._digest = "unknown"
        return self._digest

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with retries for transport errors and 5xx (Ollama drops connections when it
        swaps models in and out of memory); other failures are not retried."""
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(2.0**attempt)
            try:
                response = self._client.post(self._url, json=payload)
                response.raise_for_status()
                body: dict[str, Any] = response.json()
                return body
            except httpx.TransportError as exc:
                last = exc
            except httpx.HTTPStatusError as exc:
                last = exc
                if exc.response.status_code < 500:
                    break
            except ValueError as exc:
                last = exc
                break
        raise EmbedError(f"embedding request to {self._url} failed: {last}") from last

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        body = self._post({"model": self.model.name, "input": list(texts), "truncate": False})
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
