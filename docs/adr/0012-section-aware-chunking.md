# ADR-0012: Section-aware chunking with verbatim, traceable chunks

- Status: Accepted
- Date: 2026-11-19
- Deciders: Project owner

## Context

Retrieval needs pieces small enough to match a question and large enough to carry a complete
thought. Regulatory text is organised by headings, and an answer has to cite which section it
came from, which page version, and when we retrieved it (exit criterion of Phase 1).

## Decision

- **Never cross a section.** Every chunk sits under exactly one heading path.
- **Size.** At most 1,800 characters (roughly 400 tokens of English), with up to 200 characters of
  overlap. Both are settings, not constants; Phase 2 evaluation decides whether they are right.
- **Where to cut, in order:** line boundaries (paragraph, list item, table row), then sentence
  ends, then spaces, and only then in the middle of a word.
- **Overlap is whole lines.** The next chunk starts a few lines back only if those lines fit in the
  overlap budget; otherwise there is no overlap. Overlap never makes the next piece too large.
- **Verbatim.** A chunk's text is exactly `section.text[start:end]`; offsets are stored. Nothing is
  rewritten. The heading path is added only at embedding time (`contextualised()`).
- **Identity.** `chunk_id = <source_id>:<first 12 of raw sha256>:s<section>:c<chunk>`. The same
  input and settings give the same ids. A changed page gives different ids.
- **Lineage on every chunk.** Source id, raw hash, retrieval time, final URL, page title, date
  modified, section path and anchor.
- **Storage.** `data/curated/<source_id>/<raw_sha256>.v<cleaner>.c<chunker>.jsonl`, git-ignored.
- Short sections are not merged with their neighbours. That keeps every chunk traceable to one
  heading; the cost is a few very small chunks (3 under 100 characters in FINTRAC's page).

## Alternatives considered

| Option | Why not |
|---|---|
| Fixed-size windows over the whole page | Cuts across headings, so the citation can be wrong |
| Semantic chunking with an embedding model | Needs a model before the pipeline is stable; non-deterministic ids |
| Larger chunks with no overlap | Simpler, but a sentence cut at the edge disappears from both chunks |
| Merging small sections | Better chunk sizes, worse traceability; revisit only if evaluation shows poor recall |

## Consequences

- On the two pages tried: E-21 gives 39 chunks (median 529 characters) and FINTRAC STR gives 215
  (median 1,088), none above the limit.
- Tables become many short row lines; a long table spreads over several chunks.
- The chunk file is rewritten whenever the chunker version, cleaner version or raw page changes,
  and old files stay.

## Revisit when

Evaluation (Phase 2) shows chunks too large or small, table questions fail, or small sections need
merging.
