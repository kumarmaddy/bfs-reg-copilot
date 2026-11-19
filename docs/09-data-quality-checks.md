# 09. Data-quality checks (Phase 1)

Run them with `uv run python -m bfs_reg_copilot.ingest dq`. The command prints one line per
finding and exits 0 when there are no ERRORs, 5 otherwise. Add `--strict` to fail on warnings too.
The same checks run as tests (`tests/test_dq.py`), and one test runs them on your local data.

An **ERROR** means the data must not be used. A **WARNING** means a person should look.

| Code | Severity | What it checks | Why it exists |
|---|---|---|---|
| DQ-01 | ERROR | Every chunk names a source the register allows to be ingested | Governance: nothing enters the corpus around the register |
| DQ-02 | ERROR | Every chunk's raw hash and retrieval time match a stored retrieval, and the stored page still matches its hash | Lineage: any chunk can be traced to the exact bytes we downloaded |
| DQ-03 | ERROR | The page URL is https and on the host the register names | A redirect or typo cannot smuggle in another site's text |
| DQ-04 | ERROR / WARNING | Retrieval time is UTC and not in the future (error); older than 180 days (warning) | Dates in citations must be right, and stale guidance should be refreshed |
| DQ-05 | ERROR | Chunk text is an exact slice of the cleaned section; heading path matches | Nothing is reworded between cleaning and chunking |
| DQ-06 | ERROR | Chunk ids are unique, sizes are within the limit, numbering is consistent | Stable identifiers for citations and evaluation |
| DQ-07 | WARNING | No page furniture phrases ("Report a problem", "Date modified", ...) in chunk text | Cleaning missed something |
| DQ-08 | ERROR | Every non-blank character of the cleaned text is in at least one chunk | The chunker lost text |
| DQ-09 | WARNING | Cleaned text is at least 85% of the page's main text | The cleaner dropped too much, or the page was only partly captured |
| DQ-10 | WARNING | No two chunks of 80+ characters have identical text | Often legitimate repetition in the source, sometimes a cleaning fault |
| DQ-11 | ERROR / WARNING | No control or replacement characters (error); no garbled-encoding patterns (warning) | Encoding damage |
| DQ-12 | ERROR / WARNING | At least one chunk (error); at least 1,000 characters in total (warning) | An empty or nearly empty page is a failed fetch, not a document |
| DQ-13 | WARNING | An allowed source is not fetched, cleaned and chunked yet | Visible progress, not a failure |
| DQ-14 | ERROR | Nothing is stored for a source that is blocked, pending or not in the register | The register is the only way in |
| DQ-15 | ERROR | `.gitignore` lists every corpus folder, and git tracks nothing under `data/` except `data/sources/` | Exit criterion: no corpus text in git (ADR-0007) |

## Phase 1 exit criteria and where they are enforced

| Criterion | Check |
|---|---|
| Every chunk traces to a register entry and a retrieval date | DQ-01, DQ-02, DQ-04 |
| Data-quality tests pass | the whole table; the CI job runs them on synthetic data and a developer runs them on the real corpus |
| No corpus text in git | DQ-15 (checked in CI and locally) |

## Known limits

- CI has no corpus, so it proves the checks work on invented pages, not that today's real pages
  are clean. The real-data check is a local run of `dq` and the local-only test.
- DQ-09 and DQ-10 are heuristics; their thresholds were set from two pages and may need tuning.
- The checks do not judge whether the guidance text is correct, only that it is faithfully what
  the publisher's page said on the retrieval date.
