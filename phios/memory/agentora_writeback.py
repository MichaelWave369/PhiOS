"""R4a: fail-closed, operator-gated Agentora -> governed PhiOS memory adapter.

No network listener is created. This module is invoked only by trusted code
with an explicitly enabled MemoryOperatorRuntime and memory.write authority.
"""
from __future__ import annotations

import hashlib

from .models import MemoryRecord
from .operator import MemoryOperatorRuntime
from .validation import require_nonempty, require_utc_timestamp, strict_canonical_json

PROTOCOL = "phios.agentora.writeback.v1"
_ID_DOMAIN = (PROTOCOL + "\n").encode("utf-8")
_MAX_BODY_BYTES = 32 * 1024


def operation_identity(payload: dict[str, object]) -> dict[str, object]:
    """Stable logical write identity; notes/tags remain part of request conflict check."""
    if not isinstance(payload, dict):
        raise ValueError("writeback payload must be an object")
    raw_session = payload.get("session_id")
    raw_task = payload.get("task_id")
    if not isinstance(raw_session, str) or not isinstance(raw_task, str):
        raise ValueError("session_id and task_id must be strings")
    session = require_nonempty(raw_session, "session_id")
    task = require_nonempty(raw_task, "task_id")
    raw = payload.get("raw_payload")
    if not isinstance(raw, dict):
        raise ValueError("raw_payload must be an object")
    outcome = raw.get("outcome")
    if not isinstance(outcome, dict) or not outcome:
        raise ValueError("raw_payload.outcome must be a nonempty object")
    return {"session_id": session, "task_id": task, "outcome": outcome}


def operation_id(payload: dict[str, object]) -> str:
    identity = operation_identity(payload)
    return hashlib.sha256(_ID_DOMAIN + strict_canonical_json(identity).encode("utf-8")).hexdigest()


def canonical_envelope(payload: dict[str, object], *, created_at_utc: str) -> str:
    operation_identity(payload)
    date = require_utc_timestamp(created_at_utc, "created_at_utc")
    envelope = {"protocol_version": PROTOCOL, "created_at_utc": date, "payload": payload}
    text = strict_canonical_json(envelope)
    if len(text.encode("utf-8")) > _MAX_BODY_BYTES:
        raise ValueError("writeback envelope too large")
    return text


class AgentoraWritebackAdmission:
    """Idempotent local adapter into the existing PhiOS canonical memory store."""

    def __init__(self, runtime: MemoryOperatorRuntime) -> None:
        self.runtime = runtime

    def admit(
        self,
        payload: dict[str, object],
        *,
        created_at_utc: str,
        expected_operation_id: str | None = None,
    ) -> dict[str, object]:
        self.runtime.require_enabled()
        if not self.runtime.authority.allows("memory.write"):
            raise PermissionError("memory.write authority is required")
        identity = operation_identity(payload)
        op_id = operation_id(payload)
        if expected_operation_id is not None and op_id != expected_operation_id:
            raise ValueError("operation identity mismatch")
        body = canonical_envelope(payload, created_at_utc=created_at_utc)
        record = MemoryRecord.build(
            record_id="agentora-writeback-" + op_id,
            revision=1,
            source_id="agentora",
            source_kind="service",
            provenance_refs=("agentora:" + str(identity["task_id"]),),
            created_at=require_utc_timestamp(created_at_utc, "created_at_utc"),
            scope_id=self.runtime.config.scopes[0],
            classification=self.runtime.config.classifications[0],
            retention_policy_id=self.runtime.config.retention_policy_id,
            expires_at=None,
            epistemic_kind="source",
            text=body,
        )
        previously_seen = self.runtime.store.operation_receipt_status(op_id) is not None
        result = self.runtime.put(record, operation_id=op_id, task_id=str(identity["task_id"]))
        receipt = self.runtime.store.operation_receipt_status(op_id)
        if result.status not in {"ok", "unavailable"}:
            return {"ok": False, "operation_id": op_id, "state": result.status,
                    "error_code": result.error_code}
        if receipt is None:
            return {"ok": False, "operation_id": op_id, "state": "unavailable",
                    "error_code": result.error_code or "RECEIPT_MISSING"}
        return {
            "ok": receipt["state"] == "published",
            "operation_id": op_id,
            "state": receipt["state"],
            "receipt_id": receipt["receipt_id"],
            "record_id": receipt["record_id"],
            "replayed": previously_seen,
        }

    def status(self, operation: str) -> dict[str, object]:
        self.runtime.require_enabled()
        if not self.runtime.authority.allows("memory.read"):
            raise PermissionError("memory.read authority is required")
        if not isinstance(operation, str) or len(operation) != 64:
            raise ValueError("operation id must be a SHA-256 hex digest")
        try:
            int(operation, 16)
        except ValueError as exc:
            raise ValueError("operation id must be a SHA-256 hex digest") from exc
        saved = self.runtime.store.operation_receipt_status(operation)
        if saved is None:
            return {"ok": False, "operation_id": operation, "state": "not_found"}
        return {
            "ok": saved["state"] == "published",
            "operation_id": operation,
            "state": saved["state"],
            "receipt_id": saved["receipt_id"],
            "record_id": saved["record_id"],
        }
