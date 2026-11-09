# 05. Data statement

| | |
|---|---|
| Version | 0.1 (Draft for Gate 1) |
| Date | 2026-11-08 |
| Related | [`register.yaml`](../data/sources/register.yaml), [ADR-0007](adr/0007-public-data-only-no-corpus-in-repo.md), [ADR-0008](adr/0008-residency-exception-learning-environment.md) |

## 1. Principle

This project uses **public data only**. It uses no employer, client or customer data, not even
samples, and no personal data. If that ever changes, the system is re-rated (see
[04](04-risk-register.md)) and the owner obtains written approval first.

## 2. Data inventory and classification

| Data | Classification | Where it lives | Notes |
|---|---|---|---|
| Source documents (regulator pages and PDFs) | Public, third-party owned | Private object storage and database; **never in the repository** | Publisher terms apply; see section 3 |
| Chunks and embeddings | Derived from third-party text | Private database | Treated as part of the corpus: not published, not redistributed |
| Source register | Own work, public | Repository | Metadata and URLs only |
| Gold question set and labels | Own work | Repository, except the sealed hold-out | Questions are original; expected answers are paraphrased key points, not copied text |
| User queries | Treated as confidential | Application logs | Redacted before logging; short retention |
| Evaluation results and traces | Own work | MLflow and observability store | May include short quoted excerpts; kept private |
| Secrets and keys | Secret | Key Vault; never in git | Push protection and secret scanning on the repository |

## 3. Source terms and what they mean for the design

| Publisher | Terms observed on 2026-11-08 | Design consequence |
|---|---|---|
| OSFI | Non-commercial reproduction is permitted without further permission if accuracy is ensured, the full title and author are named, and the copy states it is based on the version at the original URL. Commercial redistribution needs prior written permission. Modification, adaptation and translation are not addressed | Non-commercial use only. Every answer shows title, issuer, URL and retrieval date. Quotations are short. The system does not present itself as OSFI's |
| FINTRAC and other canada.ca sites | Canada.ca general terms say the same in substance. A FINTRAC-specific footer notice was not seen because the fetch was truncated | FINTRAC sources stay blocked until the owner confirms the footer terms (register entry `B-FINTRAC-STR`) |
| eCFR / US federal rules (Phase 3) | US federal government works are generally in the public domain **[to verify]** | Confirm per source before ingestion |

**Commercial use needs separate permission.** If this work were used commercially, for example
inside a client engagement, the corpus rights would need a fresh decision by the client's counsel.
That is a real finding to raise with a client, and it is recorded here so it is not forgotten.

Attribution text shown with answers comes from each register entry's `attribution_template`.

## 4. Handling rules

1. **Ingestion is gated.** A source is ingested only if its register entry has
   `ingest_allowed: true`, which CI allows only with verified terms and an opened primary page.
2. **Provenance on every chunk:** register id, URL, retrieval timestamp, content hash, section
   anchor, effective date where known, language, jurisdiction.
3. **Versioning:** a changed content hash creates a new version for review. The old version is
   kept for reproducibility of past evaluation runs and is not served to users unless chosen.
4. **Logging:** log request ids, timings, token counts, retrieved chunk ids and model versions.
   Do not log raw queries or answers in clear text; log redacted forms. Proposed retention: 30
   days for application logs [owner to confirm].
5. **No personal data:** the interface warns against pasting personal or confidential
   information. Presidio-style detection redacts likely personal data before logging.
6. **Crawling manners:** identify the client, respect robots.txt, rate-limit, and prefer official
   downloads or APIs over scraping.

## 5. Residency decision

| Environment | Where data and processing live |
|---|---|
| Local development | The owner's laptop only |
| Cloud demo storage, database, compute | Azure Canada Central |
| Hosted model calls (learning environment) | **Exception:** a global model deployment may process prompts outside Canada. Acceptable only because all data is public. Recorded in ADR-0008 |
| Production variant (described, not built) | Regional standard or provisioned deployment in a Canadian region, verified model availability, no global standard or global batch deployments |

Model availability in Canadian regions is narrower than in other regions, according to
community answers on Microsoft's Q&A site, which are not authoritative. **[to verify]** against
Microsoft's current model-availability documentation before Phase 4.

## 6. Open items

1. Owner confirms the FINTRAC footer terms (unblocks `B-FINTRAC-STR`).
2. Owner opens `B-FINTRAC-CPR` and `B-FINTRAC-RBA` and confirms title, date and terms.
3. Confirm US federal public-domain treatment before Pack C.
4. Confirm the log retention period.
