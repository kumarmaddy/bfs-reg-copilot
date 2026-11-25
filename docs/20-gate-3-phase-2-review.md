# Gate 3: Phase 2 review (baseline RAG and evaluation)

Review of Phase 2 against the exit criteria in `06-delivery-plan.md`. Tick an item only when the
evidence exists. "Owner" items cannot be done by the assistant.

**Result: conditional go.** Reviewed 2026-11-25. On the same day the owner accepted the
recommendations on D-1, D-2 and D-3 below. Both exit criteria are met and evidenced, and nothing
found blocks Phase 3. Phase 3 may start once the four conditions under "Conditions for starting
Phase 3" are met. C-1 to C-3 were met on 2026-11-25. C-4 (slice 3.0) remains and must be done
before the first Phase 3 run.

## Exit criteria

| # | Exit criterion | Evidence | Done |
|---|---|---|---|
| G3-1 | M1 and M2 measured on the dev split and recorded | Run `20261125T100230Z-baseline-dev`: M1 22 of 32, M2 12 of 12, M4 30 of 32, M5 0 of 46, M8 3 of 3 scored, 0 errors. Grades committed in `eval/baselines/`; record in [doc 17](17-baseline-v1.md); grades confirmed by the owner on 2026-11-25 | [x] |
| G3-2 | A small evaluation subset runs in CI | Nine-question subset (3 per kind) with each of five test doubles, `eval validate`, and one command-line run, in CI ([doc 19](19-ci-evaluation.md)). **This checks the measuring instrument, not answer quality** | [x] |
| G3-3 | An answer with citations works end to end | API smoke test on the owner's machine, 2026-11-25: the E-23 effective-date question returned the right answer with a verified citation (URL, retrieval time, page-version hash) in 15 s. Failure path checked: with Ollama stopped the API returned `503 dependency_unavailable` and recovered without a restart | [x] |
| G3-4 | Gold set of at least 60 questions | 60 items: 40 answerable, 15 refusal, 5 adversarial; 48 dev and 12 hold-out ([doc 12](12-gold-set.md)) | [x] |
| G3-5 | **Owner:** the hold-out has not been run | The harness refuses a hold-out run without a flag and a reason and logs each one in `eval/holdout-log.jsonl`. The assistant has not seen that file. Check: `Test-Path eval\holdout-log.jsonl`. Owner check 2026-11-25: `Test-Path eval\holdout-log.jsonl` returned `False`, so no hold-out run has been logged | [x] |
| G3-6 | No corpus text in git | Recorded grades hold ids, point numbers and short notes only. DQ-15 still fails if a file outside `data/sources/` is tracked | [x] |

Checks of the code at the time of review: 361 tests passed and 1 skipped (Airflow is not
installed) on the owner's machine; ruff, format and mypy clean on 82 files; CI `check` green on
the merge of every Phase 2 pull request.

## Planned work, as built

| Planned (06) | Built | Record |
|---|---|---|
| pgvector schema | Plain-SQL migrations, one chunk table, embeddings per model at 1,024 dimensions | ADR-0015, doc 14 |
| Embedder | Local bge-m3 through Ollama; chosen over qwen3-embedding 0.6b on dev hit@5 (93.8% against 87.5%) | ADR-0016 |
| Retriever | Dense top-5 baseline. Hybrid (RRF) built and compared on dev: 28 of 32 against 30 of 32 for dense, so it is off by default | ADR-0017, doc 15 |
| Generator via gateway | One gateway interface, local `qwen2.5:7b`, structured answers, sources treated as data | ADR-0018, doc 16 |
| API | `/ask`, `/health`, `/ready`; citations with lineage; local only | ADR-0019, doc 18 |
| Gold set (60 or more) | 60 items, sealed hold-out | ADR-0014, doc 12 |
| Eval harness | M1, M2, M4, M5, M8 with Wilson intervals, grading sheet, hold-out guard | doc 13 |

## What the baseline shows

| Cause of the 10 failed M1 questions | Items | Share |
|---|---|---|
| Incomplete answer (right content, missing points) | 6 | 6 of 10 |
| Wrong content | 2 | 2 of 10 |
| Retrieval miss | 2 | 2 of 10 |

