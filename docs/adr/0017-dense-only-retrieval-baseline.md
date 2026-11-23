# ADR-0017: Dense-only retrieval is the baseline; hybrid is built but off

- Status: Accepted
- Date: 2026-11-23
- Deciders: Project owner

## Context

ADR-0004 planned hybrid retrieval (keyword plus vector, fused by reciprocal rank). Slice 2.5 built
all three retrievers behind one interface and compared them on the 32 answerable **dev**
questions before deciding. The adoption rule was fixed before any keyword or hybrid number was
seen: hybrid replaces dense-only only if hit@5 does not drop and it gains at least one question at
hit@5 or at least two at hit@3.

## What was measured

bge-m3 ([ADR-0016](0016-embedding-model-bge-m3.md)), 624 chunks, hit@k at section level.

| | hit@1 | hit@3 | hit@5 | hit@10 |
|---|---|---|---|---|
| dense | 22/32 | 29/32 | **30/32** (93.8%) | 31/32 |
| fulltext | 10/32 | 19/32 | 22/32 (68.8%) | 27/32 |
| hybrid | 20/32 | 28/32 | 28/32 (87.5%) | 31/32 |

Hybrid recovered G-E21-005 but lost G-B10-003, G-B13-001 and G-STR-002, which dense got right.
Latency per question was about 94 ms (p50) and 109 ms (p95) for dense and hybrid.

## Decision

The baseline retriever is **dense-only with bge-m3**. By the rule, hybrid does not qualify
(hit@5 fell from 30 to 28). The hybrid and keyword retrievers stay in the code, tested, but are
not the default, so they can be revisited without rebuilding.

## How much weight this carries

- Thirty-two questions: a swing of two is inside the noise (intervals 80-98% against 72-95%). The
  result is "no evidence that hybrid helps here", not "hybrid is worse".
- The keyword side is **untuned** on purpose. It ORs every stemmed word of the question, so common
  words ("report", "client", "entity") pull in unrelated chunks; that is the likely source of the
  three losses. A weighted or stricter keyword query might help, but tuning on 32 questions
  invites fitting them, so this was not tried.
- The rule was written knowing dense was already at 30 of 32, so hybrid had little room to gain.
- Retrieval only: no claim about answer quality.

## Consequences

- Simpler baseline: one model call and one SQL query per question.
- ADR-0004 stays accepted (PostgreSQL, pgvector and full-text columns); only the hybrid step is
  deferred. The `text_search` column and index remain, since they cost little.
- The two dev misses (G-E21-005, G-STR-003) are the targets for later improvements: smaller
  chunks, a reranker, or query rewriting. Each is judged against this baseline on dev.

## Revisit when

The dev set is larger, a reranker is added (hybrid candidates may suit it better than dense
alone), or the US eCFR pack adds text where exact section numbers matter more.
