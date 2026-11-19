"""Section-aware chunking.

A chunk never crosses a section boundary, so its heading path always describes all of its text.
Long sections are cut on paragraph, list-item and table-row boundaries first, then on sentence
ends, then on spaces, and only as a last resort in the middle of a word. Neighbouring chunks of
one section overlap by a few lines so a sentence that straddles a cut is not lost.

Every chunk text is an exact slice of its section text (`section.text[start:end]`), so nothing is
reworded and any chunk can be checked against the cleaned page it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import AwareDatetime, BaseModel, ConfigDict

from bfs_reg_copilot.ingest.cleaned_store import CleanedDocument

CHUNKER_VERSION: Final = "1"

_SENTENCE_END: Final = re.compile(r"(?<=[.!?;:])\s+")
_SPACE: Final = re.compile(r"\s+")


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 1800  # about 400 tokens of English prose
    overlap_chars: int = 200

    def __post_init__(self) -> None:
        if self.max_chars < 200:
            raise ValueError("max_chars must be at least 200")
        if not 0 <= self.overlap_chars <= self.max_chars // 2:
            raise ValueError("overlap_chars must be between 0 and half of max_chars")


class Chunk(BaseModel):
    """One retrievable unit, carrying everything needed to cite it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    # lineage: register entry, the exact raw bytes, and when we retrieved them
    source_id: str
    raw_sha256: str
    retrieved_at: AwareDatetime
    final_url: str
    page_title: str
    date_modified: str | None
    # location in the page
    section_index: int
    section_heading: str
    section_path: tuple[str, ...]
    anchor: str | None
    chunk_index: int
    chunk_count: int
    section_start: int
    section_end: int
    text: str

    def contextualised(self) -> str:
        """Text with its heading path in front: what to embed, while `text` stays verbatim."""
        return " > ".join(self.section_path) + "\n" + self.text


def _cut_before(text: str, limit: int, pattern: re.Pattern[str]) -> tuple[int, int] | None:
    """Last (end_of_text, start_of_next) with end_of_text <= limit and past the halfway mark."""
    best: tuple[int, int] | None = None
    for match in pattern.finditer(text):
        if match.start() > limit:
            break
        if match.start() >= limit // 2:
            best = (match.start(), match.end())
    return best


def _split_long(text: str, offset: int, max_chars: int) -> list[tuple[int, int]]:
    pieces: list[tuple[int, int]] = []
    pos = 0
    while len(text) - pos > max_chars:
        window = text[pos : pos + max_chars + 1]
        cut = _cut_before(window, max_chars, _SENTENCE_END) or _cut_before(
            window, max_chars, _SPACE
        )
        if cut is None:  # no break point at all, e.g. one enormous token
            pieces.append((offset + pos, offset + pos + max_chars))
            pos += max_chars
            continue
        pieces.append((offset + pos, offset + pos + cut[0]))
        pos += cut[1]
    pieces.append((offset + pos, offset + len(text)))
    return pieces


def _pieces(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Smallest units we will not cut: one line each, unless a single line is too long."""
    pieces: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        if len(line) <= max_chars:
            pieces.append((pos, pos + len(line)))
        else:
            pieces.extend(_split_long(line, pos, max_chars))
        pos += len(line) + 1
    return pieces


def _windows(pieces: list[tuple[int, int]], config: ChunkingConfig) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    i, n = 0, len(pieces)
    while i < n:
        j = i
        while j < n and pieces[j][1] - pieces[i][0] <= config.max_chars:
            j += 1
        j = max(j, i + 1)
        windows.append((pieces[i][0], pieces[j - 1][1]))
        if j >= n:
            break
        # Start the next chunk a few pieces back, as long as the overlap stays small and the
        # next piece still fits behind it. k == j means no overlap.
        k = j
        while k - 1 > i and pieces[j - 1][1] - pieces[k - 1][0] <= config.overlap_chars:
            k -= 1
        while k < j and pieces[j][1] - pieces[k][0] > config.max_chars:
            k += 1
        i = k
    return windows


def chunk_document(doc: CleanedDocument, config: ChunkingConfig | None = None) -> tuple[Chunk, ...]:
    config = config or ChunkingConfig()
    chunks: list[Chunk] = []
    for section in doc.sections:
        windows = _windows(_pieces(section.text, config.max_chars), config)
        for number, (start, end) in enumerate(windows):
            chunks.append(
                Chunk(
                    chunk_id=(
                        f"{doc.source_id}:{doc.raw_sha256[:12]}:s{section.index:03d}:c{number:03d}"
                    ),
                    source_id=doc.source_id,
                    raw_sha256=doc.raw_sha256,
                    retrieved_at=doc.retrieved_at,
                    final_url=doc.final_url,
                    page_title=doc.page_title,
                    date_modified=doc.date_modified,
                    section_index=section.index,
                    section_heading=section.heading,
                    section_path=section.path,
                    anchor=section.anchor,
                    chunk_index=number,
                    chunk_count=len(windows),
                    section_start=start,
                    section_end=end,
                    text=section.text[start:end],
                )
            )
    return tuple(chunks)
