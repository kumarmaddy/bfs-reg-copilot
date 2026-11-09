# Delivery plan

Start date: 2026-11-08. Calendar dates are targets for a single part-time owner and will slip;
the **cut order** below says what to drop first.

## Phases, exit criteria and gates

| Phase | Outcome | Main work | Exit criteria | Gate |
|---|---|---|---|---|
| 0 Frame and govern | Agreed scope, metrics, risks, sources, scaffold | Docs 00-08, ADRs, register validation, CI | Gate 0/1 checklist passed; owner has verified principle numbers and FINTRAC terms | 0, 1 |
| 1 Data pipeline | Cleaned, versioned, chunked corpus with lineage | Fetch only `ingest_allowed` sources; raw/cleaned/curated layers; Airflow DAG; chunking with section metadata; data-quality tests | Every chunk traces to a register entry and retrieval date; DQ tests green; no corpus in git | 2 |
| 2 Baseline RAG + evaluation | Working end-to-end answer with citations; gold set; baseline scores | pgvector schema, embedder, retriever, generator via gateway, API, gold set (≥60), eval harness | M1 and M2 measured on dev split and recorded; evaluation runs in CI on a small subset | 3 |
| 3 Improve | Better retrieval, abstention, optional fine-tune, Pack C | Hybrid BM25+vector, reranker, abstention threshold, guardrails, optional QLoRA, eCFR pack | M1 ≥ 90% and M2 ≥ 90% on hold-out, or documented gap | 4 |
| 4 Productionise | Reproducible deployment with observability | Terraform, Helm, kind then AKS, CI/CD, secrets, tracing, load test | M3 p95 < 10 s deployed; teardown tested; cost within budget | 5 |
| 5 Shadow pilot and operate | Evidence pack | Model card, E-23-style inventory entry, runbook, monitoring review, demo | Documents complete; limitations stated; credential wording agreed | 6 |

## Indicative timeline

| Window | Phase |
|---|---|
| Week 1 | 0, then start 1 |
| Weeks 2-3 | 1 and 2 |
| Weeks 4-5 | 3 |
| Weeks 6-7 | 4 (inside the Azure free-credit window; start the clock only when ready) |
| Week 8 | 5 |

The Azure free credit lasts 30 days from sign-up, so create the account only when Phase 4 starts.

## Cut order if time runs short

1. Fine-tuning (Phase 3 optional part).
2. Shadow pilot (Phase 5).
3. Pack C (US eCFR).
4. AKS deployment (keep `kind`).

**Never cut:** the gold set and evaluation, the source register, the risk register, and the honest
description of limits.

## Working agreements

- Every phase ends with a review against its exit criteria, written into the gate checklist.
- Changes to scope, metrics or sources go through the change log in `02-success-metrics.md` or the
  register, not silent edits.
- Anything unverified is marked `[to verify]` until the owner checks the primary source.
