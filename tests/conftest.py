"""Database fixtures: each test gets a brand-new empty database that is dropped afterwards."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from bfs_reg_copilot.store.db import Conn, connect
from bfs_reg_copilot.store.migrate import apply_pending, discover
from dbhelpers import ADMIN_URL, with_db


@pytest.fixture
def conn() -> Iterator[Conn]:
    assert ADMIN_URL
    name = f"bfs_test_{uuid.uuid4().hex[:10]}"
    admin = connect(ADMIN_URL)
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{name}"')
    connection = connect(with_db(ADMIN_URL, name))
    try:
        yield connection
    finally:
        connection.close()
        admin.cursor().execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture
def migrated(conn: Conn) -> Conn:
    apply_pending(conn, discover())
    return conn
