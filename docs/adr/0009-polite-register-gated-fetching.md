# ADR-0009: Register-gated, polite fetching

- Status: Accepted
- Date: 2026-11-18
- Deciders: Project owner

## Context

The corpus comes from government websites whose terms we have read (OSFI, FINTRAC and Canada.ca;
see the source register). Those terms permit non-commercial reproduction with attribution. They
say nothing about automated access, so ordinary crawler etiquette is our only guide. The register
already records which sources may be ingested; the fetcher must not be able to bypass it.

## Decision

The fetcher (`bfs_reg_copilot.ingest.fetcher`) applies these rules, in order:

1. **Register gate.** Only sources with `ingest_allowed: true` are fetched. Blocked, pending and
   unknown ids are refused before any network call, and the refusal states why.
2. **Same host, https only.** Every request and every redirect hop must use https and stay on the
   host of the registered URL. A redirect elsewhere is refused, not followed.
3. **robots.txt.** The path must be allowed. A 404 or 410 on `robots.txt` means no rules. Any other
   failure to read it (including 401, 403 and 5xx) means we do not fetch.
4. **Rate limit.** At least 2 seconds between requests to one host.
5. **Identification.** The User-Agent names this project and links to its public repository. It
   contains no personal contact details.
6. **Limits.** A 30 second timeout, a 20 MB body limit, at most 5 redirects, and only HTTP 200
   counts as success. There are no automatic retries; a failure is reported, not hidden.

## Alternatives considered

| Option | Why not |
|---|---|
| `requests` | Works, but `httpx` has a built-in mock transport that lets every rule be tested without the network |
| Scrapy or another crawling framework | Far more machinery than a handful of known pages needs, and it hides the rules we want to be able to read |
| Treating a failed `robots.txt` read as "allowed" | Standard etiquette allows it for 4xx, but a 403 often means a firewall is blocking bots; stopping is the safer reading |
| Automatic retries | Hide transient failures and extend load on a public server. Add later, with backoff, if real failures need them |

## Consequences

- Fetching can only ever touch pages the register permits, on hosts it names. Moving a source to
  a new host needs a register edit, which is reviewed.
- Some legitimate redirects (for example to a bare domain without `www`) will be refused until the
  registered URL is updated. This is deliberate.
- Fetch results carry the retrieval time and HTTP validators (ETag, Last-Modified) for lineage.
  Storing them is slice 1.2.
- A 2 second delay makes a full fetch of the corpus slow, which is acceptable for a handful of
  pages.

## Revisit when

A source needs login or an API (not planned), a publisher states automated-access rules that
differ from these, or real failures show that retries with backoff are needed.
