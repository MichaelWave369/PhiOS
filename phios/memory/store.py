from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import MemoryRecord
from .validation import strict_canonical_json

SCHEMA_VERSION = 1


class MemoryStore:
    """Canonical PhiOS-owned memory store. No vector extensions are loaded here."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    expires_at TEXT,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (record_id, revision)
                );
                CREATE TABLE IF NOT EXISTS record_heads (
                    record_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (record_id, revision)
                        REFERENCES records(record_id, revision)
                );
                CREATE TABLE IF NOT EXISTS tombstones (
                    record_id TEXT PRIMARY KEY,
                    deleted_at TEXT NOT NULL,
                    operation_id TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS receipt_outbox (
                    operation_id TEXT PRIMARY KEY,
                    request_sha256 TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS index_work (
                    work_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                """
            )
            row = conn.execute(
                "SELECT value FROM store_metadata WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO store_metadata(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported governed-memory schema version")

    def put_pending(
        self,
        record: MemoryRecord,
        *,
        operation_id: str,
        request_sha256: str,
        receipt_json: str,
    ) -> bool:
        with self._connect() as conn:
            prior = conn.execute(
                "SELECT request_sha256 FROM receipt_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior is not None:
                if prior["request_sha256"] != request_sha256:
                    raise ValueError("operation_id was already used for a different request")
                return False
            tombstone = conn.execute(
                "SELECT 1 FROM tombstones WHERE record_id=?", (record.record_id,)
            ).fetchone()
            if tombstone is not None:
                raise ValueError("tombstoned record_id cannot be reused")
            head = conn.execute(
                "SELECT revision FROM record_heads WHERE record_id=?",
                (record.record_id,),
            ).fetchone()
            expected = 1 if head is None else int(head["revision"]) + 1
            if record.revision != expected:
                raise ValueError(f"revision must be {expected}")
            conn.execute(
                """
                INSERT INTO records(
                    record_id, revision, record_sha256, source_id,
                    scope_id, classification, expires_at, payload_json
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    record.record_id,
                    record.revision,
                    record.record_sha256,
                    record.source_id,
                    record.scope_id,
                    record.classification,
                    record.expires_at,
                    strict_canonical_json(record.to_dict()),
                ),
            )
            conn.execute(
                """
                INSERT INTO record_heads(record_id, revision, published)
                VALUES(?,?,0)
                ON CONFLICT(record_id) DO UPDATE SET
                    revision=excluded.revision,
                    published=0
                """,
                (record.record_id, record.revision),
            )
            conn.execute(
                """
                INSERT INTO receipt_outbox(operation_id, request_sha256, receipt_json, published)
                VALUES(?,?,?,0)
                """,
                (operation_id, request_sha256, receipt_json),
            )
            conn.execute(
                "INSERT INTO index_work(record_id, revision, action) VALUES(?,?, 'upsert')",
                (record.record_id, record.revision),
            )
        return True

    def record_operation_receipt(
        self,
        *,
        operation_id: str,
        request_sha256: str,
        receipt_json: str,
    ) -> bool:
        """Persist a non-mutating/index operation receipt before returning derived data."""

        with self._connect() as conn:
            prior = conn.execute(
                "SELECT request_sha256 FROM receipt_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior is not None:
                if prior["request_sha256"] != request_sha256:
                    raise ValueError("operation_id was already used for a different request")
                return False
            conn.execute(
                """
                INSERT INTO receipt_outbox(operation_id, request_sha256, receipt_json, published)
                VALUES(?,?,?,0)
                """,
                (operation_id, request_sha256, receipt_json),
            )
        return True

    def mark_receipt_published(self, operation_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT receipt_json FROM receipt_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            conn.execute(
                "UPDATE receipt_outbox SET published=1 WHERE operation_id=?",
                (operation_id,),
            )
            payload = json.loads(row["receipt_json"])
            if payload.get("operation") in {"put", "revise"}:
                record_id = payload["record_versions"][0]["record_id"]
                conn.execute(
                    "UPDATE record_heads SET published=1 WHERE record_id=?",
                    (record_id,),
                )

    def pending_receipts(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT receipt_json FROM receipt_outbox WHERE published=0 ORDER BY rowid"
            ).fetchall()
        return [json.loads(row["receipt_json"]) for row in rows]

    def get(self, record_id: str, *, now: datetime | None = None) -> MemoryRecord | None:
        now = now or datetime.now(UTC)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT r.payload_json
                FROM record_heads h
                JOIN records r ON r.record_id=h.record_id AND r.revision=h.revision
                LEFT JOIN tombstones t ON t.record_id=h.record_id
                WHERE h.record_id=? AND h.published=1 AND t.record_id IS NULL
                """,
                (record_id,),
            ).fetchone()
        return self._live_record_from_row(row, now=now)

    def get_current_version(
        self,
        record_id: str,
        revision: int,
        record_sha256: str,
        *,
        now: datetime | None = None,
    ) -> MemoryRecord | None:
        """Hydrate only the still-current, published, live canonical version."""

        now = now or datetime.now(UTC)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT r.payload_json
                FROM record_heads h
                JOIN records r ON r.record_id=h.record_id AND r.revision=h.revision
                LEFT JOIN tombstones t ON t.record_id=h.record_id
                WHERE h.record_id=?
                  AND h.revision=?
                  AND h.published=1
                  AND t.record_id IS NULL
                  AND r.record_sha256=?
                """,
                (record_id, revision, record_sha256),
            ).fetchone()
        return self._live_record_from_row(row, now=now)

    def get_indexable_record(
        self,
        record_id: str,
        revision: int,
        *,
        now: datetime | None = None,
    ) -> MemoryRecord | None:
        """Return only a current/published/live version for derived indexing."""

        now = now or datetime.now(UTC)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT r.payload_json
                FROM record_heads h
                JOIN records r ON r.record_id=h.record_id AND r.revision=h.revision
                LEFT JOIN tombstones t ON t.record_id=h.record_id
                WHERE h.record_id=?
                  AND h.revision=?
                  AND h.published=1
                  AND t.record_id IS NULL
                """,
                (record_id, revision),
            ).fetchone()
        return self._live_record_from_row(row, now=now)

    def list_eligible_versions(
        self,
        *,
        allowed_scopes: tuple[str, ...],
        allowed_classifications: tuple[str, ...],
        now: datetime | None = None,
    ) -> tuple[tuple[str, int, str], ...]:
        """Return only canonical versions authorized for ranking by the caller's policy."""

        if not allowed_scopes or not allowed_classifications:
            return ()
        now = now or datetime.now(UTC)
        scope_marks = ",".join("?" for _ in allowed_scopes)
        class_marks = ",".join("?" for _ in allowed_classifications)
        sql = f"""
            SELECT r.record_id, r.revision, r.record_sha256
            FROM record_heads h
            JOIN records r ON r.record_id=h.record_id AND r.revision=h.revision
            LEFT JOIN tombstones t ON t.record_id=h.record_id
            WHERE h.published=1
              AND t.record_id IS NULL
              AND r.scope_id IN ({scope_marks})
              AND r.classification IN ({class_marks})
              AND (r.expires_at IS NULL OR r.expires_at > ?)
            ORDER BY r.record_id, r.revision
        """
        params: tuple[object, ...] = (
            *allowed_scopes,
            *allowed_classifications,
            now.astimezone(UTC).isoformat(),
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return tuple(
            (str(row["record_id"]), int(row["revision"]), str(row["record_sha256"]))
            for row in rows
        )

    def list_current_record_ids(
        self,
        *,
        source_ids: tuple[str, ...],
        allowed_scopes: tuple[str, ...],
        allowed_classifications: tuple[str, ...],
        limit: int = 16,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        """Enumerate bounded current canonical IDs within explicit policy bounds."""

        if not source_ids or not allowed_scopes or not allowed_classifications:
            return ()
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 50):
            raise ValueError("limit must be an integer between 1 and 50")
        now = now or datetime.now(UTC)
        source_marks = ",".join("?" for _ in source_ids)
        scope_marks = ",".join("?" for _ in allowed_scopes)
        class_marks = ",".join("?" for _ in allowed_classifications)
        sql = f"""
            SELECT r.record_id
            FROM record_heads h
            JOIN records r ON r.record_id=h.record_id AND r.revision=h.revision
            LEFT JOIN tombstones t ON t.record_id=h.record_id
            WHERE h.published=1
              AND t.record_id IS NULL
              AND r.source_id IN ({source_marks})
              AND r.scope_id IN ({scope_marks})
              AND r.classification IN ({class_marks})
              AND (r.expires_at IS NULL OR r.expires_at > ?)
            ORDER BY r.rowid DESC
            LIMIT ?
        """
        params: tuple[object, ...] = (
            *source_ids,
            *allowed_scopes,
            *allowed_classifications,
            now.astimezone(UTC).isoformat(),
            limit,
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return tuple(str(row["record_id"]) for row in rows)

    def enqueue_reindex(
        self,
        *,
        allowed_scopes: tuple[str, ...],
        allowed_classifications: tuple[str, ...],
        now: datetime | None = None,
    ) -> int:
        """Queue fresh upserts for currently live/published versions in explicit policy bounds."""

        versions = self.list_eligible_versions(
            allowed_scopes=allowed_scopes,
            allowed_classifications=allowed_classifications,
            now=now,
        )
        with self._connect() as conn:
            for record_id, revision, _record_sha256 in versions:
                conn.execute(
                    "INSERT INTO index_work(record_id, revision, action) VALUES(?,?, 'upsert')",
                    (record_id, revision),
                )
        return len(versions)

    def pending_index_work(self, limit: int = 100) -> tuple[dict[str, object], ...]:
        bounded = max(1, min(int(limit), 1000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT work_id, record_id, revision, action
                FROM index_work
                WHERE status='pending'
                ORDER BY work_id
                LIMIT ?
                """,
                (bounded,),
            ).fetchall()
        return tuple(
            {
                "work_id": int(row["work_id"]),
                "record_id": str(row["record_id"]),
                "revision": int(row["revision"]),
                "action": str(row["action"]),
            }
            for row in rows
        )

    def mark_index_work_done(self, work_id: int) -> None:
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE index_work SET status='done' WHERE work_id=? AND status='pending'",
                (work_id,),
            ).rowcount
            if changed != 1:
                raise KeyError(work_id)

    def delete(
        self,
        record_id: str,
        *,
        operation_id: str,
        deleted_at: str,
        request_sha256: str,
        receipt_json: str,
    ) -> bool:
        with self._connect() as conn:
            prior = conn.execute(
                "SELECT request_sha256 FROM receipt_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior is not None:
                if prior["request_sha256"] != request_sha256:
                    raise ValueError("operation_id was already used for a different request")
                return False
            head = conn.execute(
                "SELECT revision FROM record_heads WHERE record_id=?", (record_id,)
            ).fetchone()
            if head is None:
                raise KeyError(record_id)
            conn.execute(
                "INSERT OR IGNORE INTO tombstones(record_id, deleted_at, operation_id) VALUES(?,?,?)",
                (record_id, deleted_at, operation_id),
            )
            conn.execute(
                "INSERT INTO receipt_outbox(operation_id, request_sha256, receipt_json) VALUES(?,?,?)",
                (operation_id, request_sha256, receipt_json),
            )
            conn.execute(
                "INSERT INTO index_work(record_id, revision, action) VALUES(?,?, 'remove')",
                (record_id, int(head["revision"])),
            )
        return True

    def expire_due(self, *, now: datetime) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT h.record_id
                FROM record_heads h
                JOIN records r ON r.record_id=h.record_id AND r.revision=h.revision
                LEFT JOIN tombstones t ON t.record_id=h.record_id
                WHERE t.record_id IS NULL AND r.expires_at IS NOT NULL AND r.expires_at <= ?
                """,
                (now.astimezone(UTC).isoformat(),),
            ).fetchall()
        return [str(row["record_id"]) for row in rows]

    def _live_record_from_row(
        self,
        row: sqlite3.Row | None,
        *,
        now: datetime,
    ) -> MemoryRecord | None:
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        expires_at = payload.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at).astimezone(UTC) <= now.astimezone(UTC):
            return None
        return self._record_from_payload(payload)

    @staticmethod
    def _record_from_payload(payload: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            record_id=str(payload["record_id"]),
            revision=int(payload["revision"]),
            source_id=str(payload["source_id"]),
            source_kind=str(payload["source_kind"]),
            provenance_refs=tuple(str(v) for v in payload["provenance_refs"]),
            created_at=str(payload["created_at"]),
            scope_id=str(payload["scope_id"]),
            classification=str(payload["classification"]),
            retention_policy_id=str(payload["retention_policy_id"]),
            expires_at=str(payload["expires_at"]) if payload.get("expires_at") else None,
            epistemic_kind=str(payload["epistemic_kind"]),  # type: ignore[arg-type]
            derived_from=tuple(str(v) for v in payload["derived_from"]),
            exactness_class=(
                str(payload["exactness_class"])
                if payload.get("exactness_class") is not None
                else None
            ),
            transformation_lineage_sha256s=tuple(
                str(v)
                for v in payload.get("transformation_lineage_sha256s", [])
            ),
            taint_labels=tuple(str(v) for v in payload.get("taint_labels", [])),
            contradicts=tuple(str(v) for v in payload["contradicts"]),
            text=str(payload["text"]),
            content_sha256=str(payload["content_sha256"]),
            record_sha256=str(payload["record_sha256"]),
        )
