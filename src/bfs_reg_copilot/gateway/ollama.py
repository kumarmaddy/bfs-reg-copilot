"""Gateway to a local Ollama server (POST /api/chat). Nothing leaves the machine.

What the gateway guarantees, because each of these has silently ruined an experiment elsewhere:
- only reviewed models can be called;
- the context window is set explicitly (Ollama's default would silently cut a long prompt) and a
  prompt that cannot fit is refused rather than truncated;
- decoding is repeatable: temperature 0 and a fixed seed;
- transient failures are retried a bounded number of times, then reported;
- every call is counted, so a run can report tokens and time.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, Final

import httpx

from bfs_reg_copilot.gateway.types import Completion, GatewayError, Message, Usage

DEFAULT_HOST: Final = "http://127.0.0.1:11434"
ALLOWED_MODELS: Final = ("qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b")
DEFAULT_NUM_CTX: Final = 8192
DEFAULT_SEED: Final = 20261123
CHARS_PER_TOKEN: Final = 3  # deliberately pessimistic: real English averages about 4


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + 1


class OllamaGateway:
    is_test_double = False

    def __init__(
        self,
        model: str,
        *,
        host: str | None = None,
        client: httpx.Client | None = None,
        num_ctx: int = DEFAULT_NUM_CTX,
        seed: int = DEFAULT_SEED,
        temperature: float = 0.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if model not in ALLOWED_MODELS:
            raise GatewayError(f"model {model!r} is not on the reviewed list: {ALLOWED_MODELS}")
        raw_host = host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)
        self._base = (raw_host if raw_host.startswith("http") else f"http://{raw_host}").rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"
        self._client = client or httpx.Client(timeout=600.0)
        self._num_ctx = num_ctx
        self._seed = seed
        self._temperature = temperature
        self._retries = retries
        self._sleep = sleep
        self._digest: str | None = None
        self.usage = Usage()

    def describe(self) -> dict[str, str]:
        return {
            "model": self.model,
            "model_digest": self._model_digest(),
            "temperature": str(self._temperature),
            "seed": str(self._seed),
            "num_ctx": str(self._num_ctx),
        }

    def check_ready(self) -> None:
        try:
            response = self._client.get(f"{self._base}/api/tags")
            response.raise_for_status()
            names = {str(m.get("name")) for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError) as exc:
            raise GatewayError(f"cannot reach Ollama at {self._base}: {exc}") from exc
        if self.model not in names:
            raise GatewayError(f"{self.model} is not installed; run: ollama pull {self.model}")

    def _model_digest(self) -> str:
        """The exact model build, so a run can be tied to it. 'unknown' if Ollama will not say."""
        if self._digest is None:
            try:
                response = self._client.get(f"{self._base}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                match: dict[str, Any] = next((m for m in models if m.get("name") == self.model), {})
                self._digest = str(match.get("digest", "unknown"))[:12]
            except (httpx.HTTPError, ValueError):
                self._digest = "unknown"
        return self._digest

    def complete(
        self,
        messages: list[Message],
        *,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> Completion:
        needed = sum(estimate_tokens(m.content) for m in messages) + max_tokens
        if needed > self._num_ctx:
            raise GatewayError(
                f"prompt too long: about {needed} tokens needed, window is {self._num_ctx}"
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "seed": self._seed,
                "num_ctx": self._num_ctx,
                "num_predict": max_tokens,
            },
        }
        if schema is not None:
            payload["format"] = schema
        started = time.perf_counter()
        body = self._post(payload)
        message = body.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise GatewayError(f"unexpected reply from Ollama: {str(body)[:120]}")
        completion = Completion(
            text=message["content"],
            model=self.model,
            prompt_tokens=int(body.get("prompt_eval_count", 0)),
            completion_tokens=int(body.get("eval_count", 0)),
            finish_reason=str(body.get("done_reason", "stop")),
            latency_s=time.perf_counter() - started,
        )
        self.usage.add(completion)
        return completion

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        last = "no attempt made"
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(2.0**attempt)
            try:
                response = self._client.post(f"{self._base}/api/chat", json=payload)
                if response.status_code >= 500:
                    last = f"server error {response.status_code}"
                    continue
                response.raise_for_status()
                body = response.json()
            except httpx.TransportError as exc:
                last = f"{type(exc).__name__}: {exc}"
                continue
            except (httpx.HTTPError, ValueError) as exc:  # a 4xx or bad JSON will not improve
                raise GatewayError(f"request to {self._base} failed: {exc}") from exc
            if not isinstance(body, dict):
                raise GatewayError("Ollama reply was not a JSON object")
            return body
        raise GatewayError(f"Ollama unreachable or failing after {self._retries + 1} tries: {last}")
