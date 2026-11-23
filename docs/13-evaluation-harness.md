# 13. Evaluation harness

Scores a pipeline against the gold set ([12](12-gold-set.md)) and reports the metrics of
[02](02-success-metrics.md). Built before any model exists and tested with test doubles, so the
scorer is trusted before it judges a system.

## What is checked by the machine and what by a person

| Metric | How | Notes |
|---|---|---|
| M1 cited-answer accuracy | Mechanical gate, then a person | An answer fails without a person if it refused, errored, or cited no section that holds the support. The rest are graded by a person against the key points and the item's pass rule |
| M2 correct refusal | Mechanical | Passes when the pipeline's `refused` flag is true. It does not read the text for made-up content |
| M4 retrieval hit@5 | Mechanical | A supporting *section* is among the first 5 retrieved chunks |
| M5 fabricated citations | Mechanical | A cited chunk whose section was not retrieved for that question |
| M8 adversarial | A person (pass or fail) | Reported as "not graded" until graded. `G-ADV-003` is not run (needs a planted chunk) |
| Latency p50 / p95 | Mechanical | Recorded per answer, for information. M3 is measured later, on the deployed version |

Not yet built: M6 faithfulness, M7 cost, M9 provenance completeness, and a judge model. A judge is
only allowed after it agrees with the owner on at least 30 graded items (doc 02 section 5).

Every rate comes with a 95% Wilson interval. With 32 dev questions the interval is wide: a change
of a few points between two runs is noise.

## What a pipeline must provide

```python
class PipelineAnswer:
    text: str
    refused: bool                      # the pipeline's own "cannot answer from the sources"
    cited_chunks: tuple[str, ...]      # chunk ids the answer cites
    retrieved_chunks: tuple[str, ...]  # ranked, best first
```

The generator (slice 2.6) must therefore return a structured answer with an explicit refusal flag
and chunk ids, not only free text. Matching is by section, so citing another chunk of the right
section counts.

## Running it

```powershell
uv run python -m bfs_reg_copilot.eval run --pipeline oracle --out-dir eval/runs   # test double
uv run python -m bfs_reg_copilot.eval grade-sheet eval\runs\<run_id>               # writes grades.csv
uv run python -m bfs_reg_copilot.eval score eval\runs\<run_id>
```

Runs are stored in `eval/runs/<run_id>/` (`meta.json`, `answers.jsonl`, `grades.csv`), which is
git-ignored. `meta.json` records the commit (with `+dirty` if the tree had changes), the hash of the
gold file, the pipeline and its settings, and whether it was a test double. Doubles are labelled
"TEST DOUBLE" in the report and are never results.

**Grading.** Open `grades.csv` in Excel or VS Code. For each answerable row, write the numbers of
the key points the answer states correctly in `points_hit` (for example `1 2 4`; `0` for none), and
`y` in `contradicts` if the answer says something the sources contradict. For each adversarial row
write `pass` or `fail` in `verdict`. A blank cell means not graded yet, and the report says how many
are outstanding. The sheet is never overwritten.

## The hold-out seal

`--split holdout` is refused unless `--confirm-holdout` and `--reason "..."` are given. Each
hold-out run appends one line to `eval/holdout-log.jsonl` (time, run id, pipeline, commit, reason).
That file is committed, so the use of the hold-out is visible in history. Tuning on the hold-out
defeats it; run it at gates only.

## Known limits

- M2 trusts the refusal flag. A pipeline that sets the flag but also writes invented content would
  pass M2; the person grading the answers is the check for that.
- Section-level matching is lenient on M4 and M1 citations. It rewards finding the right section,
  not the exact chunk.
- Latency here is local and informational.
- The doubles prove the arithmetic and the gates. They say nothing about a real system.

## Change log

| Date | Change |
|---|---|
| 2026-11-23 | Harness v1: M1, M2, M4, M5, M8 with doubles, grading sheet, hold-out guard |
