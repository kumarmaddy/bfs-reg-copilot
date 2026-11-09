# ADR-0005: LangChain used only inside adapters, behind our own interfaces

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner

## Context

Bank job postings reviewed ask for LangChain experience, and name LlamaIndex and Haystack as
useful extras. Frameworks change quickly and can make behaviour hard to trace, which is a problem
for explainability and model-risk review (E-23 expects documented methodology and review of
third-party components).

## Decision

Define small interfaces in our own code (`Embedder`, `Retriever`, `Generator`, `Reranker`).
Domain and evaluation code depend only on those interfaces. LangChain is allowed inside adapter
modules where it saves effort (document loaders, text splitting, prompt templates), with versions
pinned. No framework types cross an interface boundary.

## Alternatives considered

| Option | Why not |
|---|---|
| No framework at all | Cleanest to audit, but skips a skill the market asks for |
| LlamaIndex or Haystack | Valid; evidence suggests LangChain is requested more often in the postings reviewed (small sample) |
| Framework throughout | Couples evaluation and governance evidence to a fast-moving library |

## Consequences

- A little more code than using the framework end to end.
- The evaluation harness and tests run against interfaces, so swapping the framework or the model
  does not invalidate them.
- Each adapter must be pinned and listed as a third-party component in the inventory.

## Revisit when

The client uses a different framework, or a framework upgrade breaks an adapter twice in a row.
