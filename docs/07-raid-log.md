# RAID log

Risks are detailed in [04-risk-register.md](04-risk-register.md); this log tracks the project
items that need an owner and a date.

## Assumptions

| ID | Assumption | Check by |
|---|---|---|
| A-1 | OSFI guideline pages remain publicly available and reproduction for non-commercial learning use is acceptable under OSFI's terms | Phase 1 start |
| A-2 | A hosted model is available at acceptable cost for the cloud demo | Phase 4 start |
| A-3 | The owner can spend about 8-10 hours per week | Weekly |
| A-4 | A 3B-7B local model is adequate for development | Phase 2 |

## Issues

| ID | Issue | Owner | Status |
|---|---|---|---|
| I-1 | FINTRAC page footer terms not seen; B-pack sources blocked | Owner | Open |
| I-2 | OSFI principle and section numbers in the trace are unverified | Owner | Open |
| I-3 | OSFI E-21 final status unconfirmed | Owner | Open |
| I-4 | No independent reviewer assigned | Owner | Open (accepted limitation, R-17) |

## Dependencies

| ID | Dependency | Needed for |
|---|---|---|
| D-1 | GitHub repository `kumarmaddy/bfs-reg-copilot` created | Phase 0 close |
| D-2 | Azure subscription with free credit | Phase 4 |
| D-3 | Kaggle or Colab GPU access | Optional fine-tune |
| D-4 | Client name and cloud (expected within about 10 days) | Adjust ADR-0001 mapping |

## Decisions log

| Date | Decision | Where |
|---|---|---|
| 2026-11-08 | Persona, M1-M3 targets accepted | 02-success-metrics.md |
| 2026-11-08 | Public repository; public data only | ADR-0007 |
| 2026-11-08 | Stack choices | ADR-0001 to 0006 |
| 2026-11-08 | Learning-environment residency exception | ADR-0008 |
