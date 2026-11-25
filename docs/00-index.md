# Documentation index

Project: **bfs-reg-copilot**. Document set version 0.4, dated 2026-11-23. Phases 0 and 1 complete; Phase 2 (baseline RAG and evaluation) in progress.

## How to use this set

Read in order. Each document states what decision it supports and what would change it. Status
values: **Draft** (written, not yet reviewed), **In review**, **Accepted**, **Superseded**.

| # | Document | Decision it supports | Gate | Status |
|---|---|---|---|---|
| 01 | [Concept brief](01-concept-brief.md) | Should we build this, for whom, and what it must never do | 0 | Accepted |
| 02 | [Success metrics](02-success-metrics.md) | What "good" means, frozen before we measure | 0 | In review |
| 03 | [Requirements trace](03-requirements-trace.md) | Which regulatory expectations we align to and how we evidence them | 0 | Accepted |
| 04 | [Risk register and tier](04-risk-register.md) | How risky the system is and what controls that implies | 0 | Accepted (see the note below) |
| 05 | [Data statement](05-data-statement.md) | What data we use, how we handle it, and the residency exception | 1 | Accepted |
| 06 | [Delivery plan](06-delivery-plan.md) | What gets built when, and what "done" means per phase | 0 | Accepted |
| 07 | [RAID log](07-raid-log.md) | Risks, assumptions, issues and dependencies for the project itself | 0 | Accepted |
| 08 | [Gate 0 and 1 checklist](08-gate-0-1-checklist.md) | Whether Phase 1 may start | 0, 1 | Accepted |
| 09 | [Data-quality checks](09-data-quality-checks.md) | What must be true of every chunk before it is used | 2 | Accepted |
| 10 | [Running the ingest DAG](10-orchestration.md) | How to run and verify the Airflow pipeline | 2 | Accepted |
| 11 | [Gate 2: Phase 1 review](11-gate-2-phase-1-review.md) | Whether Phase 2 may start | 2 | Draft |
| 12 | [Gold set](12-gold-set.md) | What M1 and M2 are measured on, and its limits | 3 | Draft |
| 13 | [Evaluation harness](13-evaluation-harness.md) | How answers are scored, and what a person must grade | 3 | Draft |
| 14 | [Database](14-database.md) | How to run the local database, the schema, and what loading does | 3 | Draft |
| 15 | [Retrieval](15-retrieval.md) | The three retrievers, how to try them, and the rule for adopting hybrid | 3 | Draft |
| 16 | [Generator](16-generator.md) | How the baseline answers, how to run it, and how to read the first results | 3 | Draft |
| 17 | [Baseline v1 record](17-baseline-v1.md) | The first measured M1, M2, M4 and M5 on dev, and what to compare later changes against | 3 | Draft |
| 18 | [The API](18-api.md) | How to run the API, what it returns, and its limits | 3 | Draft |
| 19 | [Evaluation in CI](19-ci-evaluation.md) | What the CI evaluation checks, and what it cannot | 3 | Draft |
| 20 | [Gate 3: Phase 2 review](20-gate-3-phase-2-review.md) | Whether Phase 3 may start | 3 | Draft |
| 21 | [Running an experiment](21-running-experiments.md) | How a Phase 3 change is tested and compared against the baseline | 4 | Draft |

| ADR | [Architecture decision records](adr/README.md) | Why the stack is what it is, and what we rejected | 0 | Accepted |

Machine-readable governance lives in [`../data/sources/register.yaml`](../data/sources/register.yaml)
and is validated on every commit.

## Roles

This is a one-person project, so roles are assigned to hats, not people. The limitation is
recorded openly in [04-risk-register.md](04-risk-register.md) (risk R-17).

| Role | Held by | Notes |
|---|---|---|
| Product owner and approver | Project owner | Accepts scope, targets and the release decision |
| Developer | Project owner | Builds and operates the system |
| Independent reviewer (model validation) | **None. Accepted limitation (2026-11-18)** | Single-owner pilot. Compensating control: written review checklist, automated CI evidence, and a peer review requested at Gates 3 and 5 if one is available. Recorded as risk R-17 |
| Security reviewer | **None. Accepted limitation (2026-11-18)** | Same compensating control: automated scanning plus a written threat review. Recorded as risk R-17 |

## Conventions

- Dates are ISO 8601. The project start date is 2026-11-08.
- Regulatory content is paraphrased, never copied in bulk. Each claim names its source.
- A statement that comes from a tool summary and not from a human reading of the primary text is
  marked **[to verify]** until the owner confirms it.
| 21 | [Running an experiment](21-running-experiments.md) | How a Phase 3 change is tested and compared against the baseline | 4 | Draft |
