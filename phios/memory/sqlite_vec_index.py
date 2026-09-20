from __future__ import annotations

import json
import math
import sqlite3
import struct
from pathlib import Path

from .models import EmbeddingIdentity, VectorCandidate
from .validation import strict_canonical_json

EXPECTED_SQLITE_VEC_VERSION = "0.1.9"
MAX_SEARCH_LIMIT = 50


def _serialize_f32(vector: tuple[float, ...], *, dimensions: int) -> bytes:
    if len(vector) != dimensions:
        raise ValueError("vector dimension mismatch")
    values: list[float] = []
    for value in vector:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("vector values must be finite")
        values.append(number)
    return struct.pack(f"{dimensions}f", *values)


class SqliteVecIndex:
    """Disposable sqlite-vec generation containing only derived vectors and linkage."""

    def __init__(self, path: Path, *, identity: EmbeddingIdentity) -> None:
        self.path = path.expanduser()
        self.embedding_identity = identity
        self.generation_id = identity.generation_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def available(self) -> bool:
        return True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.enable_load_extension(True)
            try:
                import sqlite_vec  # type: ignore[import-not-found]

                sqlite_vec.load(conn)
            finally:
                conn.enable_load_extension(False)
            version = str(conn.execute("SELECT vec_version()").fetchone()[0]).removeprefix("v")
            if version != EXPECTED_SQLITE_VEC_VERSION:
                raise RuntimeError(
                    f"sqlite-vec version {version!r} does not match "
                    f"{EXPECTED_SQLITE_VEC_VERSION!r}"
                )
            conn.set_authorizer(self._authorizer)
            conn.execute("PRAGMA trusted_schema=OFF")
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def _authorizer(
        action: int,
        arg1: str | None,
        arg2: str | None,
        database: str | None,
        source: str | None,
    ) -> int:
        del database, source
        if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            function_name = (arg2 or arg1 or "").lower()
            if function_name in {"load_extension", "vec_npy_file"}:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vectors (
                    record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    PRIMARY KEY (record_id, revision)
                );
                """
            )
            expected = {
                "generation_id": self.generation_id,
                "embedding_identity": strict_canonical_json(self.embedding_identity.to_dict()),
                "schema_version": "phios.sqlite_vec_index.v0.1",
                "sqlite_vec_version": EXPECTED_SQLITE_VEC_VERSION,
            }
            for key, value in expected.items():
                row = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
                if row is None:
                    conn.execute("INSERT INTO metadata(key, value) VALUES(?,?)", (key, value))
                elif str(row["value"]) != value:
                    raise RuntimeError(f"derived index metadata mismatch for {key}")

    def upsert(
        self,
        *,
        record_id: str,
        revision: int,
        record_sha256: str,
        vector: tuple[float, ...],
        identity: EmbeddingIdentity,
    ) -> None:
        if identity != self.embedding_identity:
            raise RuntimeError("embedding identity does not match active index generation")
        blob = _serialize_f32(vector, dimensions=self.embedding_identity.dimensions)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO vectors(record_id, revision, record_sha256, embedding)
                VALUES(?,?,?,?)
                ON CONFLICT(record_id, revision) DO UPDATE SET
                    record_sha256=excluded.record_sha256,
                    embedding=excluded.embedding
                """,
                (record_id, revision, record_sha256, blob),
            )

    def remove(self, record_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM vectors WHERE record_id=?", (record_id,))

    def search(
        self,
        vector: tuple[float, ...],
        *,
        eligible_versions: tuple[tuple[str, int, str], ...],
        limit: int,
    ) -> tuple[VectorCandidate, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= MAX_SEARCH_LIMIT):
            raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")
        if not eligible_versions:
            return ()
        blob = _serialize_f32(vector, dimensions=self.embedding_identity.dimensions)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TEMP TABLE IF NOT EXISTS eligible (
                    record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    PRIMARY KEY(record_id, revision, record_sha256)
                ) WITHOUT ROWID
                """
            )
            conn.execute("DELETE FROM eligible")
            conn.executemany(
                "INSERT INTO eligible(record_id, revision, record_sha256) VALUES(?,?,?)",
                eligible_versions,
            )
            rows = conn.execute(
                """
                SELECT
                    v.record_id,
                    v.revision,
                    v.record_sha256,
                    vec_distance_l2(?, v.embedding) AS distance
                FROM vectors v
                INNER JOIN eligible e
                  ON e.record_id=v.record_id
                 AND e.revision=v.revision
                 AND e.record_sha256=v.record_sha256
                ORDER BY distance ASC, v.record_id ASC, v.revision ASC
                LIMIT ?
                """,
                (blob, limit),
            ).fetchall()
        candidates: list[VectorCandidate] = []
        for row in rows:
            distance = float(row["distance"])
            if not math.isfinite(distance):
                continue
            candidates.append(
                VectorCandidate(
                    record_id=str(row["record_id"]),
                    revision=int(row["revision"]),
                    record_sha256=str(row["record_sha256"]),
                    retrieval_distance=distance,
                )
            )
        return tuple(candidates)

    def vector_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0])

    def metadata(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}
