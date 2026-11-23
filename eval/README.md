# Evaluation

- `gold/gold-v1.yaml`: the gold set (60 items; questions, paraphrased key points and chunk ids only,
  never copied source text). Method and limits: `docs/12-gold-set.md`.
- Check it: `uv run python -m bfs_reg_copilot.eval validate`.
- The scoring harness arrives in slice 2.2. Specification: `docs/02-success-metrics.md`.
