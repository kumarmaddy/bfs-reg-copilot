"""Storage tests. The first group needs no database; the second runs only when
BFS_TEST_DATABASE_URL points at a Postgres with pgvector and a role allowed to create databases.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bfs_reg_copilot.ingest.chunk_store import write_chunks
from bfs_reg_copilot.ingest.chunking import Chunk
from bfs_reg_copilot.store.db import (
    EMBEDDING_DIMS,
    Conn,
    Error,
    connect,
    describe,
    parse_url,
    transaction,
)
from bfs_reg_copilot.store.loader import (
    COLUMNS,
    chunk_to_row,
    counts,
    current_chunk_files,
    load_source,
)
from bfs_reg_copilot.store.migrate import (
    MIGRATIONS_DIR,
    MigrationError,
    applied_versions,
    apply_pending,
    discover,
)

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def make_chunk(
    source: str = "S-TEST",
    sha: str = "a" * 64,
    n: int = 1,
    text: str = "Banks must assess model risk.",
    retrieved_at: datetime = T0,
) -> Chunk:
    return Chunk(
        chunk_id=f"{source}:{sha[:12]}:s001:c{n:03d}",
        source_id=source,
        raw_sha256=sha,
        retrieved_at=retrieved_at,
        final_url="https://example.test/page",
        page_title="Test page",
        date_modified=None,
        section_index=1,
        section_heading="Scope",
        section_path=("Test page", "Scope"),
        anchor=None,
        chunk_index=n - 1,
        chunk_count=2,
        section_start=0,
        section_end=len(text),
        text=text,
    )


# --- no database needed ------------------------------------------------------------------------


def test_real_migrations_are_valid_and_checksummed() -> None:
    migrations = discover()
    assert migrations[0].version == "0001"
    assert len({m.checksum for m in migrations}) == len(migrations)


def test_migration_vector_size_matches_python_constant() -> None:
    text = (MIGRATIONS_DIR / "0001_init.sql").read_text(encoding="utf-8")
    sizes = {int(n) for n in re.findall(r"vector\((\d+)\)", text)}
    assert sizes == {EMBEDDING_DIMS}


def test_discover_rejects_gaps_and_odd_names(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0003_c.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="versions must be"):
        discover(tmp_path)
    (tmp_path / "0003_c.sql").unlink()
    (tmp_path / "notes.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="expected a name"):
        discover(tmp_path)


def test_every_chunk_field_has_a_column() -> None:
    """A new Chunk field must be stored or knowingly dropped, never silently lost."""
    assert set(COLUMNS) == set(Chunk.model_fields)
    assert set(chunk_to_row(make_chunk())) == set(COLUMNS)


def test_current_file_is_the_most_recently_retrieved(tmp_path: Path) -> None:
    old = make_chunk(sha="1" * 64, retrieved_at=T0)
    new = make_chunk(sha="2" * 64, retrieved_at=T0 + timedelta(days=3))
    write_chunks(tmp_path, (old,), "1")
    write_chunks(tmp_path, (new,), "1")
    other = make_chunk(source="S-OTHER")
    write_chunks(tmp_path, (other,), "1")
    files = current_chunk_files(tmp_path)
    assert set(files) == {"S-TEST", "S-OTHER"}
    assert files["S-TEST"].name.startswith("2" * 64)
    assert set(current_chunk_files(tmp_path, only="S-OTHER")) == {"S-OTHER"}


def test_parse_url_and_describe_hide_the_password() -> None:
    url = "postgresql://bfs:p%40ss@db.example:5433/mydb"
    assert parse_url(url) == {
        "host": "db.example",
        "port": 5433,
        "database": "mydb",
        "user": "bfs",
        "password": "p@ss",
    }
    assert describe(url) == "db.example:5433/mydb"
    with pytest.raises(ValueError, match="postgresql://"):
        parse_url("mysql://x@y/z")


# --- database needed ---------------------------------------------------------------------------

ADMIN_URL = os.environ.get("BFS_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not ADMIN_URL, reason="set BFS_TEST_DATABASE_URL to run")


def _with_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


@pytest.fixture
def conn() -> Iterator[Conn]:
    """A connection to a brand-new, empty database that is dropped afterwards."""
    assert ADMIN_URL
    name = f"bfs_test_{uuid.uuid4().hex[:10]}"
    admin = connect(ADMIN_URL)
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{name}"')
    connection = connect(_with_db(ADMIN_URL, name))
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


INSERT_ONE = (
    "INSERT INTO chunk_embeddings (chunk_id, model, embedding) VALUES (%s, 'm', %s::vector)"
)


def vec(first: float, size: int = EMBEDDING_DIMS) -> str:
    return "[" + ",".join([str(first)] + ["0"] * (size - 1)) + "]"


@needs_db
def test_migrate_creates_schema_and_is_idempotent(conn: Conn) -> None:
    assert applied_versions(conn) == {}
    assert apply_pending(conn, discover()) == ["0001"]
    assert apply_pending(conn, discover()) == []
    assert set(applied_versions(conn)) == {"0001"}


@needs_db
def test_edited_migration_is_refused(migrated: Conn, tmp_path: Path) -> None:
    (tmp_path / "0001_init.sql").write_text("SELECT 'a different file';")
    with pytest.raises(MigrationError, match="edited after it was applied"):
        apply_pending(migrated, discover(tmp_path))


@needs_db
def test_database_ahead_of_code_is_refused(migrated: Conn, tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="does not know"):
        apply_pending(migrated, ())


@needs_db
def test_failed_migration_leaves_nothing_behind(conn: Conn, tmp_path: Path) -> None:
    (tmp_path / "0001_good.sql").write_text("CREATE TABLE ok (id int);")
    (tmp_path / "0002_bad.sql").write_text("CREATE TABLE ok2 (id int); SELECT nope;")
    with pytest.raises(Error):
        apply_pending(conn, discover(tmp_path))
    assert applied_versions(conn) == {}
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('ok')")
    assert tuple(cur.fetchone() or ()) == (None,)


@needs_db
def test_load_is_idempotent_and_reports_changes(migrated: Conn, tmp_path: Path) -> None:
    chunks = (make_chunk(n=1), make_chunk(n=2, text="Second chunk about governance."))
    path = write_chunks(tmp_path, chunks, "1")
    first = load_source(migrated, "S-TEST", path)
    assert (first.inserted, first.unchanged, first.changed) == (2, 0, 0)
    second = load_source(migrated, "S-TEST", path)
    assert (second.inserted, second.unchanged, second.changed) == (0, 2, 0)
    assert counts(migrated) == [("S-TEST", 2, 0)]


@needs_db
def test_changed_text_drops_its_stale_embedding(migrated: Conn, tmp_path: Path) -> None:
    sha = "b" * 64
    path = write_chunks(tmp_path, (make_chunk(sha=sha, n=1), make_chunk(sha=sha, n=2)), "1")
    load_source(migrated, "S-TEST", path)
    for n in (1, 2):
        migrated.cursor().execute(
            INSERT_ONE,
            (f"S-TEST:{sha[:12]}:s001:c{n:03d}", vec(1.0)),
        )
    migrated.commit()
    assert counts(migrated) == [("S-TEST", 2, 2)]
    edited = (make_chunk(sha=sha, n=1), make_chunk(sha=sha, n=2, text="Reworded by a re-chunk."))
    result = load_source(migrated, "S-TEST", write_chunks(tmp_path / "v2", edited, "2"))
    assert (result.unchanged, result.changed) == (1, 1)
    assert counts(migrated) == [("S-TEST", 2, 1)]


@needs_db
def test_new_page_version_supersedes_the_old_one(migrated: Conn, tmp_path: Path) -> None:
    old = write_chunks(tmp_path / "a", (make_chunk(sha="1" * 64),), "1")
    new = write_chunks(tmp_path / "b", (make_chunk(sha="2" * 64),), "1")
    load_source(migrated, "S-TEST", old)
    result = load_source(migrated, "S-TEST", new)
    assert result.superseded == 1
    assert counts(migrated) == [("S-TEST", 1, 0)]
    cur = migrated.cursor()
    cur.execute("SELECT count(*) FROM chunks")
    assert tuple(cur.fetchone() or ()) == (2,)  # the old version is kept, not deleted
    # loading the old file again makes it current and supersedes the newer one
    load_source(migrated, "S-TEST", old)
    cur = migrated.cursor()
    cur.execute("SELECT chunk_id FROM chunks WHERE superseded_at IS NULL")
    assert [tuple(r) for r in cur.fetchall()] == [(f"S-TEST:{'1' * 12}:s001:c001",)]


@needs_db
def test_wrong_source_is_refused(migrated: Conn, tmp_path: Path) -> None:
    path = write_chunks(tmp_path, (make_chunk(source="S-OTHER"),), "1")
    with pytest.raises(ValueError, match="another source"):
        load_source(migrated, "S-TEST", path)
    assert counts(migrated) == []


@needs_db
def test_embedding_size_is_enforced_and_cascade_deletes(migrated: Conn, tmp_path: Path) -> None:
    path = write_chunks(tmp_path, (make_chunk(),), "1")
    load_source(migrated, "S-TEST", path)
    chunk_id = make_chunk().chunk_id
    with pytest.raises(Error), transaction(migrated):
        migrated.cursor().execute(
            INSERT_ONE,
            (chunk_id, vec(1.0, size=768)),
        )
    migrated.cursor().execute(
        INSERT_ONE,
        (chunk_id, vec(1.0)),
    )
    migrated.cursor().execute("DELETE FROM chunks WHERE chunk_id = %s", (chunk_id,))
    cur = migrated.cursor()
    cur.execute("SELECT count(*) FROM chunk_embeddings")
    assert tuple(cur.fetchone() or ()) == (0,)


@needs_db
def test_nearest_vector_and_full_text_queries_work(migrated: Conn, tmp_path: Path) -> None:
    a = make_chunk(n=1, text="Federally regulated institutions must manage model risk.")
    b = make_chunk(n=2, text="Suspicious transaction reports are filed with FINTRAC.")
    load_source(migrated, "S-TEST", write_chunks(tmp_path, (a, b), "1"))
    migrated.cursor().execute(
        INSERT_ONE.replace("(%s, 'm', %s::vector)", "(%s,'m',%s::vector),(%s,'m',%s::vector)"),
        (a.chunk_id, vec(1.0), b.chunk_id, vec(-1.0)),
    )
    cur = migrated.cursor()
    cur.execute(
        "SELECT chunk_id FROM chunk_embeddings WHERE model = 'm' "
        "ORDER BY embedding <=> %s::vector LIMIT 1",
        (vec(0.9),),
    )
    assert tuple(cur.fetchone() or ()) == (a.chunk_id,)
    cur.execute(
        "SELECT chunk_id FROM chunks WHERE text_search @@ websearch_to_tsquery('english', %s)",
        ("model risk",),
    )
    assert [tuple(r) for r in cur.fetchall()] == [(a.chunk_id,)]


@needs_db
@pytest.mark.skipif(not Path("data/curated").is_dir(), reason="no local corpus")
def test_real_corpus_loads_and_matches_the_files(migrated: Conn) -> None:
    files = current_chunk_files(Path("data/curated"))
    assert files
    for source, path in files.items():
        load_source(migrated, source, path)
    stored = {s: n for s, n, _ in counts(migrated)}
    from bfs_reg_copilot.ingest.chunk_store import read_chunks

    assert stored == {s: len(read_chunks(p)) for s, p in files.items()}
