# Gate 0 / Gate 1 checklist

Tick an item only when the evidence exists. "Owner" items cannot be done by the assistant.

## Gate 0: is this worth doing, and is it framed correctly?

| # | Check | Evidence | Done |
|---|---|---|---|
| G0-1 | Problem, persona and non-goals written | 01-concept-brief.md | [x] |
| G0-2 | Metrics with targets and a measurement protocol | 02-success-metrics.md | [x] |
| G0-3 | Risk tier assigned with rationale and re-rating triggers | 04-risk-register.md | [x] |
| G0-4 | Requirements mapped to controls and phases | 03-requirements-trace.md | [x] |
| G0-5 | Public-data-only rule and residency exception recorded | ADR-0007, ADR-0008, 05-data-statement.md | [x] |
| G0-6 | **Owner:** open each OSFI guideline and confirm the principle and section numbers marked `[to verify]` | Edited 03-requirements-trace.md | [ ] |
| G0-7 | **Owner:** assign an independent reviewer, or record the limitation as accepted | 00-index.md roles | [ ] |

## Gate 1: is the foundation safe to build on?

| # | Check | Evidence | Done |
|---|---|---|---|
| G1-1 | Source register exists, validates in CI, blocks unverified sources | `reg-register validate` | [x] |
| G1-2 | **Owner:** open the FINTRAC pages, read the footer terms, update the register | Register entries B-FINTRAC-* | [ ] |
| G1-3 | Repository scaffold with lint, types, tests, CI, dependency and code scanning | ci.yml, codeql.yml, dependabot.yml | [x] |
| G1-4 | No corpus text in the repository | .gitignore, ADR-0007 | [x] |
| G1-5 | Delivery plan, cut order, RAID log | 06, 07 | [x] |
| G1-6 | Create the GitHub repo, push, confirm CI is green | Green ci run on main, 2026-11-10 | [x] |
| G1-7 | Enable branch protection and secret scanning on the repo | Ruleset protect-main; secret scanning and push protection on | [x] |

## Result

Gate 0 and Gate 1 pass when every row is ticked. Open owner items do not block starting Phase 1
reading, but **ingestion of any source must wait for its register entry to be verified**.
