# ADR-0002: Terraform for infrastructure as code

- Status: Accepted
- Date: 2026-11-08
- Deciders: Project owner

## Context

Infrastructure must be reproducible, reviewable and removable on demand, because the plan relies
on standing the environment up only during the free-credit window and tearing it down afterwards.
Bank platform job postings reviewed list Terraform (or Ansible) with Kubernetes or OpenShift. B-10
expects substitutability and exit planning.

## Decision

Use Terraform with a remote state backend in a private, versioned Azure storage container with
state locking. Organise as small modules (network, cluster, database, registry, secrets,
monitoring) so a module can be re-implemented for another cloud.

## Alternatives considered

| Option | Why not |
|---|---|
| Bicep | Simpler for Azure alone, but it does not carry over to AWS or GCP, which conflicts with ADR-0001 |
| Pulumi | Capable and uses general-purpose languages, but less common in the bank postings reviewed |
| Manual portal setup | Not reproducible or reviewable |

## Consequences

- State must be protected: it can contain sensitive values. Secrets live in Key Vault, not in
  variables or state where avoidable.
- Teardown is one command, which supports cost control (risk R-10).
- A single owner means no real separation of duties on infrastructure changes (risk R-17).

## Revisit when

The client standardises on a different tool, or provider licensing for Terraform changes in a way
that affects the project.
