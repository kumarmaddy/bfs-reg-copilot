# 02. Success metrics and evaluation protocol

| | |
|---|---|
| Version | 0.1 (Draft for Gate 0) |
| Date | 2026-11-08 |
| Rule | **Targets are frozen at Gate 0.** Changing one needs a dated change note in section 6. |

Freezing targets before measuring prevents moving the goalposts after seeing the baseline. The
baseline is expected to fall short of several of these; the gap is the work.

## 1. Primary metrics (accepted by the owner)

| ID | Metric | Definition | Target | Measured on | Gate |
|---|---|---|---|---|---|
| M1 | Cited-answer accuracy | Share of **answerable** gold questions whose answer is substantively correct per the key points **and** cites at least one source section that contains the support | >= 90% | Gold set, hold-out at Gate 3 | 3 |
| M2 | Correct refusal rate | Share of **unanswerable or out-of-scope** gold questions where the system says it cannot answer from the sources and does not fabricate | >= 90% | Gold set | 3 |
| M3 | p95 latency | 95th percentile time from request to final answer, warm, single user, deployed version | < 10 s | Load script, 100 requests | 5 |

## 2. Supporting metrics (proposed; calibrate after the Phase 2 baseline)

| ID | Metric | Definition | Proposed target |
|---|---|---|---|
| M4 | Retrieval hit@5 | Gold supporting section appears in the top 5 retrieved chunks | >= 90% |
| M5 | Fabricated citation rate | Citations that point to a document or section not in the retrieved context | <= 1% (stretch: 0) |
| M6 | Faithfulness | Share of answers with no claim unsupported by the retrieved context | >= 90% |
| M7 | Cost per answered query | Model and retrieval cost on the hosted version | <= US$0.02 |
| M8 | Prompt-injection resistance | Adversarial cases where an instruction in a document or query overrides the rules | 0 successes in the adversarial set |
| M9 | Provenance completeness | Answers that show version or retrieval date for every cited source | 100% |
| M10 | Evaluation reproducibility | Same commit and settings reproduce M1 to M6 | within 2 points |

The M7 ceiling is derived from my arithmetic on a third-party price table (roughly US$0.001 per
query on a small hosted model and about US$0.012 on a large one at 3,000 input and 400 output
tokens).

## 3. Scale and resilience assumptions (assumptions, not requirements)

These exist so the design is tested against something. Re-set them after the baseline.

| ID | Assumption | Test |
|---|---|---|
| S1 | 20 concurrent users with p95 under 15 s | Load test in Phase 4 |
| S2 | Index of at least 50,000 chunks with retrieval p95 under 500 ms | Scale corpus (US Title 12 plus Packs A and B); the chunk count is a guess until measured |
| S3 | Corpus index is rebuildable: RTO 4 h, RPO 24 h | Restore drill in Phase 5 |
| S4 | A changed source is detected by content hash and flagged for re-review before re-indexing | Ingestion test |

## 4. Gold set specification

- **Size:** at least 60 questions: 40 answerable, 15 unanswerable or out of scope, 5 adversarial.
- **Answerable item fields:** question, key points of a correct answer, supporting source id and
  section anchor(s), type (lookup, definition, multi-hop, comparison, date or version), difficulty.
- **Unanswerable cases include:** topics not in the corpus, US rules asked in a Canadian context
  before Pack C exists, requests for legal advice, and questions with a false premise.
- **Adversarial cases include:** instruction text inside a document, requests to reveal the system
  prompt, and attempts to obtain an uncited answer.
- **Split:** 80% development, 20% hold-out. The hold-out is sealed until Gate 3 and used once per
  release candidate.
- **Labelling:** by the owner from the primary text, never from a model's answer. Because there
  is one annotator, re-label a random 15 items after 48 hours to estimate self-consistency.
- **Coverage:** every ingestible source supplies at least 5 answerable questions, so no source is
  untested.

## 5. Measurement protocol

1. Evaluation runs from a single command and is also run by CI on a small smoke subset.
2. Human labels are the reference. A language-model judge may be used to scale M5 and M6, but only
   after agreement with human labels is checked on at least 30 items (proposed threshold: 85%
   agreement) and the judge model and prompt are recorded.
3. Every run logs: git commit, corpus version and hashes, embedding model, generation model and
   version, prompt version, retrieval settings, and seed where applicable.
4. Results are written to a file and tracked in MLflow so any claim can be traced to a run.

## 6. Change log for targets

| Date | Change | Reason | Approved by |
|---|---|---|---|
| 2026-11-08 | Initial targets M1 to M3 accepted by the owner; M4 to M10 and S1 to S4 proposed | Gate 0 | Project owner |
