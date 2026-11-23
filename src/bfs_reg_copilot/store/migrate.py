"""Plain-SQL migrations: numbered files, applied in order, each recorded with its checksum.

An applied migration must never be edited. If its file no longer matches the recorded checksum
the run stops, because the database and the repository no longer agree about what was applied.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bfs_reg_copilot.store.db import Conn, transaction

MIGRATIONS_DIR: Final = Path(__file__).parent / "migrations"
_NAME: Final = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_LOCK_KEY: Final = 7_246_001  # arbitrary constant: one migrator at a time


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str
    checksum: str


def discover(directory: Path = MIGRATIONS_DIR) -> tuple[Migration, ...]:
    """Read the migration files. Versions must start at 0001 and have no gaps or duplicates."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if match is None:
            raise MigrationError(f"{path.name}: expected a name like 0001_short_name.sql")
        sql = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        found.append(Migration(match.group(1), match.group(2), sql, digest))
    expected = [f"{i:04d}" for i in range(1, len(found) + 1)]
    if [m.version for m in found] != expected:
        raise MigrationError(
            f"migration versions must be {expected}, found {[m.version for m in found]}"
        )
    return tuple(found)


def applied_versions(conn: Conn) -> dict[str, str]:
    """version -> checksum for what the database has applied (empty if never migrated)."""
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('schema_migrations') IS NOT NULL")
    row = cur.fetchone()
    if row is None or not row[0]:
        return {}
    cur.execute("SELECT version, checksum FROM schema_migrations")
    return {str(v): str(c) for v, c in cur.fetchall()}


def apply_pending(conn: Conn, migrations: tuple[Migration, ...]) -> list[str]:
    """Apply what is missing, in one transaction. Returns the versions applied."""
    done: list[str] = []
    cur = conn.cursor()
    with transaction(conn):
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, name text NOT NULL, checksum text NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        recorded = applied_versions(conn)
        known = {m.version for m in migrations}
        unknown = sorted(set(recorded) - known)
        if unknown:
            raise MigrationError(f"database has migrations this code does not know: {unknown}")
        for m in migrations:
            if m.version in recorded:
                if recorded[m.version] != m.checksum:
                    raise MigrationError(
                        f"migration {m.version}_{m.name} was edited after it was applied; "
                        "add a new migration instead"
                    )
                continue
            cur.execute(m.sql)
            cur.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                (m.version, m.name, m.checksum),
            )
            done.append(m.version)
    return done