Two of the six "incomplete" failures are partly rubric defects (G-E23-001, G-B10-002; see D-2).
Over-refusal was 1 of 32. Faithfulness (M6) is not measured, so unsupported additions are not
counted anywhere. Whether the tables-flattened-to-lines decision from Phase 1 caused any failure
has **not been analysed**; do that at the start of Phase 3.

## Deviations from the measurement protocol (`02-success-metrics.md`, section 5)

| Protocol says | What was done | Consequence |
|---|---|---|
| Results are tracked in MLflow | Results are files plus a record document and a manifest | Acceptable for one person; revisit if runs multiply in Phase 3 |
| Every run logs corpus version and hashes, and the embedding model and version | A run logs the retriever name (`dense:bge-m3`) but not the embedding model's digest or a corpus hash | A re-pulled embedding model, or a re-loaded corpus, would not show in the run record. **Fix before Phase 3 runs** (small harness change) |
| A judge model scales M5 and M6 after 85% agreement with human labels | Not built; M5 is mechanical, M6 is absent | Planned for Phase 3 |
| Label by the owner from the primary text; re-label 15 items after 48 hours | The assistant drafted items and the M1 grades; the owner confirmed them. The re-label was skipped by the owner's choice | Known limit (R-17); every M1 figure inherits it |

The one measured sign of **reproducibility (M10)**: a re-run of the baseline reproduced 31 of 31
unchanged answers exactly (text, citations, refusal flag) on one machine at temperature 0.
That is one repeat, on one machine; it does not yet show agreement "within 2 points" across
conditions.

## Found by running it, not by reading it

- The first full baseline run had one error: Ollama dropped an embedding connection. The embedder
  now retries transient failures.
- `score` treated a missing `--grades` file as "no grades" and printed a plausible but empty
  result. A missing explicit path is now an error.
- CI runs mypy over the tests; the assistant's local check covered only the source. Use plain
  `mypy`, as CI does.
- Odd characters in answers (`â`) were a Windows PowerShell display problem. The database holds
  the correct characters (checked by code point).
- Doc 02 and doc 06 disagree about which gate first uses the hold-out (see D-1).

## Carried forward

| Item | Status | Where it goes |
|---|---|---|
| Prompt-injection scanning of source text; `G-ADV-003` is skipped because it needs a fixture, so M8 covers 3 of the 4 dev adversarial items | Open (RAID I-5) | Phase 3 guardrails |
| `A-OSFI-B10` chunk count differs between machines (71 against 72) | Open (RAID I-6) | Owner; compare manifests |
| API has no authentication, TLS or rate limit; one request at a time | Open (RAID I-7) | Phase 4 |
| Baseline p95 latency 21.6 s on the laptop against the M3 target of 10 s, which is measured on a deployed service | Open (RAID I-8, R-12) | Decide model and hardware at Phase 4 start |
| The run folder (`eval/runs/`) is not in git; the baseline answers exist only on the owner's laptop | New | Owner: keep a private backup. The grades alone cannot reproduce the answers |
| Answers can be returned as `uncited` (answered, but nothing verified) | By design for the baseline | Phase 3 guardrail |
| Docs 12 to 20 are still marked Draft | New | Owner: accept or revise at this gate |

## Decisions for the owner

| # | Decision | Recommendation | Owner decision (2026-11-25) |
|---|---|---|---|
| D-1 | **When is the hold-out first run?** Doc 02 says it is sealed "until Gate 3" and doc 06 puts the M1 and M2 hold-out target in Phase 3, whose gate is 4 | Do **not** run it now. The baseline is untuned and was never expected to meet the targets; the hold-out has only 12 items, and each use spends its value. Run it once, at Gate 4, against the Phase 3 release candidate. Record the change in doc 02 section 6 with a dated note (wording below) and correct "Hold-out at Gate 3" in the M1 row and the split rule | **Accepted.** The doc 02 edit is still to be made |
| D-2 | **Gold v2:** fix the two rubric defects (G-E23-001, G-B10-002) and consider more items | Do it **once, before any Phase 3 run**, so that every comparison uses one rubric. Re-score the stored baseline answers under v2 (the answers do not change; only two grading decisions do) and record that as baseline v2, keeping the v1 files. Dev has only 32 answerable questions: see the sample-size point below | **Accepted.** Done in slice 3.0 |
| D-3 | **Go or no-go for Phase 3** | Conditional go, once D-1 and D-2 are settled and the run-metadata fix (embedding digest, corpus hash) is made | **Accepted:** conditional go |
| D-4 | **Peer review.** Risk R-17 says to request a peer review at Gates 3 and 5 | Ask one person to read docs 17 and 20 and the flagged grades, or record here that none is available | **Recorded: none available (2026-11-25).** Single-owner project; the accepted limitation in R-17 stands, and R-17 asks again at Gate 5 |

