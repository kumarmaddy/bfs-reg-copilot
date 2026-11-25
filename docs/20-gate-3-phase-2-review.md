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

## Experiment 3.1 result (k = 8 against k = 5)

Run 2026-11-25 on the 47 dev items, gold v2, commit c1e27cb, same model (qwen2.5:7b, digest
845dbda0ea48), embedder (bge-m3, digest 790764642607), corpus (fingerprint 624:8a54e9fe360a) and
settings. The only difference is `k`. The rule written above was not changed after the run.
The reference run (k = 5) reproduced the first baseline exactly: all 33 grades carried, same
prompt-token total, so M10 holds.

| Measure | k = 5 (reference) | k = 8 |
|---|---|---|
| M1 cited-answer accuracy | 24/32 = 75% | 25/32 = 78% (95% CI 61% to 89%) |
| M2 correct refusal | 12/12 | 12/12 |
| Over-refusal of answerable questions | 1/32 | 1/32 |
| M4 hit@5 | 30/32 | 30/32 |
| M4 measured over all 8 passages | 30/32 | 31/32 |
| M5 fabricated citations | 0/46 | 0/51 |
| Latency p50 / p95 | 16.1 s / 21.0 s | 20.0 s / 26.2 s |
| Prompt tokens (47 calls) | 67,121 | 100,207 |
| Model time | 673 s | 858 s |

| Rule condition | Result |
|---|---|
| (a) at least 4 fixed and at most 1 broken | **Fail**: 2 fixed (G-CPR-004, G-STR-001), 1 broken (G-RBA-003) |
| (b) M5 stays 0 | Pass |
| (c) over-refusal rises by at most 1 | Pass (1 to 1) |
| (d) p95 at most 32 s | Pass (26.2 s) |

**Verdict: do not adopt k = 8.** Net gain is +1 question, below the four-fixed floor and the
roughly six needed to show an effect on 32 questions. Of the eight questions failing at k = 5, six
still fail: three have unchanged answers (G-B10-001, G-B13-001, G-E21-001) and three changed but
still fail (G-E21-005, G-RBA-002, G-STR-003). So the verdict does not depend on the borderline
grading calls listed below.

**What it shows.**
- More context did not fix incomplete answers. The 7B model summarises instead of listing every
  required item, with the passages already in front of it. This points at the prompt or the model,
  not at retrieval depth.
- The two real fixes: G-CPR-004 now gives the review report and its 30-day limit, and G-STR-001
  now gives the three thresholds the right way round (swapped at k = 5).
- The one break (G-RBA-003) is a borderline grade, see below.
- Retrieval: the "hit@5" line cannot move with `k`, so it hides the effect. Over all 8 passages,
  G-E21-005 is now retrieved (ranks 6 to 8) but its answer still fails; G-STR-003 is still missed.
- Cost of the extra context: 49% more prompt tokens, p50 +4 s, p95 +5 s.

**Grading caveat.** The 19 changed answers were first graded by Claude (draft) against the v2
rubrics; the owner adopted these drafts as the grades of record without re-grading each row, and the borderline calls below have not been checked against the source text. Borderline calls: G-RBA-003
(definition given, but omits the regulatory, reputational, legal and financial considerations;
not credited, which counts as broken), G-STR-004 (omits "with an explanation of the change";
credited), G-B13-003 (adds "background checks", not among the key points; source not yet checked),
G-E21-005 (marked as contradicting because it says E-21 is read with E-21). Crediting G-RBA-003
makes broken 0 and fixed 2: the rule still fails on (a). The graders knew which run was which,
which is a risk of bias. Reported as it is.

**Recorded, not tried.** Retrieval depth between 5 and 8 passages, and a larger k with a
reranker, were not tested. This result covers k = 8 on this model and this prompt only.

### Proposed order after 3.1 (for the owner to approve)

The failure analysis and this result both say the main loss is incomplete answers, which retrieval
changes cannot fix. Retrieval steps can move M1 by at most the two retrieval misses (one now).
Proposal, with the rule for each written before its run:

