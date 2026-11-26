"""The model gateway, against a mock Ollama server."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from bfs_reg_copilot.gateway.ollama import DEFAULT_NUM_CTX, OllamaGateway, estimate_tokens
from bfs_reg_copilot.gateway.types import GatewayError, Message

MESSAGES = [Message("system", "Be brief."), Message("user", "Hello?")]


def reply(content: str = "hi", **extra: Any) -> httpx.Response:
    body = {
        "message": {"role": "assistant", "content": content},
        "prompt_eval_count": 12,
        "eval_count": 3,
        "done_reason": "stop",
        **extra,
    }
    return httpx.Response(200, json=body)


def gateway(handler: Any, **kwargs: Any) -> OllamaGateway:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaGateway("qwen2.5:7b", host="http://ollama.test", client=client, **kwargs)


def test_request_carries_the_settings_that_make_runs_repeatable() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return reply()

    schema = {"type": "object"}
    completion = gateway(handler).complete(MESSAGES, schema=schema, max_tokens=100)
    body = seen[0]
    assert body["model"] == "qwen2.5:7b"
    assert body["stream"] is False
    assert body["format"] == schema
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert body["options"] == {
        "temperature": 0.0,
        "seed": 20261123,
        "num_ctx": DEFAULT_NUM_CTX,
        "num_predict": 100,
    }
    assert (completion.text, completion.prompt_tokens, completion.completion_tokens) == (
        "hi",
        12,
        3,
    )
    assert completion.finish_reason == "stop"


def test_no_schema_means_no_format_field() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return reply()

    gateway(handler).complete(MESSAGES)
    assert "format" not in seen[0]


def test_usage_accumulates_over_calls() -> None:
    g = gateway(lambda request: reply())
    g.complete(MESSAGES)
    g.complete(MESSAGES)
    assert (g.usage.calls, g.usage.prompt_tokens, g.usage.completion_tokens) == (2, 24, 6)
    assert g.usage.seconds >= 0


def test_only_reviewed_models_can_be_called() -> None:
    with pytest.raises(GatewayError, match="reviewed list"):
        OllamaGateway("some-random-model:latest", host="http://x")


def test_a_prompt_that_cannot_fit_is_refused_not_truncated() -> None:
    g = gateway(lambda request: reply(), num_ctx=1000)
    too_long = [Message("user", "x" * 5000)]
    with pytest.raises(GatewayError, match="prompt too long"):
        g.complete(too_long, max_tokens=100)
    assert estimate_tokens("x" * 300) == 101


def test_transient_failures_are_retried_then_succeed() -> None:
    calls: list[int] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, text="busy")
        return reply("finally")

    g = gateway(handler, retries=2, sleep=waits.append)
    assert g.complete(MESSAGES).text == "finally"
    assert len(calls) == 3
    assert waits == [2.0, 4.0]


def test_connection_failures_give_up_after_the_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("refused")

    g = gateway(handler, retries=1, sleep=lambda s: None)
    with pytest.raises(GatewayError, match="unreachable or failing after 2 tries"):
        g.complete(MESSAGES)
    assert len(calls) == 2


def test_client_errors_are_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(GatewayError, match="failed"):
        gateway(handler, sleep=lambda s: None).complete(MESSAGES)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"oops": 1}),
        httpx.Response(200, json=[1]),
    ],
)
def test_unusable_replies_are_errors(response: httpx.Response) -> None:
    with pytest.raises(GatewayError):
        gateway(lambda request: response).complete(MESSAGES)


def test_describe_records_the_model_build() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen2.5:7b", "digest": "845dbda0ea48abcdef"}]}
            )
        return reply()

    info = gateway(handler).describe()
    assert info["model"] == "qwen2.5:7b"
    assert info["model_digest"] == "845dbda0ea48"
    assert info["temperature"] == "0.0"
    assert info["num_ctx"] == str(DEFAULT_NUM_CTX)


def test_describe_survives_a_server_that_will_not_say() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert gateway(handler).describe()["model_digest"] == "unknown"


def test_check_ready_accepts_an_installed_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})

    gateway(handler).check_ready()


def test_check_ready_names_the_missing_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})

    with pytest.raises(GatewayError, match=r"ollama pull qwen2\.5:7b"):
        gateway(handler).check_ready()


def test_check_ready_reports_an_unreachable_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(GatewayError, match="cannot reach Ollama"):
        gateway(handler).check_ready()


def test_think_is_absent_by_default_and_sent_only_when_asked() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return reply()

    plain = gateway(handler)
    plain.complete(MESSAGES)
    assert "think" not in seen[0]  # every earlier run sent exactly this payload
    assert "think" not in plain.describe() or plain.describe().get("think") is None

    quiet = gateway(handler, think=False)
    quiet.complete(MESSAGES)
    assert seen[1]["think"] is False
    assert quiet.describe()["think"] == "false"


def test_the_experiment_candidates_are_on_the_reviewed_list() -> None:
    from bfs_reg_copilot.gateway.ollama import ALLOWED_MODELS

    for tag in ("qwen3.5:9b", "qwen3:14b", "gemma3:12b", "gemma4:12b", "phi4:14b"):
        assert tag in ALLOWED_MODELS
