# 03. Requirements trace

| | |
|---|---|
| Version | 0.2 (Draft for Gate 0) |
| Date | 2026-11-08 |
| References checked | 2026-11-18 (checklist item G0-6) |
| Sources | OSFI Guideline E-23 (2027), Guideline B-10, Guideline B-13 (register ids A-OSFI-E23, A-OSFI-B10, A-OSFI-B13) |

## Read this first

- **This is a voluntary alignment.** The assistant is a portfolio project, not a federally
  regulated institution's model. A real institution would map these expectations to its own
  policies. The purpose here is to practise the mapping and to produce evidence a reviewer
  would recognise.
- **Section and principle numbers were checked on 2026-11-18.** The heading numbers and
  titles of each guideline PDF were compared with every reference below, and four references
  were corrected. The paraphrases in the "Expectation" column are our wording and were
  spot-checked, not compared line by line. The owner's spot check is recorded in checklist
  item G0-6.
- **The guidelines are principles-based.** None of the three mentions generative AI or language
  models. E-23 explicitly covers AI/ML in its definition of a model (section A.4), and its
  application to a retrieval-augmented assistant below is **our interpretation**, not OSFI's.
- **Draft versus final.** The 2021 draft of B-13 described five domains. The final text has
  three domains and 17 principles. Use the final.
- **Dates.** E-23 was issued on 2025-09-11 and takes effect on **2027-05-01**; both dates are
  shown on the guideline. B-13 was issued on 2022-07-31 and B-10 on 2023-04-30. Their effective
  dates (2024-01-01 for B-13 and 2024-05-01 for B-10) come from secondary sources and are not
  stated in the guideline PDFs **[to verify]**.

## Trace table

Phase column: when the control is built or evidenced.

### E-23 Model Risk Management