Proposed doc 02 section 6 line for D-1:
`| 2026-11-25 | The hold-out is first run at Gate 4 (end of Phase 3), once per release candidate, not at Gate 3 | Baseline is untuned and not expected to meet targets; doc 06 already places the hold-out target in Phase 3 | Project owner |`

## Sample size: what dev can and cannot show

With 32 answerable dev questions, a comparison of two versions on the same questions is
decided by how many questions flip. If version B fixes *n* questions and breaks none, an exact
two-sided sign test gives p of about 0.25 for 3 fixes, 0.06 for 5, and 0.03 for 6. So a Phase 3
change must fix about **six** questions with no regressions before dev can call it a real
improvement. Smaller gains are direction, not proof. The sign test counts only the questions that
flip, so more questions do not lower the six. What more questions do is make the same six flips a
smaller share of the set: six of 32 is a 19-point gain, six of 64 is 9 points. So a larger gold
set lets smaller real improvements be detected, and that is the main argument for enlarging it in
v2 (D-2). Any added items must be written from the primary text before the system is run on them.

## Proposed order for Phase 3

Chosen from the failure analysis, not from preference. Each experiment's decision rule is
written here, **before any run**: no retrieval depth, reranker or prompt change has been tried
on dev yet.

| Step | What | Why |
|---|---|---|
| 3.0 | Gold v2; add embedding digest and corpus hash to run metadata; back up the run folder | Fixes the yardstick before using it (D-2) |
| 3.1 | **More context per question**: retrieve 8 passages instead of 5, with the same everything else | Six of ten failures are incompleteness. Cheapest change that addresses the main failure |
| 3.2 | Tune hybrid retrieval | Hybrid is already built; its keyword side lost to dense on dev (28 against 30), so tune it before judging it |
| 3.3 | Reranker | Addresses the two retrieval misses and ranking of extra context |
| 3.4 | Guardrails: block `uncited` answers, refusal floor, prompt-injection scanning (I-5) | Closes M8 coverage and the baseline's known gaps |
| 3.5 | Faithfulness (M6) with a checked judge model | Without it, unsupported additions go uncounted |
| 3.6 | Optional: fine-tuning; eCFR source pack | Only if the targets are still missed |

**Pre-registered rule for 3.1** (written 2026-11-25, before any run with 8 passages): adopt k = 8
only if, on the same dev questions, (a) at least four questions move from fail to pass and at most
one moves from pass to fail, (b) M5 stays at 0, (c) the refusal count on answerable questions does
not rise by more than one, and (d) p95 latency stays at or below 32 s (1.5 times the baseline).
Report the flips by question, not only the totals. If (a) is met but the gain is under six, record
it as "promising, not proven" and re-test on the enlarged v2 dev set. The context window (8,192
tokens) limits how far k can go; the gateway refuses prompts that do not fit.

## Conditions for starting Phase 3

| # | Condition | State |
|---|---|---|
| C-1 | G3-5: the owner confirms the hold-out has not been run (`Test-Path eval\holdout-log.jsonl` gives `False`, or the file has no entries) | [x] 2026-11-25: `False` |
| C-2 | D-4: the peer-review outcome is written into the table above | [x] 2026-11-25: none available |
| C-3 | D-1: doc 02 is edited (change-log line, the M1 row and the split rule now say Gate 4) | [x] 2026-11-25 |
| C-4 | Slice 3.0 is done before the first Phase 3 run: gold v2, embedding digest and corpus hash in run metadata, and a private backup of `eval/runs/` | [ ] |

## Next

Merge this review, then slice 3.0. When C-1 to C-3 are ticked and this document is merged, create
the `phase-2-complete` tag. Slices 3.1 onward run only after C-4.
