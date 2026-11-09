# ADR-0003: Kubernetes (kind locally, AKS in Azure) with Helm

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner

## Context

Banks run workloads on Kubernetes or OpenShift. One bank job posting reviewed describes an
on-premises OpenShift environment for GenAI guardrails and observability; another lists
Kubernetes or OpenShift with Docker. The budget is near zero, and AKS node costs are not covered by an always-free allowance
**[to verify the current AKS and VM pricing before Phase 4]**.

## Decision

Package services as containers and deploy with Helm. Run locally on `kind` for all development
and tests. Deploy to AKS only during a short window inside the free-credit period for the demo
and the load test, then tear down with Terraform.

## Alternatives considered

| Option | Why not |
|---|---|
| Azure Container Apps | Less effort, but hides the platform concerns a bank team deals with |
| Azure Functions / App Service | Good free allowances, but not how a bank GenAI platform is usually run |
| Docker Compose only | Fine for development; does not demonstrate scaling, probes or deployment strategy |

## Consequences

- More moving parts, so operational docs and a runbook matter more.
- Local parity: the same Helm chart runs on `kind` and AKS, with different values files.
- Autoscaling and rollout behaviour can be demonstrated and load-tested.

## Revisit when

AKS cost exceeds the credit window, or the client's platform is OpenShift (then adapt the chart).
