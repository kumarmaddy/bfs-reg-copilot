"""Tests for the source and licence register rules."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from bfs_reg_copilot.registry import Register, load_register
from bfs_reg_copilot.registry.cli import EXIT_INVALID, EXIT_OK, EXIT_UNREADABLE, main

REGISTER_PATH = Path(__file__).resolve().parents[1] / "data" / "sources" / "register.yaml"


@pytest.fixture(scope="module")
def raw() -> dict[str, Any]:
    data = yaml.safe_load(REGISTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _ingestible_source(raw: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(next(s for s in raw["sources"] if s["ingest_allowed"]))


def _with_first_source(raw: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(raw)
    data["sources"] = [source]
    data["pending"] = []
    return data


def test_committed_register_is_valid() -> None:
    register = load_register(REGISTER_PATH)
    assert len(register.sources) >= 1
    assert register.ingestible(), "expected at least one ingestible source"


def test_no_source_may_be_redistributed_in_repo() -> None:
    register = load_register(REGISTER_PATH)
    assert all(s.redistribute_in_repo is False for s in register.sources)


def test_every_ingestible_source_has_verified_terms() -> None:
    for source in load_register(REGISTER_PATH).ingestible():
        assert source.verification.primary_page_opened
        assert source.verification.terms_verified_on is not None
        assert source.reproduction_class.value != "unverified"


def test_redistribution_flag_cannot_be_true(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["redistribute_in_repo"] = True
    with pytest.raises(ValidationError):
        Register.model_validate(_with_first_source(raw, source))


def test_blocked_source_requires_reason(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["ingest_allowed"] = False
    source["blocking_reason"] = "  "
    with pytest.raises(ValidationError, match="blocking_reason"):
        Register.model_validate(_with_first_source(raw, source))


def test_unverified_terms_cannot_be_ingestible(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["reproduction_class"] = "unverified"
    with pytest.raises(ValidationError, match="unverified"):
        Register.model_validate(_with_first_source(raw, source))


def test_unopened_primary_page_cannot_be_ingestible(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["verification"]["primary_page_opened"] = False
    with pytest.raises(ValidationError, match="not opened"):
        Register.model_validate(_with_first_source(raw, source))


def test_missing_terms_date_cannot_be_ingestible(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["verification"]["terms_verified_on"] = None
    with pytest.raises(ValidationError, match="terms_verified_on"):
        Register.model_validate(_with_first_source(raw, source))


def test_attribution_template_required_when_attribution_required(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["attribution_template"] = ""
    with pytest.raises(ValidationError, match="attribution_template"):
        Register.model_validate(_with_first_source(raw, source))


def test_superseded_documents_cannot_be_ingestible(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["status"] = "superseded"
    with pytest.raises(ValidationError, match="superseded"):
        Register.model_validate(_with_first_source(raw, source))


def test_plain_http_urls_are_rejected(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["url"] = "http://www.osfi-bsif.gc.ca/en/guidance/example"
    with pytest.raises(ValidationError, match="https"):
        Register.model_validate(_with_first_source(raw, source))


def test_duplicate_ids_are_rejected(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    data = _with_first_source(raw, source)
    data["sources"] = [source, copy.deepcopy(source)]
    with pytest.raises(ValidationError, match="duplicate"):
        Register.model_validate(data)


def test_id_cannot_collide_between_sources_and_pending(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    data = _with_first_source(raw, source)
    data["pending"] = [
        {
            "id": source["id"],
            "title": "Same id as a source",
            "issuer": "Somebody",
            "pack": "A",
            "why_pending": "Testing collisions between lists.",
            "next_action": "Rename it",
        }
    ]
    with pytest.raises(ValidationError, match="duplicate"):
        Register.model_validate(data)


def test_pending_sources_can_never_be_ingestible(raw: dict[str, Any]) -> None:
    data = copy.deepcopy(raw)
    data["pending"][0]["ingest_allowed"] = True
    with pytest.raises(ValidationError):
        Register.model_validate(data)


def test_unknown_fields_are_rejected(raw: dict[str, Any]) -> None:
    source = _ingestible_source(raw)
    source["surprise"] = "typo guard"
    with pytest.raises(ValidationError, match="surprise"):
        Register.model_validate(_with_first_source(raw, source))


def test_cli_validate_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(REGISTER_PATH)]) == EXIT_OK
    assert "OK:" in capsys.readouterr().out


def test_cli_summary_lists_blocked_sources(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["summary", str(REGISTER_PATH)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "blocked sources:" in out
    assert "B-FINTRAC-STR" in out


def test_cli_reports_invalid_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == EXIT_INVALID
    assert "INVALID" in capsys.readouterr().out


def test_cli_reports_missing_file(tmp_path: Path) -> None:
    assert main(["validate", str(tmp_path / "nope.yaml")]) == EXIT_UNREADABLE


def test_cli_reports_malformed_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "broken.yaml"
    bad.write_text("sources: [unclosed\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == EXIT_INVALID
