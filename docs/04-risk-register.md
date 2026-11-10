# 04. Risk register and risk tier

| | |
|---|---|
| Version | 0.1 (Draft for Gate 0) |
| Date | 2026-11-08 |
| Scales | Likelihood (L) and impact (I) from 1 (low) to 5 (high). Score = L x I. 1-6 low, 8-12 medium, 15-25 high |

## 1. Risk tier

**Tier: Moderate** (internal 3-level scale: Low, Moderate, High).

OSFI's final E-23 asks institutions to rate model risk using clear criteria that combine
quantitative and qualitative factors, and its release letter says it removed the reference to
"risk classification". This tier is therefore an internal judgement with a written rationale.

| Factor | Assessment | Direction |
|---|---|---|
| Business use | Advisory research aid; a human decides | Lowers |
| Complexity | Retrieval plus a hosted language model; non-deterministic | Raises |
| Autonomy | None: no tools, no actions | Lowers |
| Data reliability | Authoritative public sources, but they change and can be stale | Neutral |
| Customer impact | None directly | Lowers |
| Regulatory risk | A wrong reading of a regulatory expectation could mislead an analyst | Raises |
| Third-party dependence | Hosted model and cloud provider | Raises |

**Re-rate to High when any of these happens:** internal policies or non-public data are added;
the output feeds a decision without human verification; the system gains the ability to act
(agents, filings, tickets); it is offered to customers; the use case changes materially.
**Re-review (not necessarily re-rate) when:** the base model or version changes, the embedding
model changes, prompts or retrieval settings change, the corpus changes materially, or a metric
breaches its threshold.

## 2. Risk register

Residual scores assume the mitigations are in place and tested.

| ID | Risk | Cause | Impact | L | I | Score | Mitigation | Residual | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | Confident wrong answer | Model hallucination or poor retrieval | Analyst relies on a wrong reading | 4 | 4 | 16 | Answer only from retrieved text; mandatory citations; abstention tuned and measured (M1, M2, M6); UI states "verify against the source" | Medium | 2, 3 |
| R-02 | Fabricated citation | Model invents section numbers | Loss of trust; wrong reference in a memo | 3 | 4 | 12 | Citations generated from retrieved chunk metadata, not free text; automated check that every citation maps to a retrieved chunk (M5) | Low | 2, 3 |
| R-03 | Stale or superseded source | Regulator updates a document | Answer cites an old rule | 4 | 4 | 16 | Content hash per source; re-check schedule; answers show retrieval date and version; superseded sources blocked in register | Medium | 1, 5 |
| R-04 | Jurisdiction mix-up | CA and US texts blended | Wrong regime applied | 3 | 4 | 12 | Jurisdiction metadata filter; answer states jurisdiction; gold questions test it | Low | 3 |
| R-05 | Automation bias | Users trust fluent text | Verification skipped | 4 | 3 | 12 | Citations link to the original; visible limitations text; usage guidance | Medium | 4, 5 |
| R-06 | Indirect prompt injection | Instructions hidden in a source document | Rules overridden or data leaked | 2 | 4 | 8 | Treat retrieved text as data in the prompt design; adversarial tests (M8); no tools to abuse; content scanning on ingest | Low | 3, 4 |
| R-07 | Personal data in queries and logs | Users paste sensitive text | Privacy incident | 3 | 3 | 9 | Public-data-only policy; Presidio redaction before logging; short log retention; warning text | Low | 4 |
| R-08 | Breach of source terms | Corpus text redistributed or presented as official | Takedown or reputational harm | 3 | 4 | 12 | Corpus never in repo (ADR-0007); register gates ingestion; attribution on every answer; non-commercial use only | Low | 0, 1 |
| R-09 | Model version change or retirement | Provider updates or retires a model | Silent quality regression or outage | 4 | 3 | 12 | Pin versions; evaluation reruns on change; gateway allows fast swap; record retirement dates | Medium | 4, 5 |
| R-10 | Cost overrun | Free credit expires; fine-tuned hosting charges; always-on resources | Unexpected bill | 3 | 3 | 9 | Budget alert before anything else; Terraform teardown; no fine-tuned hosting on Azure; open the account only at Phase 4 | Low | 4 |
| R-11 | Provider outage | Cloud or model service down | Demo unavailable | 3 | 2 | 6 | Local fallback model through the gateway; recorded demo | Low | 4, 5 |
| R-12 | Scale or latency failure | Chunking or index choice | Misses M3 or S1 to S2 | 3 | 3 | 9 | Load test with scale corpus; index tuning; caching | Low | 3, 4 |
| R-13 | Context lost in chunking | Sections split badly | Wrong or missing answer | 4 | 3 | 12 | Structure-aware chunking; section anchors in metadata; retrieval hit@5 measured | Low | 1, 2 |
| R-14 | Overfitting to the gold set | Tuning against the same questions | Inflated metrics | 4 | 3 | 12 | Sealed 20% hold-out; used once per release candidate; log every run | Low | 2, 3 |
| R-15 | Residency exception misunderstood | Global model deployment processes data outside Canada | Perceived breach of residency expectation | 2 | 3 | 6 | Documented exception for public data only (ADR-0008); production variant described | Low | 1, 4 |
| R-16 | Supply-chain vulnerability | Dependencies, container images, gateway | Compromise | 3 | 4 | 12 | Pinned versions, dependency audit, image scanning, SBOM, Dependabot, CodeQL | Medium | 0, 4 |
| R-17 | No independent review; one person holds every role | Solo project | Weak challenge; separation-of-duties gap | 5 | 3 | 15 | Written review checklist; automated evidence; request a peer review at Gates 3 and 5. **Accepted limitation** | Medium | all |
| R-18 | Overstating the credential | Describing the project as production-proven | Credibility loss in front of a client | 3 | 5 | 15 | README and demo say "built to production patterns on public data, not deployed in a regulated institution" | Low | all |
| R-19 | Tool-summary errors in this document set | Section numbers extracted by automated summary | Wrong reference cited | 3 | 3 | 9 | Mark [to verify]; owner checks against primary text at Gate 0 (G0-6) | Low | 0 |

## 3. Review cadence

While the system is a demonstration: review this register at each gate and whenever a re-review
trigger above occurs. If it were deployed in an institution, cadence would be set by that
institution's rating.
