"""Load and validate the register from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from bfs_reg_copilot.registry.models import Register


def load_register(path: Path) -> Register:
    """Parse ``path`` and return a validated :class:`Register`.

    Raises ``ValueError`` if the file is not a YAML mapping and
    ``pydantic.ValidationError`` (a ``ValueError`` subclass) if the content breaks a rule.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"{path}: expected a YAML mapping at the top level"
        raise ValueError(msg)
    return Register.model_validate(raw)
