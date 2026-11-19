# ADR-0011: Cleaning keeps main content and heading structure

- Status: Accepted
- Date: 2026-11-19
- Deciders: Project owner

## Context

OSFI and FINTRAC pages are large HTML documents. OSFI's E-21 page is about 110 KB of markup for
roughly 28 K characters of guidance; FINTRAC's suspicious transaction page is about 400 KB for
roughly 230 K characters. Most of the rest is navigation, scripts, forms and footers. Retrieval
quality and citations depend on clean text that still knows which heading it sits under.

## Decision

- Parse with BeautifulSoup and Python's built-in `html.parser` (no `lxml`: one less native
  dependency on Windows).
- Keep only `<main>`. Drop scripts, styles, `nav`, forms, buttons and the page-details footer
  (`.pagedetails`). The page's "Date modified" is kept as metadata, not as text.
- Drop the "In this guidance", "In this section", "In this annex", "Related links" and "On this
  page" link lists. They do not change the heading path of what follows.
- Split into sections at every heading. Each section records its level, heading, anchor id (when
  the page provides one) and the full breadcrumb path (`h1 > h2 > h3`). Headings with no body text
  are omitted but remain in their children's paths.
- Lists keep their nesting with indentation and `- `; table rows become `cell | cell` lines;
  `<br>` becomes a line break; whitespace and non-breaking spaces are normalised.
- Wording is never changed. The cleaner does not summarise, correct or translate.
- Each cleaned document carries `source_id`, `raw_sha256`, `retrieved_at`, `final_url` and the
  cleaner version, and is stored as `data/cleaned/<source_id>/<raw_sha256>.v<version>.json`
  (git-ignored). Bumping `CLEANER_VERSION` produces new files and keeps the old ones.
- Pages without `<main>` or without any text fail loudly instead of producing empty output.

## Alternatives considered

| Option | Why not |
|---|---|
| `trafilatura` or `readability` | Good for news articles, but they guess what is "content" and can drop tables and definitions that matter in regulation |
| Convert to Markdown with a library | Adds formatting syntax the chunker would have to strip again; we need structure, not styling |
| `lxml` parser | Faster, but a native dependency; speed is irrelevant for a handful of pages |
| Strip all tags from the whole page | Keeps menus and footers and loses heading structure |

## Consequences

- A section is the natural unit for chunking (slice 1.4), and its path is the citation context.
- Tables become plain lines, which loses merged-cell layout. Acceptable for retrieval; revisit if
  evaluation shows table questions failing.
- Very long sections exist (FINTRAC's Definitions is about 58 K characters); the chunker must
  split them.
- Both rules above are tuned on two publishers. A new publisher needs its own check.

## Revisit when

A source is a PDF (this cleaner handles HTML only), a publisher redesigns its pages, or evaluation
shows lost content.
