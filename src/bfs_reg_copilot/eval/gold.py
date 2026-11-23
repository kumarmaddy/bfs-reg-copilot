"""The gold set: typed items, structural rules, and a check against the stored chunks.

The file holds questions, paraphrased key points and chunk ids only, never corpus text (ADR-0007).
Specification: docs/02-success-metrics.md section 4. Method and limits: docs/12-gold-set.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SOURCE_ID = r"[A-D](?:-[A-Z0-9]+)+"
CHUNK_ID_RE = re.compile(rf"^({SOURCE_ID}):([0-9a-f]{{12}}):s\d{{3}}:c\d{{3}}$")

# Minimums from docs/02 section 4.
MIN_ITEMS = 60
MIN_ANSWERABLE = 40
MIN_REFUSAL = 15
MIN_ADVERSARIAL = 5
MIN_ANSWERABLE_PER_SOURCE = 5
HOLDOUT_SHARE_RANGE = (0.15, 0.25)


class GoldError(Exception):
    """The gold file cannot be read or is not valid."""


class Split(StrEnum):
    DEV = "dev"
    HOLDOUT = "holdout"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PassRule(_Frozen):
    """How many key points a correct answer needs (metric M1)."""

    min_points: int = Field(ge=1)
    required_points: tuple[int, ...] = ()
    text: str


class CorpusVersion(_Frozen):
    """The page version the items were written against."""

    raw_sha256_prefix: str = Field(pattern=r"^[0-9a-f]{12}$")
    page_date: str
    retrieved: str
    url: str


class _ItemBase(_Frozen):
    id: str = Field(pattern=r"^G-[A-Z0-9]+-[A-Z]?\d{2,3}$")
    split: Split
    type: str
    question: str = Field(min_length=10)


class AnswerableItem(_ItemBase):
    kind: Literal["answerable"]
    source: str = Field(pattern=rf"^{SOURCE_ID}$")
    difficulty: Difficulty
    key_points: tuple[str, ...] = Field(min_length=1)
    pass_rule: PassRule
    supporting_chunks: tuple[str, ...] = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def _check(self) -> AnswerableItem:
        count = len(self.key_points)
        rule = self.pass_rule
        if rule.min_points > count:
            raise ValueError(f"{self.id}: min_points {rule.min_points} exceeds {count} key points")
        if any(not 1 <= n <= count for n in rule.required_points):
            raise ValueError(f"{self.id}: required_points must refer to existing key points")
        if len(rule.required_points) > rule.min_points:
            raise ValueError(f"{self.id}: more required points than min_points")
        for chunk_id in self.supporting_chunks:
            match = CHUNK_ID_RE.match(chunk_id)
            if match is None:
                raise ValueError(f"{self.id}: malformed chunk id {chunk_id!r}")
            if match.group(1) != self.source:
                raise ValueError(f"{self.id}: chunk {chunk_id} is not from source {self.source}")
        if len(set(self.supporting_chunks)) != len(self.supporting_chunks):
            raise ValueError(f"{self.id}: duplicate supporting chunk")
        return self


class RefusalItem(_ItemBase):
    kind: Literal["refusal"]
    difficulty: Difficulty
    expected_behaviour: str = Field(min_length=10)
    near_miss: str = ""


class AdversarialItem(_ItemBase):
    kind: Literal["adversarial"]
    expected_behaviour: str = Field(min_length=10)
    scored: bool
    needs_fixture: str = ""

    @model_validator(mode="after")
    def _check(self) -> AdversarialItem:
        if self.needs_fixture and self.scored:
            raise ValueError(f"{self.id}: an item that needs a fixture cannot be scored yet")
        return self


GoldItem = Annotated[
    AnswerableItem | RefusalItem | AdversarialItem,
    Field(discriminator="kind"),
]


class GoldSet(_Frozen):
    version: int
    dataset: str
    created: date
    labelling: str
    split_seed: int
    split_method: str
    corpus: dict[str, CorpusVersion]
    items: tuple[GoldItem, ...]

    @model_validator(mode="after")
    def _check(self) -> GoldSet:
        ids = [item.id for item in self.items]
        duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate item ids: {duplicates}")
        for item in self.items:
            if not isinstance(item, AnswerableItem):
                continue
            if item.source not in self.corpus:
                raise ValueError(f"{item.id}: source {item.source} has no corpus entry")
            prefix = self.corpus[item.source].raw_sha256_prefix
            for chunk_id in item.supporting_chunks:
                if f":{prefix}:" not in chunk_id:
                    raise ValueError(f"{item.id}: chunk {chunk_id} is from another page version")
        return self

    def of_kind(self, kind: str) -> tuple[GoldItem, ...]:
        return tuple(item for item in self.items if item.kind == kind)

    def in_split(self, split: Split) -> tuple[GoldItem, ...]:
        return tuple(item for item in self.items if item.split == split)


def load_gold(path: Path) -> GoldSet:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GoldError(f"cannot read {path}: {exc}") from exc
    try:
        return GoldSet.model_validate(raw)
    except ValidationError as exc:
        raise GoldError(f"{path} is not a valid gold set:\n{exc}") from exc


def check_composition(gold: GoldSet) -> list[str]:
    """Problems against the size and split rules of docs/02 section 4. Empty means fine."""
    problems: list[str] = []
    answerable = [i for i in gold.items if isinstance(i, AnswerableItem)]
    counts = {
        "answerable": (len(answerable), MIN_ANSWERABLE),
        "refusal": (len(gold.of_kind("refusal")), MIN_REFUSAL),
        "adversarial": (len(gold.of_kind("adversarial")), MIN_ADVERSARIAL),
    }
    problems += [
        f"{kind}: {have} items, need at least {need}"
        for kind, (have, need) in counts.items()
        if have < need
    ]
    if len(gold.items) < MIN_ITEMS:
        problems.append(f"total: {len(gold.items)} items, need at least {MIN_ITEMS}")
    for source in gold.corpus:
        have = sum(1 for i in answerable if i.source == source)
        if have < MIN_ANSWERABLE_PER_SOURCE:
            problems.append(f"{source}: {have} answerable items, need {MIN_ANSWERABLE_PER_SOURCE}")
        held = sum(1 for i in answerable if i.source == source and i.split == Split.HOLDOUT)
        if held < 1:
            problems.append(f"{source}: no answerable item in the hold-out")
    share = len(gold.in_split(Split.HOLDOUT)) / len(gold.items)
    low, high = HOLDOUT_SHARE_RANGE
    if not low <= share <= high:
        problems.append(f"hold-out share {share:.0%} is outside {low:.0%} to {high:.0%}")
    problems += [
        f"{i.id}: an unscored item cannot sit in the hold-out"
        for i in gold.of_kind("adversarial")
        if isinstance(i, AdversarialItem) and not i.scored and i.split == Split.HOLDOUT
    ]
    return problems


def _chunk_ids(curated_root: Path, source_id: str) -> set[str]:
    folder = curated_root / source_id
    ids: set[str] = set()
    if not folder.is_dir():
        return ids
    for path in sorted(folder.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(str(json.loads(line)["chunk_id"]))
    return ids


def check_against_chunks(gold: GoldSet, curated_root: Path) -> list[str]:
    """Every supporting chunk id must exist in the stored chunks of the labelled page version."""
    problems: list[str] = []
    stored: dict[str, set[str]] = {}
    for source, version in gold.corpus.items():
        ids = _chunk_ids(curated_root, source)
        stored[source] = ids
        if not ids:
            problems.append(f"{source}: no stored chunks under {curated_root / source}")
        elif not any(f":{version.raw_sha256_prefix}:" in i for i in ids):
            problems.append(
                f"{source}: stored chunks are from a different page version than the one the "
                f"gold set was written against ({version.raw_sha256_prefix}); re-review its items"
            )
    for item in gold.items:
        if not isinstance(item, AnswerableItem):
            continue
        known = stored.get(item.source, set())
        if not known:
            continue
        problems += [
            f"{item.id}: chunk {chunk_id} not found"
            for chunk_id in item.supporting_chunks
            if chunk_id not in known
        ]
    return problems


def summarise(gold: GoldSet) -> list[str]:
    """Plain-text counts for a quick look."""
    lines = [f"{len(gold.items)} items ({gold.dataset} v{gold.version}, created {gold.created})"]
    for kind in ("answerable", "refusal", "adversarial"):
        items = gold.of_kind(kind)
        dev = sum(1 for i in items if i.split == Split.DEV)
        lines.append(f"{kind:<12} {len(items):>3}  dev {dev:>3}  holdout {len(items) - dev:>3}")
    per_source = Counter(i.source for i in gold.items if isinstance(i, AnswerableItem))
    lines += [f"  {source:<14} {count} answerable" for source, count in sorted(per_source.items())]
    return lines
