# ADR-0006: LiteLLM as the model gateway

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner

## Context

Platform teams at banks put an AI gateway in front of models for routing, budgets, guardrails and
logging; one Singapore bank describes an on-premises GenAI platform with an AI gateway, guardrails
and observability. We need to swap between Ollama locally and a hosted model in Azure, enforce
token budgets, and keep model calls observable.

## Decision

Run LiteLLM as an OpenAI-compatible gateway between the application and all model providers.
The application knows only the gateway URL and a logical model name. Pin the version, scan the
image, store provider keys in Key Vault, and keep a documented fallback of calling the provider
directly.

## Alternatives considered

| Option | Why not (or why later) |
|---|---|
| Call provider SDKs directly | Simplest, but spreads provider details through the code and loses central budgets and logs |
| Azure API Management AI gateway features | Good Azure-native option; less portable. API Management may still sit in front of the API |
| Kong or another general gateway | Heavier; revisit if the client already runs it |

## Consequences

- One more component to secure, patch and monitor (B-13 asset inventory, supply-chain risk R-16).
- Provider swaps become configuration changes, supporting exit planning (B-10).
- Logical model names let evaluation runs record exactly which provider and version answered.

## Revisit when

The client mandates a different gateway, or a security review of the gateway raises a concern we
cannot mitigate.
