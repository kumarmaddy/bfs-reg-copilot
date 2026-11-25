# 17. Baseline v1 record (Phase 2)

The first measured result for the whole pipeline, on the **dev split only**. Later changes are
judged against these numbers. The hold-out has not been touched.

| Item | Value |
|---|---|
| Pipeline | dense top-5 (bge-m3, [ADR-0017](adr/0017-dense-only-retrieval-baseline.md)), prompt v1, `qwen2.5:7b` ([ADR-0018](adr/0018-model-gateway-and-baseline-generator.md)) |
| Run | `20261125T100230Z-baseline-dev` (not committed) |
| Code commit | `7d1b4f3158a3bacfc6f2d3da85cdbfffde304afa` |
| Gold set | v1, `bb7ee80afbf6`, dev split: 32 answerable, 12 refusal, 3 adversarial scored (G-ADV-003 skipped: it needs a document fixture, RAID I-5) |
| Settings | temperature 0, seed 20261123, `num_ctx` 8192, k = 5. max_answer_tokens 512. qwen2.5:7b digest 845dbda0ea48 (from the run metadata). The embedding model's digest is not recorded in the run |
| Machine | ThinkPad P14s Gen 5, Intel Arc iGPU via Vulkan, 32 GB RAM, local Ollama |
| Grades | [`eval/baselines/baseline-v1-dev.grades.csv`](../eval/baselines/README.md) |

## Result

| Metric | Result (95% Wilson interval) | Target | Note |
|---|---|---|---|
| M1 cited-answer accuracy | **22/32 = 69%** (51% to 82%) | >= 90% at Gate 3 | Human key-point grading |
| M2 correct refusal | **12/12 = 100%** (76% to 100%) | >= 90% | Mechanical |
| Over-refusal (answerable but refused) | **1/32** | none set | Cost side of M2; G-STR-003 |
| M4 retrieval hit@5 | **30/32 = 94%** (80% to 98%) | >= 90% (proposed) | Section level |
| M5 fabricated citations | **0/46** | <= 1% | Mechanical |
| M8 adversarial | **3/3** (44% to 100%) | 0 successes | Manual, 3 items |
| Errors / malformed outputs | 0 / 0 | | |
| Latency | p50 16.1 s, p95 21.6 s | M3 < 10 s (deployed, 100 requests) | Laptop; not comparable to M3 |

How to read it: 32 questions is a small sample, so the interval on M1 is about 31 points wide.
A change of a few questions is within noise. Do not claim an improvement from fewer than about
five questions' difference on dev. M2 is 100% but only 12 items, so its interval still starts at 76%.

## What failed (10 of 32 M1 questions)

| Cause | Items | What it means |
|---|---|---|
| Incomplete answer | E21-001, B10-001, B10-002, B13-001, CPR-004, E23-001 | Quotes the top chunk faithfully but gives only the points in that chunk |
| Wrong content | STR-001, RBA-002 | STR-001 swaps the "suspect" and "believe" definitions; RBA-002 lists steps that are not the RBA cycle. Both cite real chunks |
| Retrieval miss | E21-005, STR-003 | The supporting section is not in the top 5. STR-003 was then refused |

Two failures are defects in gold v1 rubrics, not in the system: **G-E23-001** requires the
publication date although the question asks only when the guideline takes effect, and
**G-B10-002** lists definitions as key points although the question asks only for the two names.
They are left as graded. Gold v1 is not edited after a result is seen. With both treated as
passes the figure would be 24/32 = 75%; this is a sensitivity check, not the result. Fix them in a
labelled gold v2 and re-baseline.

## What the numbers do not show

- **A cited answer can still be wrong.** M5 only checks that the cited section was retrieved.
  STR-001 and RBA-002 pass M5 and fail M1.
- **Faithfulness is not measured** (M6 is not built). RBA-004 adds advice that is not in the
  source and nothing flags it.
- **Grader independence.** The grades were drafted by Claude and are applied as recorded.
  Owner review of the flagged rows (STR-001, RBA-002, B10-002, E23-001, B13-001 and the three
  adversarial items): **confirmed by the owner on 2026-11-25**, who read the flagged rows and agreed with the draft grades.
- **The first run of this baseline had one errored item** (G-STR-002: Ollama dropped an embedding
  connection). The embedder now retries transient failures. This run is the re-run; the other 31
  answers (text, citations and refusal flag) were identical to the first run, which supports M10 (reproducibility) on this
  machine at temperature 0.
- Dev only. Hold-out numbers come at Gate 3.

## Next

Improvement ideas (more context per question, a reranker, smaller chunks, query rewriting, tuned
hybrid retrieval, M6 faithfulness) belong to Phase 3. Each is judged on dev against this record
with its decision rule written before the run.

## Rescored under gold v2 (2026-11-25)

Decision D-2 of the [Gate 3 review](20-gate-3-phase-2-review.md). **Same run, same answers.** Only
the grading rubric of two items changed, in `eval/gold/gold-v2.yaml`. Gold v1 is kept unedited and
the v1 result above stays as recorded. Manifest and grades: `eval/baselines/baseline-v2-dev.*`.

| Item | What v1 required | What v2 requires | Why |
|---|---|---|---|
| G-E23-001 (when does E-23 take effect) | The effective date and the publication date | The effective date | The question does not ask when it was published |
| G-B10-002 (the two forms of concentration risk) | Both definitions | Both forms named | The question asks for the two names |

| | Gold v1 | Gold v2 |
|---|---|---|
| M1 cited-answer accuracy | 22 of 32 = 69% (51% to 82%) | **24 of 32 = 75% (58% to 87%)** |
| M2, M4, M5, M8 | unchanged | unchanged |

**This was done after seeing the answers**, which is the risk the gold-set rules warn about. The
corrections are limited to the two cases where a key point asked for something the question did
not, and both answers gave exactly what was asked.

### Rubrics that look strict but were not changed

A read-through of all 32 dev rubrics for the same pattern found four more that an owner could
reasonably call over-demanding. They were **not** changed, because loosening rubrics one by one
after seeing which answers failed is how a score gets flattered. They are recorded here so the
strictness is visible:

| Item | Strict point | Baseline answer |
|---|---|---|
| G-B10-001 | Examples of third parties (at least three) when the question asks what counts and what is excluded | Definition and both exclusions, no examples |
| G-E21-001 | "Tolerances are typically greater than risk appetite" when the question asks for the difference | Both definitions, no relationship |
| G-CPR-004 | Three of four points, when the question asks two things (how often, and to whom) | Both asked things answered |
| G-B13-001 | Example roles (head of IT, CISO) alongside senior-management accountability | Senior management assigns to senior officers; no roles |

Sensitivity only, not a result: relaxing the first three would give M1 27 of 32 (68% to 93%);
adding G-B13-001, 28 of 32. The strict standard is defensible, since these are list questions where
the source's full list is the expected answer, and it affects every later version equally. The
read-through was done by the drafter, not an independent reviewer, and found no rubric that is too
lenient. Any of the four can still be changed by the owner, in a new gold version before the first
Phase 3 run.
