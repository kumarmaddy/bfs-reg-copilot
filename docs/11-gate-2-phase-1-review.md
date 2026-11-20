# Gate 2: Phase 1 review (data pipeline)

Review of Phase 1 against the exit criteria in `06-delivery-plan.md`. Tick an item only when the
evidence exists. "Owner" items cannot be done by the assistant.

**Result: pass.** Reviewed 2026-11-20. All three exit criteria are met and evidenced below. The
items under "Carried forward" do not block Phase 2.

## Exit criteria

| # | Exit criterion | Evidence | Done |
|---|---|---|---|
| G2-1 | Every chunk traces to a register entry and a retrieval date | Each chunk stores source id, raw SHA-256, retrieval time (UTC), final URL, page title, date modified, section path and anchor (ADR-0010, ADR-0012). `dq` checks DQ-01 to DQ-04 on every chunk: 0 errors on all 7 sources | [x] |
| G2-2 | Data-quality tests are green | 15 checks (`09-data-quality-checks.md`). `dq` run on the developer machine and in the Airflow run: 0 errors, 2 warnings (explained below). Unit tests: 154 passed locally. CI `check` green on every slice PR | [x] |
| G2-3 | No corpus text in git | `.gitignore` lists every corpus folder; DQ-15 fails if any file outside `data/sources/` is tracked; `git status` clean after runs on the Windows machine; Codespace clean tree to be confirmed by the owner | [x] |
| G2-4 | **Owner:** run the DAG for real, outside a test, and confirm it ends green | Codespace, 2026-11-20: `airflow dags test regcopilot_ingest` finished `state=success` in 27 seconds; all 7 sources fetched | [x] |

## Planned work, as built

| Planned (06) | Built | Record |
|---|---|---|
| Fetch only `ingest_allowed` sources | Register-gated, polite fetcher: https only, same host on every redirect, robots.txt, 2 s gap, size and time limits | ADR-0009 |
| raw / cleaned / curated layers | Content-addressed raw store with append-only manifest; cleaned JSON; chunk JSONL; all git-ignored | ADR-0010, ADR-0011 |
| Chunking with section metadata | Section-aware, verbatim, stable ids, overlap of whole lines | ADR-0012 |
| Data-quality tests | `ingest dq` and `tests/test_dq.py` | doc 09 |
| Airflow DAG | Thin DAG over tested stages; one sequential fetch task; `verdict` task so a failure cannot show green | ADR-0013, doc 10 |

## Corpus snapshot (Codespace run, 2026-11-20)

| Source | Bytes | Sections | Chunks |
|---|---|---|---|
| A-OSFI-E23 | 114,812 | 40 | 43 |
| A-OSFI-B10 | 159,696 | 64 | 72 |
| A-OSFI-B13 | 136,405 | 83 | 83 |
| A-OSFI-E21 | 111,586 | 38 | 39 |
| B-FINTRAC-STR | 396,529 | 131 | 215 |
| B-FINTRAC-CPR | 124,194 | 14 | 57 |
| B-FINTRAC-RBA | 196,942 | 51 | 116 |
| **Total** | | | **625** |

The two `DQ-10` warnings are identical worked-example text repeated in FINTRAC's suspicious
transaction page. The repetition is in the source, so they are accepted.

## Found by running it, not by reading it

- A stored FINTRAC page was found modified on disk (hash mismatch); the cause was never proven. Stored pages are
  now read-only, and saving over a damaged copy repairs it instead of calling it "unchanged".
- The first DAG design showed a green run when a fetch had failed. The `verdict` task fixed it.
- Fetching per source in separate Airflow tasks would have broken the 2 second gap between
  requests. Fetching is one task.

## Carried forward (does not block Phase 2)

| Item | Where it goes |
|---|---|
| Prompt-injection content scanning on ingest (DQ-16 instruction patterns; cleaner drops text hidden by `hidden`, `aria-hidden` or `display:none`). Owner decided on 2026-11-19 to defer. The cleaner does not yet drop hidden text outside forms | Risk R-06; Phase 3 guardrails |
| `A-OSFI-B10` gave 63 sections and 71 chunks on the Windows machine and 64 sections and 72 chunks in the Codespace (159,696 bytes). Compare the two manifests to see whether the page changed. Find what changed and use the latest version when verifying effective dates | RAID issue; owner |
| DQ-09 (page coverage) and DQ-10 thresholds were set from two pages | Revisit if evaluation shows lost content |
| Tables are flattened to `cell \| cell` lines | Phase 2 evaluation will show whether table questions fail |
| The Airflow tests do not run in normal CI (no Airflow there). Run `BFS_AIRFLOW_E2E=1` tests before changing `dags/` | ADR-0013 |
| No retries on fetch; no corpus backup or retention policy | Revisit before any shared deployment |
| Cleaning rules were tuned on OSFI and FINTRAC pages only | New publishers (eCFR, Phase 3) need their own check |

## Next

Phase 2 (baseline RAG and evaluation) starts with the gold set, since it protects the measurement,
then the pgvector schema. Phase 2 may start when the close-out PR is merged and the
`phase-1-complete` tag exists.
