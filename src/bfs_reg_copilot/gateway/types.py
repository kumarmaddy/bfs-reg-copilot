"""What a model call looks like to the rest of the system, whichever model answers it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


class GatewayError(Exception):
    """The model could not be called or its reply could not be used."""


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str  # "stop" is normal; "length" means the reply was cut off
    latency_s: float


@dataclass
class Usage:
    """Running totals, so cost and latency can be reported for a whole run (metrics M3, M7)."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def add(self, completion: Completion) -> None:
        self.calls += 1
        self.prompt_tokens += completion.prompt_tokens
        self.completion_tokens += completion.completion_tokens
        self.seconds += completion.latency_s


class LLMGateway(Protocol):
    name: str
    is_test_double: bool
    usage: Usage

    def describe(self) -> dict[str, str]:
        """Model, version and decoding settings worth recording with a run."""
        ...

    def check_ready(self) -> None:
        """Raise GatewayError if the model cannot be called, before a long run starts."""
        ...

    def complete(
        self,
        messages: list[Message],
        *,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> Completion:
        """One reply. With a schema the reply is constrained to valid JSON of that shape."""
        ...
