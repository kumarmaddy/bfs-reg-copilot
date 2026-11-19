"""Data-quality checks for the ingestion pipeline (Phase 1 exit criteria).

Every check returns findings instead of raising, so one run reports everything that is wrong.
An ERROR means the data must not be used (lineage broken, text altered or lost, data present for a
source the register does not allow). A WARNING means a human should look (page chrome leaked in,
the page looks only partly captured, a stale retrieval). The codes are listed in
docs/09-data-quality-checks.md.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from bfs_reg_copilot.ingest.chunk_store import chunks_path, read_chunks
from bfs_reg_copilot.ingest.chunking import Chunk, ChunkingConfig
from bfs_reg_copilot.ingest.clean import CLEANER_VERSION
from bfs_reg_copilot.ingest.cleaned_store import CleanedDocument, cleaned_file, read_cleaned
from bfs_reg_copilot.ingest.store import RawRecord, RawStore, RawStoreError
from bfs_reg_copilot.registry import Register, Source


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    source_id: str | None
    message: str

    def line(self) -> str:
        where = self.source_id or "-"
        return f"{self.severity.value:<7} {self.code}  {where}  {self.message}"


@dataclass(frozen=True)
class DqConfig:
    max_chars: int = ChunkingConfig().max_chars
    max_age_days: int = 180
    min_total_chars: int = 1000
    min_page_coverage: float = 0.85
    duplicate_min_chars: int = 80
    # Text that belongs to page furniture, never to the guidance itself.
    chrome_phrases: tuple[str, ...] = (
        "report a problem or mistake on this page",
        "skip to main content",
        "share this page",
        "top of page",
        "was this page helpful",
        "date modified",
    )


@dataclass
class DqReport:
    findings: list[Finding] = field(default_factory=list)
    chunks_checked: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    def ok(self, *, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MOJIBAKE = re.compile(r"\xc3[\x80-\xbf]|\xe2\u20ac|\xc2\xa0")  # UTF-8 read as Latin-1/cp1252


def _err(code: str, source_id: str | None, message: str) -> Finding:
    return Finding(code, Severity.ERROR, source_id, message)


def _warn(code: str, source_id: str | None, message: str) -> Finding:
    return Finding(code, Severity.WARNING, source_id, message)


# -- checks on one source's chunks -------------------------------------------------------------


def check_chunk_lineage(
    source: Source,
    records: list[RawRecord],
    chunks: tuple[Chunk, ...],
    now: datetime,
    config: DqConfig,
) -> list[Finding]:
    """DQ-01 to DQ-04: every chunk traces to this register entry and a real retrieval."""
    findings: list[Finding] = []
    known = {(r.sha256, r.retrieved_at) for r in records}
    registered_host = urlsplit(str(source.url)).hostname
    reported: set[str] = set()

    def once(finding: Finding) -> None:
        if finding.message not in reported:
            reported.add(finding.message)
            findings.append(finding)

    for chunk in chunks:
        if chunk.source_id != source.id:
            once(_err("DQ-01", source.id, f"chunk {chunk.chunk_id} names source {chunk.source_id}"))
        if not source.ingest_allowed:
            once(_err("DQ-01", source.id, "chunks exist for a source the register blocks"))
        if (chunk.raw_sha256, chunk.retrieved_at) not in known:
            once(
                _err(
                    "DQ-02",
                    source.id,
                    f"no stored retrieval matches hash {chunk.raw_sha256[:12]} at "
                    f"{chunk.retrieved_at.isoformat()}",
                )
            )
        parts = urlsplit(chunk.final_url)
        if parts.scheme != "https" or parts.hostname != registered_host:
            once(
                _err("DQ-03", source.id, f"final URL {chunk.final_url} is not on {registered_host}")
            )
        offset = chunk.retrieved_at.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            once(_err("DQ-04", source.id, "retrieval time is not UTC"))
        if chunk.retrieved_at > now:
            once(_err("DQ-04", source.id, "retrieval time is in the future"))
        elif now - chunk.retrieved_at > timedelta(days=config.max_age_days):
            once(_warn("DQ-04", source.id, f"retrieved more than {config.max_age_days} days ago"))
    return findings


def check_chunk_integrity(
    source_id: str, doc: CleanedDocument, chunks: tuple[Chunk, ...], config: DqConfig
) -> list[Finding]:
    """DQ-05/06/08/10/11/12: chunks are faithful to the cleaned page and cover all of it."""
    findings: list[Finding] = []
    sections = {s.index: s for s in doc.sections}
    if not chunks:
        return [_err("DQ-12", source_id, "no chunks were produced")]
    if sum(len(c.text) for c in chunks) < config.min_total_chars:
        findings.append(_warn("DQ-12", source_id, "very little text; was the page fully captured?"))

    ids = Counter(c.chunk_id for c in chunks)
    for chunk_id, count in ids.items():
        if count > 1:
            findings.append(_err("DQ-06", source_id, f"chunk id {chunk_id} appears {count} times"))

    covered: dict[int, list[bool]] = {i: [False] * len(s.text) for i, s in sections.items()}
    for chunk in chunks:
        section = sections.get(chunk.section_index)
        if section is None:
            findings.append(_err("DQ-05", source_id, f"{chunk.chunk_id}: section does not exist"))
            continue
        if chunk.text != section.text[chunk.section_start : chunk.section_end]:
            findings.append(
                _err("DQ-05", source_id, f"{chunk.chunk_id}: text differs from its section")
            )
        if chunk.section_path != section.path:
            findings.append(_err("DQ-05", source_id, f"{chunk.chunk_id}: heading path differs"))
        if not chunk.text.strip() or len(chunk.text) > config.max_chars:
            findings.append(
                _err("DQ-06", source_id, f"{chunk.chunk_id}: empty or over {config.max_chars}")
            )
        for position in range(chunk.section_start, min(chunk.section_end, len(section.text))):
            covered[chunk.section_index][position] = True
        if _CONTROL.search(chunk.text) or "�" in chunk.text:
            findings.append(
                _err("DQ-11", source_id, f"{chunk.chunk_id}: control or replacement character")
            )
        if _MOJIBAKE.search(chunk.text):
            findings.append(
                _warn("DQ-11", source_id, f"{chunk.chunk_id}: looks like garbled encoding")
            )
        lowered = chunk.text.lower()
        for phrase in config.chrome_phrases:
            if phrase in lowered:
                findings.append(
                    _warn("DQ-07", source_id, f"{chunk.chunk_id}: contains page chrome {phrase!r}")
                )

    for index, flags in covered.items():
        lost = sum(
            1 for i, ch in enumerate(sections[index].text) if not ch.isspace() and not flags[i]
        )
        if lost:
            findings.append(
                _err("DQ-08", source_id, f"section {index}: {lost} characters are in no chunk")
            )
    for index in sections:
        mine = sorted(c.chunk_index for c in chunks if c.section_index == index)
        if mine != list(range(len(mine))) or any(
            c.chunk_count != len(mine) for c in chunks if c.section_index == index
        ):
            findings.append(
                _err("DQ-06", source_id, f"section {index}: chunk numbering is inconsistent")
            )

    texts = Counter(c.text for c in chunks if len(c.text) >= config.duplicate_min_chars)
    for text, count in texts.items():
        if count > 1:
            findings.append(
                _warn("DQ-10", source_id, f"{count} chunks have identical text: {text[:50]!r}")
            )
    return findings


def check_page_coverage(
    source_id: str, html: bytes, doc: CleanedDocument, config: DqConfig
) -> list[Finding]:
    """DQ-09: the cleaned text should be most of what the page's main area contains."""
    main = BeautifulSoup(html, "html.parser").find("main")
    if not isinstance(main, Tag):
        return [_warn("DQ-09", source_id, "raw page has no <main>; coverage cannot be measured")]
    for junk in main.find_all(["script", "style", "noscript"]):
        junk.decompose()
    page_chars = sum(1 for ch in main.get_text() if not ch.isspace())
    kept = sum(1 for s in doc.sections for ch in s.text if not ch.isspace())
    if page_chars and kept / page_chars < config.min_page_coverage:
        ratio = kept / page_chars
        return [
            _warn("DQ-09", source_id, f"cleaned text is only {ratio:.0%} of the page's main text")
        ]
    return []


