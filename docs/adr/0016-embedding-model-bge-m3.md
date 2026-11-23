# ADR-0016: bge-m3 as the embedding model

- Status: Accepted
- Date: 2026-11-23
- Deciders: Project owner

## Context

ADR-0015 fixed the vector size at 1,024 and left the model to be chosen by measurement. Two
candidates fit: `bge-m3` and `qwen3-embedding:0.6b`, both run locally through Ollama. The decision
rule was written into the comparison code before any number was seen: choose the higher dev
hit@5; if the gap is under 5 percentage points, choose the model that embeds faster.

## What was measured

All 624 current chunks (Phase 1 snapshot) embedded with each model. 32 answerable questions from
the **dev** split; the hold-out was not used. A question is a hit when a chunk from a supporting
*section* is among the nearest k by cosine distance (the same rule as metric M4). Machine: ThinkPad
P14s Gen 5, Ollama with the Intel Arc iGPU.

| | bge-m3 | qwen3-embedding:0.6b |
|---|---|---|
| hit@1 | 22/32 (68.8%) | 21/32 (65.6%) |
| hit@3 | 29/32 (90.6%) | 25/32 (78.1%) |
| hit@5 | **30/32 (93.8%)**, 95% CI 80-98% | 28/32 (87.5%), 95% CI 72-95% |
| hit@10 | 31/32 (96.9%) | 30/32 (93.8%) |
| Embedding 624 chunks | 108 s | 126 s |
| Missed at 5 | G-E21-005, G-STR-003 | G-STR-003, G-STR-006, G-RBA-005, G-E23-006 |

## Decision

Use **bge-m3**. The hit@5 gap is 6.2 points, above the 5-point tie margin, so the rule picks the
higher model; it also embedded faster, so the tie-break would have agreed. Embeddings for
`qwen3-embedding:0.6b` stay in the database for now (embeddings are per model) and can be dropped.

## How much weight this carries

- The 6.2-point gap is **two questions** out of 32, and the 95% intervals overlap (80-98% against
  72-95%). The data are consistent with the models being equal at hit@5. The clearer signal is
  hit@3 (29 against 25), where bge-m3 is ahead by four questions.
- The comparison used the Qwen3 query instruction from its model card (unverified here). A different
  instruction could narrow the gap; it was not tuned, to avoid fitting 32 questions.
- Both models miss G-STR-003, so that question deserves a look before anyone blames the model
  (possible causes: a gold-set labelling gap, or a section the chunker split badly).
- Document text was embedded with its heading path in front. Whether that helps was not tested.
- These are retrieval numbers only. They say nothing about answer quality (M1) or refusals (M2).

## Consequences

- bge-m3 is the larger model (about 1.2 GB against 639 MB). On the project machine both fit in
  memory next to the generator; revisit if memory becomes tight in the cloud deployment.
- The retriever (slice 2.5) defaults to bge-m3. The 93.8% hit@5 is a starting point for the
  baseline, not a target: hybrid search and reranking in later slices are judged against it.
- Changing the model later means re-embedding 624 chunks (about two minutes) and re-running
  `compare`; nothing else in the schema changes.

## Revisit when

The corpus grows by an order of magnitude (US eCFR pack), the dev set is extended, retrieval
becomes the bottleneck in the M1 results, or a candidate with a clearly better published result
fits the 1,024-dimension column.
