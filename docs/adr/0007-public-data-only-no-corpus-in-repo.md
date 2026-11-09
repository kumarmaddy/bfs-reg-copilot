# ADR-0007: Public data only; no corpus text in the repository

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner

## Context

The repository is public and doubles as a portfolio. Source documents belong to their publishers.
OSFI's terms allow non-commercial reproduction with attribution and require permission for
commercial redistribution. 

## Decision

1. Use public data only. No employer, client or customer data, and no personal data, ever, unless
   the owner first gets written approval and the system is re-rated.
2. Never commit source documents, chunks, embeddings or excerpts beyond short quotations to the
   repository. Commit only URLs, metadata and the code that fetches them.
3. Ingestion is gated by the source register, which CI validates.

## Alternatives considered

| Option | Why not |
|---|---|
| Commit the corpus for easy reproduction | Breaches the spirit of publisher terms for redistribution and invites confusion about what is official |
| Mirror the corpus in cloud storage with public access | Same, and increases the chance of being mistaken for an official source |

## Consequences

- Others reproduce the system by running the ingestion, which respects each site's terms.
- Evaluation gold sets contain original questions and paraphrased key points only.
- The licence question for commercial use is explicitly deferred to counsel.

## Revisit when

A publisher grants an open licence for the documents, or the owner obtains permission.
