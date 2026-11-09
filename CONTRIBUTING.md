# Contributing

1. `make setup` once, then `make check` before every commit.
2. Never commit source documents, chunks or embeddings (ADR-0007).
3. New sources go through `data/sources/register.yaml` with terms verified first.
4. Significant design changes need an ADR in `docs/adr/`.
5. Unverified facts stay marked `[to verify]` until checked against the primary source.