# -- checks across the whole data folder ---------------------------------------------------------


def check_governance_leaks(
    register: Register, raw_root: Path, cleaned_root: Path, curated_root: Path
) -> list[Finding]:
    """DQ-14: nothing may be stored for a source the register has not cleared."""
    allowed = {s.id for s in register.ingestible()}
    known = {s.id for s in register.sources} | {p.id for p in register.pending}
    findings: list[Finding] = []
    for root in (raw_root, cleaned_root, curated_root):
        if not root.exists():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            if folder.name in allowed:
                continue
            why = "is not ingestible" if folder.name in known else "is not in the register"
            findings.append(
                _err("DQ-14", folder.name, f"{root.name}/{folder.name} exists but source {why}")
            )
    return findings


_CORPUS_DIRS = ("data/raw/", "data/cleaned/", "data/curated/", "data/embeddings/")


def check_repo_hygiene(repo_root: Path) -> list[Finding]:
    """DQ-15: corpus folders are git-ignored and nothing outside data/sources/ is tracked."""
    findings: list[Finding] = []
    ignore = repo_root / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    findings += [
        _err("DQ-15", None, f".gitignore does not list {folder}")
        for folder in _CORPUS_DIRS
        if folder not in lines
    ]
    git = shutil.which("git")
    if git is None or not (repo_root / ".git").exists():
        return (
            findings  # not a git checkout (for example a zip); the ignore rules were still checked
        )
    tracked = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [git, "-C", str(repo_root), "ls-files", "--", "data"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    findings += [
        _err("DQ-15", None, f"{name} is tracked by git")
        for name in tracked
        if not name.startswith("data/sources/")
    ]
    return findings


# -- the whole run -------------------------------------------------------------------------------


def run_dq(
    register: Register,
    *,
    raw_root: Path,
    cleaned_root: Path,
    curated_root: Path,
    repo_root: Path | None = None,
    now: datetime | None = None,
    config: DqConfig | None = None,
) -> DqReport:
    config = config or DqConfig()
    now = now or datetime.now(UTC)
    store = RawStore(raw_root)
    report = DqReport()
    report.findings += check_governance_leaks(register, raw_root, cleaned_root, curated_root)

    for source in register.ingestible():
        records = store.records(source.id)
        if not records:
            report.findings.append(_warn("DQ-13", source.id, "not fetched yet"))
            continue
        latest = records[-1]
        chunk_file = chunks_path(curated_root, source.id, latest.sha256, CLEANER_VERSION)
        cleaned = cleaned_file(cleaned_root, source.id, latest.sha256)
        if not cleaned.exists() or not chunk_file.exists():
            report.findings.append(
                _warn("DQ-13", source.id, "fetched, but not cleaned and chunked yet")
            )
            continue
        try:
            html = store.read_body(latest)
        except RawStoreError as exc:
            report.findings.append(_err("DQ-02", source.id, str(exc)))
            continue
        doc = read_cleaned(cleaned)
        chunks = read_chunks(chunk_file)
        report.chunks_checked[source.id] = len(chunks)
        report.findings += check_chunk_lineage(source, records, chunks, now, config)
        report.findings += check_chunk_integrity(source.id, doc, chunks, config)
        report.findings += check_page_coverage(source.id, html, doc, config)

    if repo_root is not None:
        report.findings += check_repo_hygiene(repo_root)
    return report
