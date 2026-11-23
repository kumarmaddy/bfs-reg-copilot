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
| [0009](0009-polite-register-gated-fetching.md) | Register-gated, polite fetching | Accepted |
| [0010](0010-raw-storage-content-addressed.md) | Raw storage is content-addressed with an append-only manifest | Accepted |
| [0011](0011-cleaning-keeps-main-content-and-headings.md) | Cleaning keeps main content and heading structure | Accepted |
| [0012](0012-section-aware-chunking.md) | Section-aware chunking with verbatim, traceable chunks | Accepted |
| [0013](0013-airflow-orchestration-thin-dag.md) | Airflow orchestrates a thin DAG over tested plain-Python stages | Accepted |
| [0014](0014-gold-set-labelling-and-sealed-holdout.md) | Gold set drafted from primary text, accepted by the owner, hold-out sealed by rule | Accepted |
| [0015](0015-storage-schema-and-embedding-size.md) | Plain-SQL migrations, one chunk table, embeddings per model at 1024 dimensions | Accepted |
| [0016](0016-embedding-model-bge-m3.md) | bge-m3 as the embedding model, chosen on dev-split hit@5 | Accepted |
| [0017](0017-dense-only-retrieval-baseline.md) | Dense-only retrieval is the baseline; hybrid is built but off | Accepted |
| [0018](0018-model-gateway-and-baseline-generator.md) | One model gateway, structured answers, and a baseline generator | Accepted |

"Accepted" here means accepted by the project owner at Gate 0 on 2026-11-08. Evidence quoted from
news articles, job postings and aggregator sites is indicative, not authoritative.
