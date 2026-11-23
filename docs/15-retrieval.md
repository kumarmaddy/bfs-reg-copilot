# 15. Retrieval

Three retrievers sit behind one interface (`Retriever.retrieve(question, k)` returns ranked chunk
ids with scores), so the generator and the evaluator do not care which one runs
([ADR-0004](adr/0004-postgres-pgvector-for-retrieval.md)).

| Retriever | How it works |
|---|---|
| `dense` | The question is embedded with bge-m3 ([ADR-0016](adr/0016-embedding-model-bge-m3.md)); the nearest chunks by cosine distance win |
| `fulltext` | The question's stemmed words are OR-ed into a PostgreSQL text query; chunks are ranked by `ts_rank_cd` with length normalisation. Untuned |
| `hybrid` | Reciprocal rank fusion of the top 50 of each: a chunk scores the sum of 1/(60 + rank) over the lists it appears in. k = 60 as in the original paper, untuned |

Only current chunks are searched (superseded page versions are ignored).

## Try it

```powershell
uv run python -m bfs_reg_copilot.retrieve ask "May a reporting entity tell its client that it has filed an STR?" --retriever dense --k 5
uv run python -m bfs_reg_copilot.retrieve compare
```

`ask` prints the chunks, their heading path and the start of their text: the quickest way to see
why a question missed. `compare` runs all three on the dev questions (hold-out untouched, see
[ADR-0014](adr/0014-gold-set-labelling-and-sealed-holdout.md)) and reports hit@1/3/5/10, a
per-source breakdown, the missed questions and latency per question.

## Rule for adopting hybrid

Fixed before any keyword or hybrid number was seen. Dense-only was already known (30 of 32 at
hit@5): hybrid replaces it only if hit@5 does not drop **and** it gains at least one question at
hit@5 or at least two at hit@3. Otherwise dense-only stays, being simpler to run and to explain.
`compare` prints the verdict. The rule was chosen knowing the dense result, which is why it
demands a gain rather than a tie.

## Result on the dev split (2026-11-23, bge-m3, 624 chunks, [ADR-0017](adr/0017-dense-only-retrieval-baseline.md))

| | hit@1 | hit@3 | hit@5 | hit@10 | Missed at 5 |
|---|---|---|---|---|---|
| dense | 22/32 | 29/32 | **30/32** | 31/32 | G-E21-005, G-STR-003 |
| fulltext | 10/32 | 19/32 | 22/32 | 27/32 | 10 questions |
| hybrid | 20/32 | 28/32 | 28/32 | 31/32 | G-B10-003, G-B13-001, G-STR-002, G-STR-003 |

Hybrid does not meet the rule (hit@5 30 to 28), so **dense-only is the baseline retriever**. Hybrid
fixed one question and broke three. Latency per question is about 94 ms at p50 and 109 ms at p95
for dense and hybrid alike (the embedding call dominates; the keyword query is near zero).

## A known hard case: G-STR-003

"May a reporting entity tell its client that it has filed an STR?" is missed by both embedding
models. The label is right: the answer is a short "Note" (about 400 characters in) inside a
1,792-character definition section, and the question says "tell the client" where the text says
"inform ... tip off". The sentence is a small part of a chunk that is mostly about something else.
Hybrid does not fix it either (the question's keywords are common words). Fixes to try later, each measured on dev: smaller chunks, a reranker over the top candidates, or
query rewriting. None is done yet.

## Limits

- 32 dev questions. A difference of one or two questions is inside the noise (see the intervals).
- Retrieval quality only. It says nothing about whether answers are correct (M1) or refuse when
  they should (M2).
