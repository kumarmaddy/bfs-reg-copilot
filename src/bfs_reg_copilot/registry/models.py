"""Typed model of the source and licence register.

The register is the system of record for *what we may ingest and why*. The validation rules
below turn governance decisions (see docs/05-data-statement.md and docs/adr/0007) into checks
that fail the build, so a source cannot be marked ingestible without verified terms.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class Jurisdiction(StrEnum):
    CA = "CA"
    US = "US"


class Pack(StrEnum):
    """Corpus packs. A: Canada prudential. B: Canada AML. C: US federal rules. D: later."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class DocType(StrEnum):
    GUIDELINE = "guideline"
    GUIDANCE = "guidance"
    LETTER = "letter"
    ADVISORY = "advisory"
    REGULATION = "regulation"
    STATUTE = "statute"


class SourceFormat(StrEnum):
    HTML = "html"
    PDF = "pdf"
    XML = "xml"
    JSON = "json"


class DocStatus(StrEnum):
    FINAL = "final"
    DRAFT = "draft"
    SUPERSEDED = "superseded"


class ReproductionClass(StrEnum):
    """How the publisher's terms treat reproduction. UNVERIFIED blocks ingestion."""

    NON_COMMERCIAL_WITH_ATTRIBUTION = "non_commercial_with_attribution"
    OPEN_LICENCE = "open_licence"
    PUBLIC_DOMAIN = "public_domain"
    UNVERIFIED = "unverified"


_FROZEN = ConfigDict(extra="forbid", frozen=True)


def _require_https(value: HttpUrl) -> HttpUrl:
    if value.scheme != "https":
        msg = f"URL must use https: {value}"
        raise ValueError(msg)
    return value


class Verification(BaseModel):
    """Evidence that a human or tool actually looked at the primary source and its terms."""

    model_config = _FROZEN

    primary_page_opened: bool
    terms_verified_on: date | None = None
    method: str = ""
    notes: str = ""


class Source(BaseModel):
    """One document we may ingest."""

    model_config = _FROZEN

    id: str = Field(pattern=r"^[A-D](-[A-Z0-9]+)+$")
    title: str = Field(min_length=3)
    issuer: str = Field(min_length=2)
    jurisdiction: Jurisdiction
    pack: Pack
    doc_type: DocType
    url: HttpUrl
    source_format: SourceFormat
    language: Literal["en", "fr"] = "en"
    status: DocStatus
    published_date: date | None = None
    last_modified_observed: date | None = None
    effective_date: date | None = None

    terms_url: HttpUrl
    reproduction_class: ReproductionClass
    terms_summary: str = Field(min_length=10)
    attribution_required: bool
    attribution_template: str = ""

    ingest_allowed: bool
    blocking_reason: str = ""
    # Corpus text is never committed to this public repository (ADR-0007).
    redistribute_in_repo: Literal[False] = False
    retrieved_on: date | None = None

    verification: Verification
    notes: str = ""

    @field_validator("url", "terms_url")
    @classmethod
    def _https_only(cls, value: HttpUrl) -> HttpUrl:
        return _require_https(value)

    @model_validator(mode="after")
    def _ingest_rules(self) -> Self:
        if not self.ingest_allowed:
            if not self.blocking_reason.strip():
                msg = f"{self.id}: ingest_allowed is false, so blocking_reason is required"
                raise ValueError(msg)
            return self

        problems: list[str] = []
        if self.reproduction_class is ReproductionClass.UNVERIFIED:
            problems.append("reproduction_class is unverified")
        if not self.verification.primary_page_opened:
            problems.append("primary page was not opened")
        if self.verification.terms_verified_on is None:
            problems.append("terms_verified_on is missing")
        if self.attribution_required and not self.attribution_template.strip():
            problems.append("attribution_template is required but empty")
        if self.status is DocStatus.SUPERSEDED:
            problems.append("superseded documents must not be ingested")
        if problems:
            msg = f"{self.id}: cannot be ingestible: " + "; ".join(problems)
            raise ValueError(msg)
        return self


class PendingSource(BaseModel):
    """A candidate we have identified but not yet verified. Never ingestible."""

    model_config = _FROZEN

    id: str = Field(pattern=r"^[A-D](-[A-Z0-9]+)+$")
    title: str = Field(min_length=3)
    issuer: str = Field(min_length=2)
    pack: Pack
    why_pending: str = Field(min_length=10)
    next_action: str = Field(min_length=5)
    ingest_allowed: Literal[False] = False


class Register(BaseModel):
    model_config = _FROZEN

    version: int = Field(ge=1)
    updated_on: date
    sources: list[Source] = Field(min_length=1)
    pending: list[PendingSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [s.id for s in self.sources] + [p.id for p in self.pending]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            msg = f"duplicate ids in register: {', '.join(duplicates)}"
            raise ValueError(msg)
        return self

    def ingestible(self) -> list[Source]:
        return [s for s in self.sources if s.ingest_allowed]
