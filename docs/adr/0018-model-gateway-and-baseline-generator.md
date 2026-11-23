# ADR-0018: One model gateway, structured answers, and a baseline generator

- Status: Accepted
- Date: 2026-11-23
- Deciders: Project owner

## Context

Slice 2.6 adds the first component that calls a language model. Three things had to be settled
before measuring anything: where model calls are made, what shape an answer takes, and how the
prompt treats retrieved text. The generator for the local baseline is `qwen2.5:7b` through Ollama
(already installed; about 14 tokens a second on the project machine).

## Decision

1. **All model calls go through one gateway** (`LLMGateway`): `complete(messages, schema)` returns
   text, token counts, finish reason and time. The pipeline never talks to Ollama directly, so
   moving to a cloud model later means writing one more gateway, not changing the pipeline.
   The Ollama gateway also: allows only reviewed models (`qwen2.5` 3b, 7b, 14b); sets the context
   window explicitly (8,192 tokens) and refuses a prompt that cannot fit, because Ollama would
   otherwise cut long prompts silently; decodes repeatably (temperature 0, fixed seed 20261123);
   retries server errors and dropped connections twice, then fails visibly; and counts tokens and
   time per run.
2. **Answers are structured:** `{"refused": bool, "answer": text, "citations": [handles]}`. The
   reply is constrained to this shape by the JSON schema given to Ollama, so the refusal flag
   (metric M2) and the citations (M1, M5) are read from fields, not guessed from prose. The
   answer is written before the citations, so the model lists what it relied on after writing it.
3. **Sources carry short handles** (S1 to S5), not the 33-character chunk ids. Handles are mapped
   back to chunk ids in code. A handle the model invents becomes a visible fabricated citation
   (`UNKNOWN:...`, counted by M5) instead of a near-miss id that might look valid.
4. **Retrieved text is data.** The prompt wraps each source in a delimiter, tells the model that
   text inside sources is never an instruction, and removes any attempt by a source to close its
   own delimiter. This lowers risk; it is **not a security boundary**. Scanning documents for
   injected instructions stays deferred to Phase 3 (RAID I-5), and one gold item (G-ADV-003)
   waits for that.
5. **The baseline has no extras:** no retrieval-score floor for refusals, no reranker, no citation
   repair. The model alone decides whether to refuse. Each addition later is judged against this
   measured starting point.
6. **Unusable output is a failed answer, not a crash:** malformed JSON becomes an uncited,
   non-refusing answer (so it fails M1 and M2) and is counted. One bad reply does not stop a run.
7. **Prompts are versioned** (`v1`). The model digest, decoding settings, retriever, k and prompt
   version are written into every run's metadata.

## Alternatives considered

| Option | Why not |
|---|---|
| LiteLLM or LangChain as the gateway | More dependencies and behaviour we did not write and would have to review; the gateway is about 150 lines. Revisit when several providers are in play |
| Free-text answers parsed with a regex for citations | The refusal flag and citations would be guessed; metrics M1, M2 and M5 would measure the parser |
| Full chunk ids in the prompt | Small models mistype long ids; errors would be hard to tell from real fabrication |
| Refusing in code when the best retrieval score is low | Plausible later improvement, but it needs a threshold tuned on data; first measure the model alone |

## Consequences

- A full dev run is about 47 questions at roughly 25 seconds each on the project machine, so about
  20 minutes. The first run uses `--limit` for a smoke test.
- The local model sends nothing off the machine. Moving to a cloud model needs a data-handling
  review first (Phase 4); the availability and pricing of Canadian-region models are still
  unverified in the RAID log.
- Temperature 0 and a fixed seed make reruns very similar, not guaranteed identical (GPU and
  Vulkan arithmetic can differ). Do not read a one-question change between runs as a regression.
- M1 needs a person to grade the answers (about 35 of them). That is the owner's time and the
  main cost of this phase.

## Revisit when

A cloud model is added, a second prompt version is tried, or the baseline's refusal behaviour
(M2) shows a pattern a score floor would fix.
