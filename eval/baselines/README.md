# Recorded baselines

Human grades for a recorded evaluation run, kept so the number in the docs can be re-derived.
Grades hold item ids, key-point numbers and short notes only: no answer text and no source text
([ADR-0007](../../docs/adr/0007-public-data-only-no-corpus-in-repo.md)).

Re-score from a run folder (the run itself is not committed):

```powershell
uv run python -m bfs_reg_copilot.eval score <run_dir> --grades eval\baselines\baseline-v1-dev.grades.csv
```

| File | Run | Commit | Gold | Result |
|---|---|---|---|---|
| `baseline-v1-dev.grades.csv` | `20261125T100230Z-baseline-dev` | `7d1b4f3` | v1 (`bb7ee80afbf6`) | M1 22/32, see [doc 17](../../docs/17-baseline-v1.md) |
