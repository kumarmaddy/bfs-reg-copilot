"""Store chunks, one JSON object per line (git-ignored, ADR-0007).

<root>/<source_id>/<raw_sha256>.v<cleaner>.c<chunker>.jsonl
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from bfs_reg_copilot.ingest.chunking import CHUNKER_VERSION, Chunk


def chunks_path(root: Path, source_id: str, raw_sha256: str, cleaner_version: str) -> Path:
    name = f"{raw_sha256}.v{cleaner_version}.c{CHUNKER_VERSION}.jsonl"
    return root / source_id / name


def write_chunks(root: Path, chunks: tuple[Chunk, ...], cleaner_version: str) -> Path:
    if not chunks:
        raise ValueError("refusing to write an empty chunk file")
    first = chunks[0]
    if any((c.source_id, c.raw_sha256) != (first.source_id, first.raw_sha256) for c in chunks):
        raise ValueError("all chunks in one file must come from the same source and raw page")
    target = chunks_path(root, first.source_id, first.raw_sha256, cleaner_version)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def read_chunks(path: Path) -> tuple[Chunk, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(Chunk.model_validate_json(line) for line in lines if line.strip())
