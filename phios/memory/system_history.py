from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from phios.mandala import ExactnessClass, TransformationLineageBuilder
from phios.memory.models import MemoryRecord, MemoryResult
from phios.memory.operator import MemoryOperatorRuntime
from phios.memory.validation import strict_canonical_json

SYSTEM_STATE_SCHEMA = "phios.system-state.v1"
SYSTEM_CHANGE_SCHEMA = "phios.system-change.v1"
SYSTEM_STATE_SOURCE = "phios-system-state-composer"
SYSTEM_CHANGE_SOURCE = "phios-system-change-deriver"
BRIDGE_VERSION = "phios.memory.system-history.v0.11"


@dataclass(frozen=True, kw_only=True)
class PersistedSystemHistory:
    state_record_ids: tuple[str, str]
    change_record_id: str
    state_receipt_ids: tuple[str | None, str | None]
    change_receipt_id: str | None
    persistent: bool = True
    canonical: bool = True
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False


def _require_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_false(value: object, field: str) -> None:
    if value is not False:
        raise ValueError(f"{field} must be false")


def _sha256_hex(value: object, field: str) -> str:
    raw = _require_string(value, field)
    normalized = raw.removeprefix("sha256:")
    if len(normalized) != 64:
        raise ValueError(f"{field} must be a SHA-256 digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError(f"{field} must be a SHA-256 digest") from exc
    return normalized.lower()


def _canonical_text(value: Mapping[str, Any]) -> str:
    return strict_canonical_json(dict(value))


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _state_record_id(receipt_digest: str) -> str:
    return f"phishell.system-state.{receipt_digest}"


def _change_record_id(change_digest: str) -> str:
    return f"phishell.system-change.{change_digest}"


def _validate_state_receipt(raw: Mapping[str, Any]) -> str:
    if raw.get("schemaVersion") != SYSTEM_STATE_SCHEMA:
        raise ValueError("unsupported system-state schema")
    if raw.get("source") != SYSTEM_STATE_SOURCE:
        raise ValueError("unexpected system-state source")
    _require_false(raw.get("executionAuthority"), "system-state executionAuthority")
    _require_false(raw.get("effectPerformed"), "system-state effectPerformed")
    if raw.get("readOnly") is not True:
        raise ValueError("system-state readOnly must be true")
    return _sha256_hex(raw.get("receiptDigest"), "system-state receiptDigest")


def _validate_change_receipt(raw: Mapping[str, Any]) -> str:
    if raw.get("schemaVersion") != SYSTEM_CHANGE_SCHEMA:
        raise ValueError("unsupported system-change schema")
    if raw.get("source") != SYSTEM_CHANGE_SOURCE:
        raise ValueError("unexpected system-change source")
    if raw.get("causeAssigned") is not False:
        raise ValueError("system-change causeAssigned must be false")
    if raw.get("severityAssigned") is not False:
        raise ValueError("system-change severityAssigned must be false")
    _require_false(raw.get("executionAuthority"), "system-change executionAuthority")
    _require_false(raw.get("effectPerformed"), "system-change effectPerformed")
    if raw.get("readOnly") is not True:
        raise ValueError("system-change readOnly must be true")
    return _sha256_hex(raw.get("changeDigest"), "system-change changeDigest")


class SystemHistoryPersistenceBridge:
    """Persist governed PhiShell history through the existing canonical memory service.

    This bridge never writes MemoryStore directly. MemoryOperatorRuntime remains the
    authority, policy, canonical-store, outbox, and Mandala publication boundary.
    """

    def __init__(self, runtime: MemoryOperatorRuntime) -> None:
        self.runtime = runtime

    def persist_transition(
        self,
        *,
        previous_state: Mapping[str, Any],
        current_state: Mapping[str, Any],
        change_receipt: Mapping[str, Any],
        task_id: str = "phishell-system-history",
    ) -> PersistedSystemHistory:
        self.runtime.require_enabled()
        if not self.runtime.authority.allows("memory.write"):
            raise PermissionError("persistent system history requires explicit memory.write authority")

        previous = _require_mapping(previous_state, "previous_state")
        current = _require_mapping(current_state, "current_state")
        change = _require_mapping(change_receipt, "change_receipt")

        previous_digest = _validate_state_receipt(previous)
        current_digest = _validate_state_receipt(current)
        change_digest = _validate_change_receipt(change)

        if _sha256_hex(change.get("fromReceiptDigest"), "fromReceiptDigest") != previous_digest:
            raise ValueError("change receipt does not reference previous system-state receipt")
        if _sha256_hex(change.get("toReceiptDigest"), "toReceiptDigest") != current_digest:
            raise ValueError("change receipt does not reference current system-state receipt")

        previous_record, previous_result = self._persist_state(
            previous,
            receipt_digest=previous_digest,
            task_id=task_id,
        )
        current_record, current_result = self._persist_state(
            current,
            receipt_digest=current_digest,
            task_id=task_id,
        )
        change_record, change_result = self._persist_change(
            change,
            change_digest=change_digest,
            previous_digest=previous_digest,
            current_digest=current_digest,
            task_id=task_id,
        )

        return PersistedSystemHistory(
            state_record_ids=(previous_record.record_id, current_record.record_id),
            change_record_id=change_record.record_id,
            state_receipt_ids=(previous_result.receipt_id, current_result.receipt_id),
            change_receipt_id=change_result.receipt_id,
        )

    def _record_policy_fields(self) -> tuple[str, str, str]:
        if not self.runtime.config.scopes or not self.runtime.config.classifications:
            raise RuntimeError("memory runtime has no configured history policy scope")
        return (
            self.runtime.config.scopes[0],
            self.runtime.config.classifications[0],
            self.runtime.config.retention_policy_id,
        )

    def _persist_state(
        self,
        state: Mapping[str, Any],
        *,
        receipt_digest: str,
        task_id: str,
    ) -> tuple[MemoryRecord, MemoryResult]:
        scope_id, classification, retention_policy_id = self._record_policy_fields()
        record_id = _state_record_id(receipt_digest)
        created_at = _require_string(state.get("composedAt"), "system-state composedAt")
        text = _canonical_text(state)
        record = MemoryRecord.build(
            record_id=record_id,
            revision=1,
            source_id="phishell.system-state",
            source_kind="subsystem",
            provenance_refs=(f"sha256:{receipt_digest}",),
            created_at=created_at,
            scope_id=scope_id,
            classification=classification,
            retention_policy_id=retention_policy_id,
            expires_at=None,
            epistemic_kind="source",
            text=text,
        )
        result = self.runtime.put(
            record,
            operation_id=f"phishell-history:state:{receipt_digest}",
            task_id=task_id,
        )
        if result.status != "ok":
            raise RuntimeError(result.error_code or "failed to persist system-state receipt")
        return record, result

    def _persist_change(
        self,
        change: Mapping[str, Any],
        *,
        change_digest: str,
        previous_digest: str,
        current_digest: str,
        task_id: str,
    ) -> tuple[MemoryRecord, MemoryResult]:
        scope_id, classification, retention_policy_id = self._record_policy_fields()
        record_id = _change_record_id(change_digest)
        created_at = _require_string(change.get("recordedAt"), "system-change recordedAt")
        text = _canonical_text(change)
        content_sha256 = _content_sha256(text)
        source_refs = (
            _state_record_id(previous_digest),
            _state_record_id(current_digest),
        )

        lineage = TransformationLineageBuilder().build(
            transform_id="phishell.system-change",
            transform_version=BRIDGE_VERSION,
            source_refs=source_refs,
            source_sha256s=(previous_digest, current_digest),
            output_ref=record_id,
            output_sha256=content_sha256,
            parameters={
                "state_schema": SYSTEM_STATE_SCHEMA,
                "change_schema": SYSTEM_CHANGE_SCHEMA,
                "cause_assigned": False,
                "severity_assigned": False,
            },
            requested_exactness=ExactnessClass.REVERSIBLE,
            information_loss_possible=False,
            semantic_inference=False,
            limitations=(
                "change receipt describes bounded observed differences only",
                "change receipt does not assign cause",
                "change receipt does not assign severity",
            ),
        )

        record = MemoryRecord.build(
            record_id=record_id,
            revision=1,
            source_id="phishell.system-change",
            source_kind="subsystem",
            provenance_refs=(
                f"sha256:{change_digest}",
                f"sha256:{previous_digest}",
                f"sha256:{current_digest}",
            ),
            created_at=created_at,
            scope_id=scope_id,
            classification=classification,
            retention_policy_id=retention_policy_id,
            expires_at=None,
            epistemic_kind="derived",
            derived_from=source_refs,
            exactness_class=lineage.exactness_class.value,
            transformation_lineage_sha256s=(lineage.receipt_sha256,),
            text=text,
        )
        result = self.runtime.put(
            record,
            operation_id=f"phishell-history:change:{change_digest}",
            task_id=task_id,
            transformation_lineage=(lineage,),
        )
        if result.status != "ok":
            raise RuntimeError(result.error_code or "failed to persist system-change receipt")
        return record, result
