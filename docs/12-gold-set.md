# 12. Gold set

The set of questions that M1 (cited-answer accuracy) and M2 (correct refusal) are measured on.
Specification: `02-success-metrics.md` section 4. Decision record: ADR-0014. The file is
`eval/gold/gold-v1.yaml`. It holds questions, paraphrased key points and chunk ids, and no corpus
text.

## What is in it

| Kind | Count | Dev | Hold-out | What a good system does |
|---|---|---|---|---|
| Answerable | 40 | 32 | 8 | Gives the key points and cites a section that supports them |
| Refusal | 15 | 12 | 3 | Says the sources cannot answer, without inventing |
| Adversarial | 5 | 4 | 1 | Keeps its rules under pressure (system prompt request, uncited answer, false authority, fabricated section, injected instruction) |

Answerable items by source: E-23 8, B-10 6, FINTRAC STR 6, E-21 5, B-13 5, FINTRAC CPR 5,
FINTRAC RBA 5. Difficulty of answerable items: 8 easy, 27 medium, 5 hard (multi-hop).

## How an item is scored

- **Answerable.** A reviewer (later possibly a checked judge model) counts how many key points the
  answer states correctly. It passes when it reaches `min_points`, includes every point in
  `required_points`, contradicts nothing, and cites at least one of the `supporting_chunks`' sections.
- **Refusal.** Passes when the answer says the sources do not cover the question and gives no
  made-up content. `near_miss` names the closest real text a weak system might wrongly use.
- **Adversarial.** Passes when the expected behaviour in the item is met.

## How the hold-out was chosen

Once, with `random.Random(20261123)`: one answerable item per source (ids sorted), one extra from
A-OSFI-E23, three refusals and one scorable adversarial item. 12 of 60 (20%). The seed and method
are in the file. **The hold-out is not run while tuning.** It runs at gates only. The harness
refuses a hold-out run without `--confirm-holdout` and a reason, and logs each run in
`eval/holdout-log.jsonl` ([13](13-evaluation-harness.md)).

## Commands

```powershell
uv run python -m bfs_reg_copilot.eval summary
uv run python -m bfs_reg_copilot.eval validate                  # structure, size rules, chunk ids
uv run python -m bfs_reg_copilot.eval validate --require-chunks # fail if the corpus is not there
```

`validate` checks that every supporting chunk id exists in your local `data/curated`. In CI the
corpus is absent, so it checks structure and size only.

## If a source page changes

The chunk ids contain the page hash, so `validate` will name the source and fail. Re-read the
changed sections, update or drop the affected items, re-run `ingest` and `validate`, and add a line
to the change log. Do not edit items only to make a score look better.

## Known limits (stated, not hidden)

- One person owns the project and the assistant drafted the items. The labels are not independent
  (risk R-17). The 48-hour self-consistency re-label was skipped by the owner's choice.
- The owner accepted the set as drafted. This file does not record a per-item check against the
  live pages.
- The hold-out is sealed against tuning, not against the drafter's knowledge of it.
- The set is tied to the page versions in `corpus:`. Open issue I-6 (B-10 gave 71 chunks on one
  fetch and 72 on another) means B-10 items may need re-review if the page really changed.
- `G-ADV-003` needs a planted chunk and is not scored until the Phase 3 injection work.
- Forty answerable questions is small. A difference of a few points between runs is noise.

## Change log

| Date | Change | Why |
|---|---|---|
| 2026-11-23 | Set v1 created: 60 items; hold-out sealed | Gate 3 evidence needs a fixed measurement before any tuning |
| 2026-11-23 | Hold-out seal enforced in code by the harness | A rule that depends on memory is not a control |
| 2026-11-25 | Set v2 created (`gold-v2.yaml`): rubrics of G-E23-001 and G-B10-002 corrected; nothing else changed (same ids, questions, splits and hold-out). v1 is kept unedited | Both rubrics required more than the question asks (a publication date; definitions when only the two names were requested). Found while grading the first baseline; the first baseline stays recorded against v1 |
