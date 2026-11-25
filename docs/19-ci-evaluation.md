# 19. Evaluation in CI

Phase 2's exit criterion asks that a small evaluation runs in CI. This is what that means, and
what it does not.

## What CI checks

Every push and pull request runs these without a model or a database of real data:

| Check | Where | Catches |
|---|---|---|
| Gold set structure (`eval validate`) | CI step | A broken or inconsistent gold file |
| Each test double on a fixed 9-question subset (3 per kind, first by id) | `tests/test_ci_subset.py` | The scorer, report or command line changing behaviour: the oracle must score 100% on M2 and M4, the always-refuse double 0% on M1 and 100% on M2, the uncited double 0% on M1, the fabricating double 100% on M5 |
| Full dev set with every double | `tests/test_eval_harness.py` | The same, on all 47 dev questions |
| One real run of the command line | CI step | A broken entry point on Linux |
| The recorded baseline's gold hash | `tests/test_baseline_record.py` | **Editing the gold set after a baseline was measured** |
| The recorded baseline's M1, M8 and grades | `tests/test_baseline_record.py` | The numbers in [doc 17](17-baseline-v1.md) drifting away from the committed grades |

## What CI does not check

**CI does not measure answer quality.** It has no local model, so the real pipeline is never run
there. A green CI means the measuring instrument works and the recorded baseline is consistent. It
does **not** mean the model's answers are good, or have not got worse. Quality is measured by
running the baseline on the project machine ([doc 16](16-generator.md)) and recording it as in
doc 17.

## When a check fails

- **"The gold file changed after baseline v1 was recorded."** Do not edit `gold-v1.yaml` to make
  the test pass. Add a labelled gold v2 (rubric fixes such as G-E23-001 and G-B10-002 belong
  there), re-run the baseline against it, record it, and add its manifest next to the v1 one.
  Keep the v1 files: they are the evidence for the older number.
- **The M1 re-derivation fails.** The grades file and the manifest disagree. Fix whichever is
  wrong and say why in the commit; do not change both to match.

## Recording a new baseline

1. Run the pipeline on dev and grade it (docs 13 and 17).
2. Commit the grades as `eval/baselines/<name>.grades.csv` and a manifest
   `eval/baselines/<name>.json` with the run id, commit, gold hash, model digest and results.
3. Add a test, or extend `tests/test_baseline_record.py`, so the new record is checked too.
4. Write the record doc, with the owner's review stated.
