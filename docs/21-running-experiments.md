# 21. Running an experiment

How a Phase 3 change is tested against the baseline, so every result is comparable and the
decision rule is applied as written. The rule for each experiment is written in
[doc 20](20-gate-3-phase-2-review.md) **before** the run.

## The reference run

Re-run the unchanged baseline once under the current gold file (v2). This also records the
embedding model's digest and the corpus fingerprint in the run metadata, which the first baseline
did not. About 12 minutes.

```powershell
uv run python -m bfs_reg_copilot.eval run --pipeline baseline --split dev
```

Carry the grades over from the first baseline. The answers should be identical (temperature 0,
fixed seed), so no new grading is needed. The command reports how many carried and how many still
need a person; it should say 0:

```powershell
uv run python -m bfs_reg_copilot.eval grade-sheet <reference_run_dir> `
  --carry-from eval\runs\20261125T100230Z-baseline-dev `
  --carry-grades eval\baselines\baseline-v2-dev.grades.csv
```

If some answers did change, the run is not exactly the one recorded in doc 17. Say so in the
experiment's record, grade the changed ones from the sheet, and use this run as the reference.

## The changed version

Run the change on the same questions. Example for experiment 3.1 (8 passages):

```powershell
uv run python -m bfs_reg_copilot.eval run --pipeline baseline --split dev --k 8
```

A prompt change uses `--prompt-version v2` (the default is `v1`, the measured baseline) and keeps `k` at 5:

```powershell
uv run python -m bfs_reg_copilot.eval run --pipeline baseline --split dev --prompt-version v2
```

Each version is recorded in the run's `meta.json`, and `flips` lists it among the settings that differ.

Carry the grades from the reference run. Answers that did not change keep their grades; answers
that changed stay blank for a person:

```powershell
uv run python -m bfs_reg_copilot.eval grade-sheet <changed_run_dir> `
  --carry-from <reference_run_dir> --carry-grades <reference_run_dir>\grades.csv
```

Open `grades.csv` in the changed run's folder. For each blank row, fill `points_hit` (and
`contradicts` if the answer says something the source contradicts) from the answer and the key
points, as for the baseline. Adversarial rows take `pass` or `fail` in `verdict`.

## The comparison

```powershell
uv run python -m bfs_reg_copilot.eval flips <reference_run_dir> <changed_run_dir> `
  --grades-before <reference_run_dir>\grades.csv --grades-after <changed_run_dir>\grades.csv
```

It lists the settings that differ, the questions fixed and broken, and applies the rule: at least
4 fixed and at most 1 broken, no fabricated citations, refusals of answerable questions up by at
most 1, and p95 latency at most 32 s. Those are the defaults, written for 3.1; options
(`--min-fixed`, `--max-broken`, `--max-refusal-rise`, `--max-p95`) set a different rule for a
different experiment, which must also be written down first.

A change of model uses `--model` and keeps the prompt and `k`. When an experiment's written rule does not gate on latency (as in 3.3), run `flips` with `--max-p95 1000` and report the latency from the `score` output in the record:

```powershell
uv run python -m bfs_reg_copilot.eval run --pipeline baseline --split dev --model qwen2.5:14b
```

Check a new model with a one-question smoke run first, written outside `eval\runs` so it is never mistaken for the latest run: `... --limit 1 --out-dir $env:TEMP\smoke`.

**Reading the verdict.** "Adopt" needs a net gain of about six questions, the size a sign test on 32
questions needs. "Promising, not proven" means the rule is met with a smaller gain: record it, and
re-test on a larger dev set before relying on it. "Do not adopt" means a condition failed; record
the result anyway. A result that did not help is still a result.

## Serving settings (Ollama)

Latency and, for a larger model, run time depend on how Ollama is set up, so it is part of the experiment.

- `OLLAMA_MAX_LOADED_MODELS=2`. A run uses two models (the embedder and the generator). With the limit at 1
  they evict each other on every question and each question pays a reload. Keep-alive can stay at the
  default of 5 minutes: questions arrive every few seconds, so the models stay loaded during a run.
- The variables are read when the server starts. Setting them with `[Environment]::SetEnvironmentVariable(
  name, value, "User")` does not change the window you ran it in, and a server started from that window
  (for example by `ollama stop` or `ollama ps` when none is running) inherits the old values. Quit Ollama
  from the tray, start it from the Start menu, then check the first line of
  `%LOCALAPPDATA%\Ollama\server.log` ("server config") for the values.
- Record `ollama --version` with each experiment, and do not update Ollama in the middle of a series.
  After any change of version or serving settings, re-run the reference and carry the grades over: it must
  report 0 still to grade, otherwise the answers changed and the reference is a new one.
- Latency is comparable only between runs under the same serving settings.

## Rules for the person running it

- Do not look at the changed answers and then adjust the rule. If the rule was wrong, say so, write
  a new one, and run again.
- Back up every run folder privately (`eval/runs/` is not in git). A later re-score under another
  gold version needs the answers.
- One change per experiment. Two changes in one run cannot be told apart.
- The hold-out is not used for experiments. It is first run at Gate 4 (doc 02).

## Reranker server (llama.cpp)

Used only by `retrieve ranks --rerank` (and a later reranked run). It is a second local process,
separate from Ollama.

```powershell
winget install llama.cpp
llama-server -hf smarttasks/bge-reranker-v2-m3-GGUF:Q4_K_M --reranking --port 8081 --host 127.0.0.1 -b 2048 -ub 2048
```

Leave it running in its own terminal; stop it with Ctrl+C. Application Control may block the first
launch; retry. Then, in another terminal, with Postgres and Ollama up:

```powershell
uv run python -m bfs_reg_copilot.retrieve ranks --rerank
```

The last lines state whether the Stage 1 rule of doc 20 is met. Passages longer than 6000
characters are cut to fit the server batch; the count is printed.
