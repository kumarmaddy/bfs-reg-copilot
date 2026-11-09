# ADR-0001: Azure (Canada Central) as primary cloud, with a portable design

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner (product owner and developer roles)

## Context

- Canadian banks use more than one cloud. Reporting from 2021 says CIBC signed with Azure,
  Scotiabank with Google Cloud and BMO with AWS. A third-party technology-stack aggregator
  (medium reliability) says RBC uses Azure and Databricks and that Scotiabank named Google Cloud
  its enterprise cloud of choice in 2024. Nothing was found for TD.
- OSFI's third-party guideline B-10 expects exit and contingency plans and asks institutions to
  consider cloud portability and concentration risk. The 2021 draft tech guidance reported in
  the press said the same about exit strategies.
- Microsoft Foundry is available in Canada Central and Canada East, and the owner intends to use
  the Azure free-credit window.

## Decision

Use Azure, region Canada Central, as the primary cloud for the demonstration. Keep the design
portable: infrastructure in Terraform, compute on Kubernetes, retrieval in PostgreSQL, telemetry
through OpenTelemetry, and all model calls through a gateway. Cloud-specific services appear only
behind our own interfaces and in the infrastructure modules.

## Alternatives considered

| Option | Why not |
|---|---|
| AWS | Equally valid and used by at least one large Canadian bank. No credit, budget or client preference favours it today |
| Google Cloud | Same as AWS; Scotiabank's choice makes it a strong candidate if the client uses it |
| Multi-cloud deployment now | Doubles the work and cost for a learning project. Portability by design gets most of the value |

## Consequences

- Faster path to a hosted model and managed identity, which matches the owner's plan.
- If the client runs another cloud, only the infrastructure module and the model-provider
  adapter change. Mapping table: concept brief and stack discussion, summarised in the README.
- We must resist convenient Azure-only shortcuts in application code.

## Revisit when

The client names its cloud, or OSFI's final guidance on cloud portability changes materially.
