"""The real backend: the local database, bge-m3 and the local generator."""

from __future__ import annotations

from collections.abc import Sequence

from bfs_reg_copilot.api.schemas import Citation
from bfs_reg_copilot.api.service import Backend
from bfs_reg_copilot.embed.ollama import EmbedError
from bfs_reg_copilot.gateway.types import GatewayError
from bfs_reg_copilot.rag.factory import build_baseline
from bfs_reg_copilot.store import db
from bfs_reg_copilot.store.db import Conn

# Failures of something we depend on. A bug in our own code is not in this list on purpose:
# it should surface as a 500, not be hidden as "try again".
DEPENDENCY_ERRORS: tuple[type[Exception], ...] = (GatewayError, EmbedError, db.Error)


class DbProvenanceSource:
    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def lookup(self, chunk_ids: Sequence[str]) -> dict[str, Citation]:
        if not chunk_ids:
            return {}
        cur = self._conn.cursor()
        cur.execute(
            "SELECT chunk_id, source_id, section_path, page_title, final_url, retrieved_at,"
            " date_modified, raw_sha256 FROM chunks WHERE chunk_id = ANY(%s)",
            (list(chunk_ids),),
        )
        rows = cur.fetchall()
        self._conn.rollback()  # end the read transaction; this object only reads
        return {
            str(r[0]): Citation(
                chunk_id=str(r[0]),
                source_id=str(r[1]),
                section_path=[str(p) for p in r[2]],
                page_title=str(r[3]),
                url=str(r[4]),
                retrieved_at=r[5],
                date_modified=None if r[6] is None else str(r[6]),
                raw_sha256=str(r[7]),
            )
            for r in rows
        }


def build_backend() -> Backend:
    conn = db.connect()
    try:
        pipeline = build_baseline(conn)
    except BaseException:
        conn.close()
        raise
    return Backend(pipeline=pipeline, provenance=DbProvenanceSource(conn), close=conn.close)
