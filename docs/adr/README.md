# Architecture decision records

Each record states the context, the decision, the alternatives we rejected and why, and what
would make us revisit it. Format: a short adaptation of MADR. Template: [0000](0000-template.md).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-cloud-azure-portable-design.md) | Azure (Canada Central) as primary cloud, with a portable design | Accepted |
| [0002](0002-terraform-for-infrastructure.md) | Terraform for infrastructure as code | Accepted |
| [0003](0003-kubernetes-for-compute.md) | Kubernetes (kind locally, AKS in Azure) with Helm | Accepted |
| [0004](0004-postgres-pgvector-for-retrieval.md) | PostgreSQL with pgvector and full-text search for retrieval | Accepted |
| [0005](0005-langchain-behind-interfaces.md) | LangChain used only inside adapters behind our own interfaces | Accepted |
| [0006](0006-litellm-model-gateway.md) | LiteLLM as the model gateway | Accepted |
| [0007](0007-public-data-only-no-corpus-in-repo.md) | Public data only; no corpus text in the repository | Accepted |
| [0008](0008-residency-exception-learning-environment.md) | Data-residency exception for the learning environment | Accepted, with expiry conditions |

"Accepted" here means accepted by the project owner at Gate 0 on 2026-11-08. Evidence quoted from
news articles, job postings and aggregator sites is indicative, not authoritative.