| Step | What | Why |
|---|---|---|
| 3.2 | **Answer-completeness prompt (v2)**: tell the model to cover every part of the question and list every item the passages give, at k = 5 | Targets the six incomplete answers directly; one change, no extra latency cost |
| 3.3 | **Larger model** (qwen2.5:14b) with the best prompt, if 3.2 leaves M1 short | Tests whether the 7B limit is the cause; latency is the risk (the rule must state a p95 limit) |
| 3.4 | Tune hybrid retrieval and reranker, only if retrieval misses matter after 3.2 and 3.3 | At most one question left to gain |
| 3.5 | Guardrails: block `uncited` answers, refusal floor, prompt-injection scanning (I-5) | Closes M8 coverage and the baseline's known gaps |
| 3.6 | Faithfulness (M6) with a checked judge model | Without it, unsupported additions go uncounted |
| 3.7 | Optional: fine-tuning; eCFR source pack | Only if the targets are still missed |

This changes the order in the table above, so it needs the owner's decision before 3.2 runs.

### Pre-registered rule for 3.2 (prompt v2)

Written 2026-11-25, after experiment 3.1 and **before any run with prompt v2**. The owner approved
the order above on the same day.

**The one change.** `--prompt-version v2` in place of v1, with `k = 5` and everything else
unchanged (model, retriever, seed, temperature, token limit). Prompt v2 replaces "answer
concisely" with a rule that asks for every item the sources state for a list, steps, elements,
criteria, requirements, tools or types, using the sources' names and numbering, with no merged,
dropped or added items, and every part of a multi-part question answered. The refusal, injection
and secrecy rules are word-for-word the same as v1 (a test checks this). The wording was written
from the failure categories in doc 17, not from any one question, and is frozen at merge: if it
changes after a run, that is a new version and a new experiment.

**Reference.** Run `20261125T154349Z-baseline-dev` (k = 5, prompt v1, gold v2): M1 24/32, p95 21.0 s,
0 malformed outputs, M2 12/12, M8 3/3, over-refusal 1/32.

**Questions the change is meant to fix.** The six that fail at k = 5: G-B10-001, G-B13-001,
G-E21-001, G-E21-005, G-RBA-002 and G-STR-003. The last is a retrieval miss and a prompt cannot fix
it. The first three are the strict-rubric items in doc 17, kept as they are, so they may not move
even if the answers improve.

**Adopt v2 only if** all of these hold on the same 32 dev questions:
- (a) at least four questions move from fail to pass and at most one from pass to fail;
- (b) M5 stays at 0;
- (c) the refusal count on answerable questions does not rise by more than one;
- (d) p95 latency is at most 32 s (1.5 times the reference);
- (e) malformed model outputs stay at 0 (longer answers could hit the 512-token limit and cut the
  JSON off);
- (f) M2 stays at 12/12 and M8 at 3/3 (the prompt touches the refusal and injection rules).

`eval flips` checks (a) to (d). Check (e) and (f) by hand in the `score` output and write them in
the record. A net gain under six is "promising, not proven", as for 3.1.

**Tuning budget.** At most two prompt versions (v2 and a possible v3) are tried on these 32 dev
questions. Each version tried on the same questions makes a pass more likely by chance, so after
that, further prompt work waits for the enlarged dev set. A v3 needs a new written rule and the
owner's decision first.

**Grading.** The changed answers are graded against the v2 gold rubrics as in 3.1. The grader knows
which run is which; the record says so.

## Experiment 3.2 result (prompt v2 against v1, k = 5)

Run 2026-11-25 on the 47 dev items, gold v2, commit eddf9e1, same model, embedder and corpus as the
reference. The only difference is `--prompt-version v2`. The rule above was not changed after the
run. The reference is run `20261125T154349Z-baseline-dev` (prompt v1).

| Measure | v1 (reference) | v2 |
|---|---|---|
| M1 cited-answer accuracy | 24/32 = 75% | 23/32 = 72% (95% CI 55% to 84%) |
| M2 correct refusal | 12/12 | 12/12 |
| Over-refusal of answerable questions | 1/32 | 1/32 |
| M4 hit@5 | 30/32 | 30/32 |
| M5 fabricated citations | 0/46 | 0/43 |
| M8 adversarial | 3/3 | 3/3 (graded from the draft) |
| Malformed outputs | 0 | 0 |
| Latency p50 / p95 | 16.1 s / 21.0 s | 16.5 s / 27.0 s |
| Prompt / completion tokens (47 calls) | 67,121 / 3,229 | 70,975 / 3,701 |
| Model time | 673 s | 729 s |

| Rule condition | Result |
|---|---|
| (a) at least 4 fixed and at most 1 broken | **Fail**: 0 fixed, 1 broken (G-RBA-003) |
| (b) M5 stays 0 | Pass |
| (c) over-refusal rises by at most 1 | Pass (1 to 1) |
| (d) p95 at most 32 s | Pass (27.0 s) |
| (e) malformed outputs stay 0 | Pass |
| (f) M2 12/12 and M8 3/3 | Pass |

