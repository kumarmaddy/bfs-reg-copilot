"""Tests for the ingestion gate command line."""

from __future__ import annotations

from pathlib import Path

import pytest

from bfs_reg_copilot.ingest.cli import EXIT_INVALID, EXIT_OK, EXIT_REFUSED, EXIT_UNREADABLE, main
from bfs_reg_copilot.registry import load_register

REGISTER_PATH = Path(__file__).resolve().parents[1] / "data" / "sources" / "register.yaml"


def test_list_shows_every_source(capsys: pytest.CaptureFixture[str]) -> None:
    register = load_register(REGISTER_PATH)
    assert main(["--register", str(REGISTER_PATH), "list"]) == EXIT_OK
    out = capsys.readouterr().out
    for source in register.sources:
        assert source.id in out
    for pending in register.pending:
        assert f"PENDING  {pending.id}" in out


def test_check_allows_an_ingestible_source(capsys: pytest.CaptureFixture[str]) -> None:
    source = load_register(REGISTER_PATH).ingestible()[0]
    assert main(["--register", str(REGISTER_PATH), "check", source.id]) == EXIT_OK
    assert capsys.readouterr().out.startswith("ALLOWED:")


def test_check_refuses_a_pending_source(capsys: pytest.CaptureFixture[str]) -> None:
    pending_id = load_register(REGISTER_PATH).pending[0].id
    assert main(["--register", str(REGISTER_PATH), "check", pending_id]) == EXIT_REFUSED
    assert capsys.readouterr().out.startswith("REFUSED:")


def test_check_refuses_an_unknown_source(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--register", str(REGISTER_PATH), "check", "A-NOPE-NOTHING"]) == EXIT_REFUSED
    assert "not in the register" in capsys.readouterr().out


def test_missing_register_is_unreadable(tmp_path: Path) -> None:
    assert main(["--register", str(tmp_path / "missing.yaml"), "list"]) == EXIT_UNREADABLE


def test_invalid_register_is_reported(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")
    assert main(["--register", str(bad), "list"]) == EXIT_INVALID


def test_fetch_refuses_a_pending_source_without_touching_the_store(tmp_path: Path) -> None:
    pending_id = load_register(REGISTER_PATH).pending[0].id
    code = main(["--register", str(REGISTER_PATH), "fetch", pending_id, "--raw-dir", str(tmp_path)])
    assert code == EXIT_REFUSED
    assert list(tmp_path.iterdir()) == []
