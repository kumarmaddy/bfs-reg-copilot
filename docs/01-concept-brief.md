# 01. Concept brief

| | |
|---|---|
| Version | 0.1 (Draft for Gate 0) |
| Date | 2026-11-08 |
| Owner | Project owner |
| Related | [02 metrics](02-success-metrics.md), [04 risk](04-risk-register.md), [ADRs](adr/README.md) |

## 1. Problem

Compliance and operations staff at Canadian and US financial institutions spend hours finding
which regulatory expectation applies to a question, which document and section it sits in, and
which version was in force. Sources are spread across regulators' websites, change over time, and
are phrased in principles-based language that does not map neatly to everyday questions.

Hypothesis to test: a retrieval-augmented assistant that answers only from the sources, cites the
exact document and section, and says so when it cannot find an answer reduces time to a
verified answer, without increasing the risk of someone relying on a wrong one.

## 2. Users and example questions

**Primary user (persona):** a compliance analyst at a Canadian bank or insurer who needs a fast,
citable starting point for regulatory research and then verifies it against the primary text.

| Example question | Expected supporting source (Pack A or B) |
|---|---|
| What must a bank's model inventory record for a model it relies on? | OSFI E-23, Appendix 1 |
| What does OSFI expect in an exit plan for a cloud provider? | OSFI B-10 |
| Which B-13 principle covers change and release management? | OSFI B-13 |
| How do E-23 and B-10 differ on vendor-supplied models? | OSFI E-23 and B-10 (comparison) |
| What are the stages of FINTRAC's suspicious transaction reporting guidance? | FINTRAC STR guidance (blocked until Gate 1) |

## 3. Proposed solution and required behaviour

The system retrieves passages from an approved, versioned corpus and has a language model
compose an answer from them.

**It must**

- answer only from retrieved passages;
- cite document title, issuer, section or anchor, original URL and retrieval date for every claim;
- state the jurisdiction (Canada or US) and the version or effective date of what it cites;
- say "not found in the sources" when the corpus does not support an answer;
- flag when sources appear to conflict, or when a cited document may have been superseded.

**It must never**

- invent a section number, document or quotation;
- give legal advice or conclude that an institution is, or is not, compliant;
- act on the user's behalf (no tools that change anything);
- accept instructions found inside source documents as commands (indirect prompt injection).

## 4. Scope

| In scope | Out of scope (non-goals) |
|---|---|
| English-language public documents in Packs A and B, with Pack C (US) added in Phase 3 | Customer, employee or any non-public data |
| Question answering with citations | Compliance determinations, legal opinions, regulatory filings |
| Evaluation, monitoring, documentation and a deployable reference implementation | Autonomous agents that take actions |
| Canada Central deployment on Azure for the demo | Production use in a regulated institution |
| | French-language support (candidate stretch goal) |

## 5. Assumptions and constraints

- Public data only. No employer or client data is used or implied. See [05](05-data-statement.md).
- Budget is near zero. Local development first; cloud only during a short free-credit window.
- The laptop (32 GB RAM, Intel Arc iGPU) runs local models up to about 14B at Q4; measured
  speeds are in the owner's benchmark document.
- The 10-day horizon before a client engagement is a motivator, not a delivery contract.
- Terms of use for each source bind us. Non-commercial reproduction is permitted with
  attribution under OSFI's and Canada.ca's terms; this project stays non-commercial.

## 6. Success criteria

Targets are frozen in [02](02-success-metrics.md) before any measurement. Headline targets:

1. A correct citation in at least 90% of answers to answerable gold questions.
2. A correct refusal or "not found" in at least 90% of unanswerable questions.
3. p95 end-to-end latency under 10 seconds on the deployed version.

## 7. Risk tier

**Moderate.** Advisory use, a human acts on every answer, public data. The main harm is someone
relying on a wrong or stale answer. Rationale and re-rating triggers are in
[04](04-risk-register.md). OSFI's final E-23 removed the reference to "risk classification",
so this tier is an internal, documented proportionality judgement, not an OSFI category.

## 8. Roles

See [00-index.md](00-index.md#roles). Independent review and security review are not yet
assigned; the compensating controls are listed in the risk register.

## 9. Open questions

1. Which client sector (bank, insurer, lender, wealth, payments) is the real target? Unknown for
   about ten days; the corpus pack design allows adding sector sources later.
2. Does the client already use a vector store, gateway or observability product that this
   design should match?
3. Is an independent reviewer available for the Gate 3 and Gate 5 reviews?