**Verdict: do not adopt prompt v2.** The six questions that fail at k = 5 and were meant to
improve still fail, except that G-STR-003 and G-E21-005 are retrieval misses a prompt cannot fix.
The result does not depend on the borderline grading calls: crediting every borderline row in v2's
favour fixes at most one question (G-B10-001), against a floor of four.

**What it shows.**
- The model followed the instruction to be complete (completion tokens up 15%), but the failures
  are errors of content, not of length. G-RBA-002 still lists two steps that are not in the cycle.
  G-STR-001 again attributes the "verified facts" definition to reasonable grounds to suspect, which
  is the definition of "believe". G-B10-001 gives examples but no definition. G-CPR-004 still omits
  what the report covers.
- Together with experiment 3.1, this points at the 7B model's reading of the sources as the likely
  limit, not at how much context it gets or how it is asked. That is a hypothesis; step 3.3 tests it.
- Cost: p95 up about 6 s, with no gain.

**Grading caveat.** Drafted by Claude against the v2 rubrics, with the grader aware of which run was
which. Borderline rows: G-B10-001 (no general definition, fails), G-B10-006 (credited for concentration
risk strategies without multi-cloud), G-RBA-003 (omits the four risk types; not credited, counts as
broken), G-B13-003 and G-E23-006 (extra statements not in the key points, source not checked),
G-RBA-004 (extra clause). None of these changes the verdict.

**Tuning budget.** One of the two prompt versions allowed on this dev set is used. The rule above
says a v3 needs a new written rule and the owner's decision first; nothing in this result argues for
spending it.

### Pre-registered rule for 3.3 (larger model)

Written 2026-11-25, after experiments 3.1 and 3.2 and **before any run with the larger model**.
The owner chose on the same day to report latency and not gate on it.

**The question.** Does a larger generator improve M1 on the same questions? Experiments 3.1 and 3.2
suggest the 7B model's reading of the sources is the limit; this tests that.

**The one change.** `--model qwen2.5:14b` in place of `qwen2.5:7b`, with prompt v1, `k = 5` and
everything else unchanged (retriever, seed, temperature, token limit). Prompt v1 is used because v2
was not adopted. The model's digest is recorded in the run's `meta.json`.

**Reference.** Run `20261125T154349Z-baseline-dev` (qwen2.5:7b, prompt v1, k = 5, gold v2): M1 24/32,
0 malformed outputs, M2 12/12, M8 3/3, over-refusal 1/32, p50 16.1 s, p95 21.0 s.

**Latency is reported, not gated.** The owner decided on 2026-11-25 that this
experiment answers "does a bigger model help M1?" and that latency becomes a separate decision in
Phase 4. The 32 s limit of 3.1 and 3.2 is therefore **not** a condition here. `eval flips` is run
with `--max-p95 1000` so its latency line does not gate, and the record reports p50, p95 and model
time against the reference and against the M3 target (10 s p95). A 14b model on this laptop is
expected to miss that target; that is recorded, not hidden. "Adopt" below means "carry the model
forward as the answer-quality candidate for the Phase 4 latency and cost decision", not "make it the
default".

**Adopt the larger model only if** all of these hold on the same 32 dev questions:
- (a) at least four questions move from fail to pass and at most one from pass to fail;
- (b) M5 stays at 0;
- (c) the refusal count on answerable questions does not rise by more than one;
- (d) the run has no errors (a run with errors is repeated, not scored), and malformed outputs stay
  at 0;
- (e) M2 stays at 12/12 and M8 at 3/3.

`eval flips` checks (a) to (c). Check (d) and (e) by hand in the `score` output. A net gain under six
is "promising, not proven". If the rule is met, the next step is the Phase 4 latency decision, with
the cost in seconds per answer stated. If it fails, the 7B model stays and the next experiments are
retrieval (3.4) and guardrails (3.5).

**Limits of the result.** Only this model size is tried. Dev has been looked at three times by now
(3.1, 3.2, 3.3), so a pass is weaker evidence than it looks; the enlarged dev set and the Gate 4
hold-out are where it is confirmed. No other model is tried on dev without a new written rule.

**Grading.** Changed answers are graded against the v2 gold rubrics as before, by a grader who knows
which run is which; the record says so.

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
