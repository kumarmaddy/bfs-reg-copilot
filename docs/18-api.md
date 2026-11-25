# 18. The API

The baseline pipeline over HTTP ([ADR-0019](adr/0019-baseline-api.md)). Local use only: it has no
authentication.

## Run it

Install once (these add the API's two dependencies to `pyproject.toml` and `uv.lock`):

```powershell
uv add fastapi uvicorn
```

The database must be loaded and embedded (doc 14) and Ollama running with `qwen2.5:7b` and
`bge-m3` (doc 16). Then:

```powershell
uv run python -m bfs_reg_copilot.api
```

The server listens on `http://127.0.0.1:8000`. Interactive documentation is at `/docs` and the
machine-readable description at `/openapi.json`. The first question is slow while Ollama loads the
models; later ones take about 16 seconds on the project machine (baseline run, doc 17).

## Ask a question

```powershell
$body = @{ question = "When does OSFI Guideline E-23 take effect?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/ask -ContentType "application/json" -Body $body
```

(Use `-ContentType "application/json; charset=utf-8"` and an explicit UTF-8 body if the question
contains accented letters; Windows PowerShell 5 otherwise sends them in the wrong encoding.)

Response:

| Field | Meaning |
|---|---|
| `request_id` | Quote this when asking about a specific answer. Also sent as `X-Request-ID` |
| `outcome` | `answered`, `refused`, or `uncited` (see below) |
| `answer` | The model's text. It is model output: check it against the cited passage |
| `citations` | Verified sources: `chunk_id`, `source_id`, `section_path`, `page_title`, `url`, `retrieved_at`, `date_modified`, `raw_sha256` |
| `unverified_citations` | Citations the model gave that match no retrieved passage. Not shown |
| `latency_ms` | Time from request to answer, including any wait for another question |

**`uncited` means the model gave an answer but nothing it cited could be verified. Do not treat it
as supported.** The baseline does not block these answers; that is a later change, judged against
the baseline.

## Errors

All errors have the shape `{"request_id", "error", "detail"}` and a fixed, safe message.

| Status | `error` | Meaning | What to do |
|---|---|---|---|
| 422 | (validation) | Empty or over-long question (limit 2,000 characters), or an unknown field | Fix the request |
| 502 | `unusable_output` | The model's reply could not be used | Try again or rephrase |
| 503 | `busy` | Another question is being answered (one at a time) | Retry after the `Retry-After` seconds |
| 503 | `dependency_unavailable` | The database or the model could not be reached | Check `docker compose ps` and `ollama list`; the next request retries |
| 500 | `internal` | A bug. The details are in the server log under the request id | Report it |

## Probes

- `GET /health`: the process is running. Does not check anything else.
- `GET /ready`: the database and the model are reachable. `503` if not.

## What is logged

The request id, outcome, number of citations, number of unverified citations, latency and the
**length** of the question. Not the question and not the answer.

## Limits to know about

- One question at a time; others wait up to 60 seconds, then get `503 busy`.
- No authentication or TLS; the server refuses to listen on a non-local address unless you pass
  `--allow-remote`. Do not do that on a shared network.
- No scanning of source documents for injected instructions (RAID I-5).
- The answer quality is the measured baseline in [doc 17](17-baseline-v1.md): 22 of 32 dev
  questions answered correctly with a verified citation. Roughly one in three answers on the dev
  set was incomplete or wrong, so every answer needs checking against its source.
