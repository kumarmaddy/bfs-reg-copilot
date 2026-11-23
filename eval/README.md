# Evaluation

- `gold/gold-v1.yaml`: the gold set (60 items; questions, paraphrased key points and chunk ids only,
  never copied source text). Method and limits: `docs/12-gold-set.md`.
- `holdout-log.jsonl`: appended each time the sealed hold-out is run (created by the first run).
- `runs/`: stored runs and grading sheets (git-ignored).
- Harness and how to run it: `docs/13-evaluation-harness.md`.
- Check the gold set: `uv run python -m bfs_reg_copilot.eval validate`.
