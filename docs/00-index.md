# Documentation index

Project: **bfs-reg-copilot**. Document set version 0.1, dated 2026-11-08. Phase 0 (frame and govern).

## How to use this set

Read in order. Each document states what decision it supports and what would change it. Status
values: **Draft** (written, not yet reviewed), **In review**, **Accepted**, **Superseded**.

| # | Document | Decision it supports | Gate | Status |
|---|---|---|---|---|
| 01 | [Concept brief](01-concept-brief.md) | Should we build this, for whom, and what it must never do | 0 | Draft |
| 02 | [Success metrics](02-success-metrics.md) | What "good" means, frozen before we measure | 0 | Draft |
| 03 | [Requirements trace](03-requirements-trace.md) | Which regulatory expectations we align to and how we evidence them | 0 | Draft |
| 04 | [Risk register and tier](04-risk-register.md) | How risky the system is and what controls that implies | 0 | Draft |
| 05 | [Data statement](05-data-statement.md) | What data we use, how we handle it, and the residency exception | 1 | Draft |
| 06 | [Delivery plan](06-delivery-plan.md) | What gets built when, and what "done" means per phase | 0 | Draft |
| 07 | [RAID log](07-raid-log.md) | Risks, assumptions, issues and dependencies for the project itself | 0 | Draft |
| 08 | [Gate 0 and 1 checklist](08-gate-0-1-checklist.md) | Whether Phase 1 may start | 0, 1 | Draft |
| ADR | [Architecture decision records](adr/README.md) | Why the stack is what it is, and what we rejected | 0 | Draft |

Machine-readable governance lives in [`../data/sources/register.yaml`](../data/sources/register.yaml)
and is validated on every commit.

## Roles

This is a one-person project, so roles are assigned to hats, not people. The limitation is
recorded openly in [04-risk-register.md](04-risk-register.md) (risk R-17).

| Role | Held by | Notes |
|---|---|---|
| Product owner and approver | Project owner | Accepts scope, targets and the release decision |
| Developer | Project owner | Builds and operates the system |
| Independent reviewer (model validation) | **Not yet assigned** | Ideally a peer who did not build the system; until then the review checklist and CI evidence are the compensating control |
| Security reviewer | **Not yet assigned** | Same compensating control: automated scanning plus a written threat review |

## Conventions

- Dates are ISO 8601. The project start date is 2026-11-08.
- Regulatory content is paraphrased, never copied in bulk. Each claim names its source.
- A statement that comes from a tool summary and not from a human reading of the primary text is
  marked **[to verify]** until the owner confirms it.
