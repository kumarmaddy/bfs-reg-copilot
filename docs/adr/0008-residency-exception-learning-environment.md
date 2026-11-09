# ADR-0008: Data-residency exception for the learning environment

- Status: Accepted, with expiry conditions
- Date: 2026-11-08
- Deciders: Project owner

## Context

Microsoft documents that global deployment types may process data in any Azure region, data-zone
types process within a data zone, and standard single-region types process in the deployment
region. Community answers on Microsoft's Q&A site say Canadian regional deployments have
historically offered a narrow set of models and that no Canadian data zone existed at the time of
writing **[to verify]**. A bank handling regulated data would avoid global deployments.

All data in this project is public regulatory text and test questions.

## Decision

In the learning environment only, hosted model calls may use a global standard deployment. All
other components (database, storage, compute, logs) stay in Azure Canada Central. The production
variant, described but not built, uses a regional standard or provisioned deployment in a Canadian
region and avoids global standard and global batch types.

## Expiry conditions

This exception ends immediately if any of the following occurs: non-public data is introduced;
the system is shown to or used by a regulated institution; a Canadian regional deployment of a
suitable model becomes available and affordable.

## Alternatives considered

| Option | Why not |
|---|---|
| Only Canadian regional model deployments | The needed model may not be offered there; would block the demo |
| Run an open model on a GPU in Canada | Costs more than the budget allows |
| Local model only in the cloud demo | Weak quality and too slow without a GPU |

## Consequences

- Recorded as risk R-15 with low residual risk.
- The demo and README state the exception plainly.
- This is a real constraint banks face, so it is a good discovery question for the client.

## Revisit when

Any expiry condition occurs, or Microsoft's model-availability page shows Canadian regional
support for a suitable model.
