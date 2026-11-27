# ADR-0020: Output guard: withhold uncited answers and instruction leaks, off by default

- Status: Proposed (accepted by the owner once the 3.9a dev run meets the rule in doc 20)
- Date: 2026-11-27
- Deciders: Project owner

## Context

The baseline has no safeguards beyond the prompt (ADR-0018, point 5). Two gaps are known. A model
can answer without citing anything the sources support (the API reports this as `uncited`,
ADR-0019), and a model can repeat its own rules when asked for them: qwen2.5:14b did in
experiment 3.3 (G-ADV-001, RAID I-5). Over 329 stored answers from seven runs, the baseline
model produced no uncited answer and no leak; the 14B run produced the one leak.

## Decision

1. **A deterministic guard runs after the model has written an answer.** It has two checks and
   no model, network or randomness:
   - **Uncited.** A non-refusal must cite at least one chunk that was really retrieved.
   - **Instruction leak.** An answer, refusing or not, that repeats eight consecutive words
     from any prompt version's rules is withheld.
2. **A withheld answer becomes a refusal** with a fixed sentence and a reason in
   `PipelineAnswer.guard` (`uncited` or `instruction_leak`). The original text and its citations
   are not passed on. Leak takes precedence over uncited as the more serious reason. Unusable
   output stays the pipeline's own failure and is counted there.
3. **Eight words.** On the stored answers, five words flags 112 of 329 (every "the sources do
   not provide" refusal), six or eight flag only the real leak. Eight is kept as the more
   conservative of the two.
4. **Off by default.** `eval run --guard` turns it on for the baseline pipeline; the run's settings
   record `guard: v1`. The API is unchanged. The baseline stays the measured starting point and
   the guard is judged against it (rule in doc 20).
5. **Pure Python, in the pipeline layer**, so the harness measures it and the API can use the
   same object later (ADR-0019 puts safeguards in the pipeline, not the API).

## Alternatives considered

| Option | Why not |
|---|---|
| A model that judges each answer | Slow, not repeatable, and needs its own validation against human labels; that is the faithfulness work (M6), a separate step |
| Match phrases such as "system prompt" | Easy to evade and it flags legitimate answers; word runs from the real rules do neither on the stored answers |
| Hide uncited answers as `refused` in the API | Rejected in ADR-0019: it changes measured behaviour outside the harness |
| A canary string in the prompt | Needs a new prompt version, which moves the baseline; reconsider if paraphrased leaks appear |

## Consequences

- A fabricated or leaking answer turns into a safe refusal. In M2 that counts as a refusal; on an
  answerable question it would count as an over-refusal, which is the honest cost.
- On dev it should change nothing (no such answers were produced), so the dev run shows cost, not
  benefit. The benefit is shown by the unit tests, the stored-answer replay and, later, the
  hold-out and real use.
- It is a net, not a security boundary. It does not judge truth (M6), cannot see a leak in other
  words, and cannot see an instruction followed without being repeated.
- Revisit when: a hosted model with a different style is used, M6 exists, or the hold-out shows a
  false positive.
