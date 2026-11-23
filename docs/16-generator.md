# 16. Generator and baseline pipeline

Retrieve five chunks with dense search ([ADR-0017](adr/0017-dense-only-retrieval-baseline.md)),
show them to the local model with the question, and read back a structured answer
([ADR-0018](adr/0018-model-gateway-and-baseline-generator.md)).

```
question -> dense retriever (bge-m3, k=5) -> prompt v1 (sources S1..S5) -> gateway -> qwen2.5:7b
         -> {"refused", "answer", "citations"} -> handles mapped to chunk ids -> PipelineAnswer
```

## Run it

The database must be loaded and embedded (doc 14) and Ollama running with `qwen2.5:7b` and
`bge-m3` installed.

```powershell
# smoke test: two items per kind (about 6 questions, 2-3 minutes)
uv run python -m bfs_reg_copilot.eval run --pipeline baseline --limit 2

# the real dev run (about 20 minutes; keep the laptop awake and plugged in)
uv run python -m bfs_reg_copilot.eval run --pipeline baseline
```

The run prints progress, stores the answers under `eval/runs/` (not committed), and prints the
mechanical metrics. M1 and M8 need a person:

```powershell
uv run python -m bfs_reg_copilot.eval grade-sheet eval\runs\<run folder>
# open grades.csv, fill points_hit / contradicts / verdict, save
uv run python -m bfs_reg_copilot.eval score eval\runs\<run folder>
```

The hold-out stays sealed: `--split holdout` still needs `--confirm-holdout` and `--reason`
([ADR-0014](adr/0014-gold-set-labelling-and-sealed-holdout.md)). Do not run it for tuning.

## What a run records

Model name and build digest, temperature, seed, context size, retriever, k, prompt version, git
commit, gold set hash, and per-answer latency. The run's last lines report malformed model
outputs and total tokens and model time.

## How to read the first results

- **M2 (correct refusal)** is mechanical: did the `refused` flag come up. A 7B model tends to
  answer from memory when the corpus lacks the topic; this is the number most likely to be poor.
- **M5 (fabricated citations)** counts citations not among the five retrieved sections, including
  invented handles. It should be near zero; anything else means the model is ignoring the rules.
- **M4 (hit@5)** here is measured on the retriever's actual output and should match doc 15 (30 of
  32 on dev for answerable items).
- **M1** is the headline and the one that costs your time. Grade strictly against the key points.

## Limits

- Prompt injection is not scanned for (RAID I-5). The prompt marks sources as data and the code
  stops a source from closing its delimiter, which helps but proves nothing.
- Repeat runs are very similar, not identical (ADR-0018).
