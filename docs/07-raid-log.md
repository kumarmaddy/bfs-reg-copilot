# RAID log

Risks are detailed in [04-risk-register.md](04-risk-register.md); this log tracks the project
items that need an owner and a date.

## Assumptions

| ID | Assumption | Check by |
|---|---|---|
| A-1 | OSFI guideline pages remain publicly available and reproduction for non-commercial learning use is acceptable under OSFI's terms | Phase 1 start |
| A-2 | A 3B-7B local model is adequate for development | Phase 2 |

## Issues

| ID | Issue | Owner | Status |
|---|---|---|---|
| I-1 | FINTRAC page footer terms not seen; B-pack sources blocked | Owner | Open |
| I-2 | OSFI principle and section numbers in the trace are unverified | Owner | Open |
| I-3 | OSFI E-21 final status unconfirmed | Owner | Open |
| I-4 | No independent reviewer assigned | Owner | Open (accepted limitation, R-17) |
| I-5 | Prompt-injection content scanning on ingest deferred (R-06): cleaner drops hidden text, DQ-16 instruction patterns | Owner | Open, Phase 3 |
| I-6 | `A-OSFI-B10` gave 71 chunks on Windows and 72 in the Codespace; compare manifests to see whether the page changed | Owner | Open |

## Dependencies

| ID | Dependency | Needed for |
|---|---|---|
| D-1 | GitHub repository `kumarmaddy/bfs-reg-copilot` created | Phase 0 close |
| D-2 | Azure subscription with free credit | Phase 4 |
| D-3 | Kaggle or Colab GPU access | Optional fine-tune |

## Decisions log

| Date | Decision | Where |
|---|---|---|
| 2026-11-08 | Persona, M1-M3 targets accepted | 02-success-metrics.md |
| 2026-11-08 | Public repository; public data only | ADR-0007 |
| 2026-11-08 | Stack choices | ADR-0001 to 0006 |
| 2026-11-08 | Learning-environment residency exception | ADR-0008 |
| 2026-11-19 | Defer prompt-injection ingest checks to Phase 3 | 11-gate-2-phase-1-review.md |

## Open verifications

| Item | Where | Check before |
|---|---|---|
| B-10 and B-13 effective dates | 03-requirements-trace.md | Phase 5 |
| US federal works public-domain status, per source | 05-data-statement.md | Phase 3 |
| Azure Canadian regional model availability | 05-data-statement.md, ADR-0008 | Phase 4 |
| AKS and VM pricing | ADR-0003 | Phase 4 |
| Write the review checklist and threat review | 00-index.md roles, R-17 | Gates 3 and 4 |
