# ADR-0004: PostgreSQL with pgvector and full-text search for retrieval

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner

## Context

Regulatory text is full of exact terms (guideline names, section numbers) as well as paraphrased
concepts, so retrieval should combine keyword and vector search. We want identical behaviour on
the laptop and in the cloud. Azure AI Search's free tier allows one service per subscription and
caps storage at 50 MB, which is a poor fit for a scale test.

## Decision

Store chunks, metadata and embeddings in PostgreSQL. Use pgvector for similarity search and
PostgreSQL full-text search for keywords, and combine ranks (reciprocal rank fusion) in the
retrieval layer behind a `Retriever` interface. Rerank the top candidates with a cross-encoder.

## Alternatives considered

| Option | Why not (or why later) |
|---|---|
| Azure AI Search | Strong enterprise option with hybrid search and semantic ranking. Free tier too small; paid tier costs money. An adapter is a Phase 4 stretch goal if the client uses it |
| Chroma or similar embedded stores | Quick to start, but not what a bank would approve and not equal to the cloud setup |
| OpenSearch / Elasticsearch | Capable, but heavier to run locally |

## Consequences

- One engine to back up, secure and monitor; widely approved in banks (indicative, not verified).
- We own the hybrid-ranking logic and index tuning (HNSW parameters).
- Scale ceiling is untested: the scale test in Phase 4 (target S2) will show whether it holds.

## Revisit when

Retrieval p95 exceeds the S2 target on the scale corpus, or the client mandates another store.
