"""A deterministic stand-in embedder for tests: hashed bag of words. Not a real model.

Texts that share words get similar vectors, which is enough to test indexing and search without
a model server. Anything measured with it is labelled a test double.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

from bfs_reg_copilot.embed.models import BGE_M3, EmbeddingModel

_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    is_test_double = True

    def __init__(self, model: EmbeddingModel = BGE_M3) -> None:
        self.model = model
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.model.dims
        for word in _WORD.findall(text.lower()):
            slot = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big")
            vector[slot % self.model.dims] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(t) for t in texts]

    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(self.model.query_format(q)) for q in queries]