| ID | Reference | Expectation (paraphrased) | Our control | Evidence | Phase |
|---|---|---|---|---|---|
| REQ-01 | E-23 A.4 | A model processes inputs to produce results and expressly includes AI/ML | Treat the assistant (corpus, retrieval, language model, answers) as a model | Inventory entry | 5 |
| REQ-02 | E-23 P1.1 | Senior ownership, skilled and multidisciplinary staff | Named roles, with gaps recorded openly | [00-index](00-index.md#roles), risk R-17 | 0 |
| REQ-03 | E-23 P1.2 | Framework covers externally sourced models and data, reviewed periodically | Vendor model and corpus are inventory items; review at each trigger | Inventory, ADR-0006 | 0, 5 |
| REQ-04 | E-23 P1.3 | Use only where it supports decisions and fits the intended purpose; retire when unfit | Purpose, non-goals and re-assessment triggers written down | [01](01-concept-brief.md), [04](04-risk-register.md) | 0 |
| REQ-05 | E-23 P2.1, App. 1 | Identify and track all models including vendor models | Inventory with the Appendix 1 fields | `docs/inventory/` entry (Phase 5) | 5 |
| REQ-06 | E-23 P2.2 | Rate inherent risk with clear quantitative and qualitative criteria; re-rate on trigger events | Written rating criteria and triggers | [04](04-risk-register.md) | 0 |
| REQ-07 | E-23 P2.3 | Rating sets review frequency, documentation depth, approval, monitoring and usage limits | Advisory-only use; review and monitoring cadence stated | [04](04-risk-register.md) | 0, 5 |
| REQ-08 | E-23 D.2 | State purpose and scope; consider transparency, bias and privacy for AI | Mandatory citations for transparency; public data only; privacy statement | [01](01-concept-brief.md), [05](05-data-statement.md) | 0 |
| REQ-09 | E-23 P3.2 | Data accurate, relevant, traceable, timely; provenance documented | Source register with versions, hashes, effective dates, retrieval dates; superseded sources blocked | `register.yaml`, ingestion tests | 0, 1 |
| REQ-10 | E-23 P3.3 | Development standards, documented methodology, performance criteria, explainability | Configuration is versioned; evaluation criteria frozen; citations required | [02](02-success-metrics.md), model card | 2, 5 |
| REQ-11 | E-23 P3.4 | Independent review, triggered by changes and breaches | Defined review triggers; evaluation suite reruns on every change; reviewer still to be assigned | Review log, CI | 3, 5 |
| REQ-12 | E-23 D.2 | Approval records suitability, rating and residual risk, with known limitations | Approval record lists limitations and required human verification | Approval record | 5 |
| REQ-13 | E-23 P3.5 | Controlled deployment, change control, dev and prod consistency, security assessment (see B-13, E-21) | Terraform, CI/CD, same container in dev and prod, injection and leakage tests | Pipelines, tests | 4 |
| REQ-14 | E-23 P3.6 | Monitoring with thresholds, drift and vendor-update tracking, contingency and decommissioning | Monitoring dashboard, pinned model versions, alert thresholds, runbook, retirement plan | Dashboards, runbook | 5 |

### B-10 Third-Party Risk Management

| ID | Reference | Expectation (paraphrased) | Our control | Evidence | Phase |
|---|---|---|---|---|---|
| REQ-15 | B-10 2.1 | Scale oversight to the risk and criticality of each arrangement | Criticality assessment for the cloud and model providers | Third-party assessment | 4 |
| REQ-16 | B-10 P4, 2.2.2, 4.4 | Due diligence before contracting and on an ongoing basis, including portability | Public-information due-diligence worksheet for each provider | Worksheet | 4 |
| REQ-17 | B-10 P6, 2.3.1, 3.1 | Written agreements; where terms are standard, compensate with monitoring and resilience | Record the provider's standard terms as accepted risk | RAID log | 4 |
| REQ-18 | B-10 2.2.3, 2.3.5, 4.4 | Assess concentration, keep exit plans, consider cloud portability | Gateway and Terraform make providers swappable; written exit plan | ADR-0001, ADR-0002, ADR-0006, exit plan | 4 |
| REQ-19 | B-10 P7, 2.2.2.3, 2.3.2.1 | Data location, isolation and access are agreed and verifiable | Residency decision and exception record | [05](05-data-statement.md), ADR-0008 | 1 |
| REQ-20 | B-10 P5, 2.2.4 | Know the provider's subcontractors, including model developers and infrastructure | List sub-processors for each hosted service | Worksheet | 4 |
| REQ-21 | B-10 P10, P11 | Monitor providers; require incident notification and root-cause analysis | Subscribe to provider status; runbook step for provider incidents | Runbook | 5 |

### B-13 Technology and Cyber Risk Management

| ID | Reference | Expectation (paraphrased) | Our control | Evidence | Phase |
|---|---|---|---|---|---|
| REQ-22 | B-13 P5 | Current asset inventory including third-party assets handling information | Component inventory (SBOM plus services list) | SBOM, inventory | 4 |
| REQ-23 | B-13 P8, P9 | Controlled change and patching, separation of duties, traceable change records | Pull requests, required checks, change log. **One person cannot separate duties**; the gap is recorded and compensated by required checks and an independent reviewer when available | Branch rules, change log | 0, 4 |
| REQ-24 | B-13 P7, 3.2.9 | Secure development lifecycle with scanning and testing before release | CodeQL, dependency audit, image scanning, tests in CI | CI results | 0, 4 |
| REQ-25 | B-13 P14, P15 | Classify data, encrypt, strong identity controls including multi-factor authentication | Data classification table, Key Vault, managed identity, MFA on GitHub and Azure | [05](05-data-statement.md), Terraform | 1, 4 |
| REQ-26 | B-13 P16 | Central logging, retention for forensics, anomaly detection | OpenTelemetry to central logs with stated retention | Dashboards | 4, 5 |
| REQ-27 | B-13 P11 to P13 | Monitor capacity, run a disaster recovery programme, test recovery | Stated recovery time and recovery point targets (S3; our wording, B-13 does not use these terms), restore drill | Drill record | 5 |
| REQ-28 | B-13 P10, P17 | Incident playbooks, cyber incident taxonomy, root-cause analysis | Runbook with severity levels and a post-incident template | Runbook | 5 |

## Gaps this table makes visible

1. No independent reviewer (REQ-11, REQ-23). Compensating control: written review checklist and
   automated evidence. Residual risk accepted for a learning project; would not be acceptable in
   an institution.
2. The AI-specific application of E-23 is interpretation (REQ-01, REQ-08, REQ-13).
3. E-21 (Operational Risk Management and Resilience) was issued in final form on 2024-08-22, with full adherence expected by 2026-09-01. It is referenced by E-23, B-10 and B-13; see `A-OSFI-E21` in the register.
