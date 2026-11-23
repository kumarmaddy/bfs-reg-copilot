"""Connecting to the database. The URL comes from the environment, never from a file in the repo.

The driver is pg8000, which is pure Python. The psycopg binary wheel ships a native libpq DLL
that Windows Application Control blocked on the project machine (ADR-0015).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final
from urllib.parse import unquote, urlsplit

import pg8000.dbapi

URL_ENV: Final = "BFS_DATABASE_URL"
# Matches docker-compose.yml: a throwaway local database, listening on loopback only.
DEFAULT_URL: Final = "postgresql://bfs:bfs_dev@127.0.0.1:5433/bfs"
EMBEDDING_DIMS: Final = 1024  # must equal vector(N) in migration 0001; a test checks this

type Conn = pg8000.dbapi.Connection
Error = pg8000.dbapi.Error


def database_url() -> str:
    return os.environ.get(URL_ENV, DEFAULT_URL)


def parse_url(url: str) -> dict[str, str | int]:
    """postgresql://user:password@host:port/dbname -> connection arguments."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgresql", "postgres"):
        raise ValueError("database URL must start with postgresql://")
    args: dict[str, str | int] = {
        "host": parts.hostname or "127.0.0.1",
        "port": parts.port or 5432,
        "database": unquote(parts.path.lstrip("/")) or "postgres",
    }
    if parts.username:
        args["user"] = unquote(parts.username)
    if parts.password:
        args["password"] = unquote(parts.password)
    return args


def describe(url: str) -> str:
    """host:port/dbname without credentials, for messages."""
    a = parse_url(url)
    return f"{a['host']}:{a['port']}/{a['database']}"


def connect(url: str | None = None) -> Conn:
    """Open a connection. Transactions are explicit: use `transaction(conn)`."""
    args = parse_url(url or database_url())
    return pg8000.dbapi.connect(timeout=5, **args)


@contextmanager
def transaction(conn: Conn) -> Iterator[None]:
    """Commit if the block succeeds, roll back if it raises."""
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
