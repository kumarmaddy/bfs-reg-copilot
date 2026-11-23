# ADR-0014: Gold set drafted from primary text, accepted by the owner, hold-out sealed by rule

- Status: Accepted
- Date: 2026-11-23
- Deciders: Project owner

## Context

Metrics M1 and M2 are only as honest as the gold set behind them (docs/02 section 4). There is one
person on this project. The specification asked the owner to label every item and to re-label a
sample after 48 hours. The owner has the time to review but asked the assistant to draft the items
as a reviewer would, and chose to skip the re-label.

## Decision

- **Drafting.** The assistant writes each question and its key points from the cleaned primary
  text, never from a model's answer to the question. Key points are paraphrases.
- **Acceptance.** The owner reviews and accepts the set. Acceptance on 2026-11-23 covers all 60
  items as drafted.
- **Structure.** One YAML file (`eval/gold/gold-v1.yaml`) with questions, key points, a pass rule
  (minimum number of key points and any that are required) and full chunk ids. No corpus text.
- **Bound to a page version.** The chunk id contains the first 12 characters of the page hash. If a
  page changes, `python -m bfs_reg_copilot.eval validate` fails and the items for that source are
  re-reviewed. This is the evaluation side of requirement S4 (changed sources are flagged).
- **Hold-out.** 12 of 60 items (20%), chosen once with a recorded seed: one answerable item per
  source plus one extra from E-23, three refusals and one scorable adversarial item. The hold-out
  is not run during tuning. It is run at gates and recorded in the change log of docs/12.
- **Unscorable item.** `G-ADV-003` (instruction hidden in a document) needs a planted chunk, so it
  is recorded but not scored until the Phase 3 prompt-injection work.

## Alternatives considered

| Option | Why not (or why later) |
|---|---|
| Owner writes all 60 items | Slower, and the owner offered review time, not authoring time |
| A model writes questions and answers from its own knowledge | Labels would encode the model's errors; the spec forbids it |
| Use a language model as judge from the start | Needs 30 human-checked items first (docs/02 section 5); later |
| Keep the 48-hour self-consistency re-label | Owner chose to skip it; recorded as a limit, not hidden |

## Consequences

- The labels are not independent: the same assistant that drafts the set will also help build and
  tune the system. The hold-out is sealed against tuning, not against the drafter's knowledge.
- A source refresh breaks chunk ids on purpose. That is a re-review prompt, at a cost of some work.
- Scores on this set are evidence for a portfolio project, not a validation by an independent
  reviewer (risk R-17).

## Revisit when

An independent reviewer becomes available (re-label a sample, report agreement); a source page
changes; the first baseline shows items that are ambiguous or wrong; the hold-out has been used
for tuning by mistake.
