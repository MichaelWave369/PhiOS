from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from phios.evidence_ref import EvidenceRef
from phios.mandala import ExactnessClass, TransformationLineageBuilder
from phios.memory.models import MemoryRecord, MemoryResult
from phios.memory.operator import MemoryOperatorRuntime
from phios.memory.validation import sha256_json, strict_canonical_json

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


def _receipt_body_sha256(value: Mapping[str, Any], digest_field: str) -> str:
    body = dict(value)
    body.pop(digest_field, None)
    encoded = json.dumps(
        body,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _state_record_id(receipt_digest: str) -> str:
    return f"phishell.system-state.{receipt_digest}"


def _change_record_id(change_digest: str) -> str:
    return f"phishell.system-change.{change_digest}"


def _validate_state_receipt(
    raw: Mapping[str, Any],
    *,
    verify_digest: bool = True,
) -> str:
    if raw.get("schemaVersion") != SYSTEM_STATE_SCHEMA:
        raise ValueError("unsupported system-state schema")
    if raw.get("source") != SYSTEM_STATE_SOURCE:
        raise ValueError("unexpected system-state source")
    _require_false(raw.get("executionAuthority"), "system-state executionAuthority")
    _require_false(raw.get("effectPerformed"), "system-state effectPerformed")
    if raw.get("readOnly") is not True:
        raise ValueError("system-state readOnly must be true")
    digest = _sha256_hex(raw.get("receiptDigest"), "system-state receiptDigest")
    if verify_digest and _receipt_body_sha256(raw, "receiptDigest") != digest:
        raise ValueError("system-state receiptDigest does not match receipt body")
    return digest


def _validate_change_receipt(
    raw: Mapping[str, Any],
    *,
    verify_digest: bool = True,
) -> str:
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
    digest = _sha256_hex(raw.get("changeDigest"), "system-change changeDigest")
    if verify_digest and _receipt_body_sha256(raw, "changeDigest") != digest:
        raise ValueError("system-change changeDigest does not match receipt body")
    return digest


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
        if not self.runtime.authority.allows("history.persist"):
            raise PermissionError("persistent system history requires explicit history.persist authority")
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


SYSTEM_HISTORY_PROJECTION_SCHEMA = "phios.system-history-projection.v0.13"
SYSTEM_HISTORY_SOURCE_IDS = ("phishell.system-state", "phishell.system-change")
SYSTEM_HISTORY_PROJECTION_LIMIT = 16


@dataclass(frozen=True, kw_only=True)
class SystemHistoryProjection:
    generated_at: str
    status: str
    limit: int
    records: tuple[dict[str, object], ...]
    omitted_record_count: int
    read_admissibility_receipt_sha256s: tuple[str, ...]
    schema_version: str = SYSTEM_HISTORY_PROJECTION_SCHEMA
    source: str = "governed-memory-system-history"
    history_scope: str = "canonical-memory"
    persistent: bool = True
    read_only: bool = True
    cause_assigned: bool = False
    severity_assigned: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "source": self.source,
            "generatedAt": self.generated_at,
            "status": self.status,
            "historyScope": self.history_scope,
            "persistent": self.persistent,
            "limit": self.limit,
            "count": len(self.records),
            "omittedRecordCount": self.omitted_record_count,
            "records": [dict(record) for record in self.records],
            "readAdmissibilityReceiptSha256s": list(
                self.read_admissibility_receipt_sha256s
            ),
            "readOnly": self.read_only,
            "causeAssigned": self.cause_assigned,
            "severityAssigned": self.severity_assigned,
            "operationalAuthority": self.operational_authority,
            "actionAuthority": self.action_authority,
            "executionAuthority": self.execution_authority,
            "effectPerformed": self.effect_performed,
        }


def _canonical_memory_record_integrity(record: MemoryRecord) -> bool:
    if hashlib.sha256(record.text.encode("utf-8")).hexdigest() != record.content_sha256:
        return False
    body = record.to_dict()
    record_sha256 = str(body.pop("record_sha256"))
    return sha256_json(body) == record_sha256


def _evidence_ref_for_history_record(
    record: MemoryRecord,
    *,
    source_version: str,
) -> EvidenceRef:
    """Derive one stable zero-authority EvidenceRef from a canonical memory record."""

    return EvidenceRef.build(
        source_id=record.record_id,
        source_kind=record.source_kind,
        source_version=source_version,
        content_sha256=record.content_sha256,
        created_at=record.created_at,
        observed_at=record.created_at,
        transformation_lineage_sha256s=record.transformation_lineage_sha256s,
        exactness_class=record.exactness_class,
    )


class SystemHistoryProjectionService:
    """Project canonical PhiShell history through governed memory reads only."""

    def __init__(self, runtime: MemoryOperatorRuntime) -> None:
        self.runtime = runtime

    def project(
        self,
        *,
        limit: int = SYSTEM_HISTORY_PROJECTION_LIMIT,
        task_id: str = "phishell-system-history-read",
    ) -> SystemHistoryProjection:
        self.runtime.require_enabled()
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 16):
            raise ValueError("persistent history limit must be an integer between 1 and 16")
        if not self.runtime.authority.allows("history.read"):
            raise PermissionError(
                "persistent system history requires explicit history.read authority"
            )
        if not self.runtime.authority.allows("memory.read"):
            raise PermissionError(
                "persistent system history requires explicit memory.read authority"
            )

        decision = self.runtime.policy.resolve(
            principal_id=self.runtime.config.principal_id,
            task_id=task_id,
            operation="memory.read",
            authority=self.runtime.authority,
        )
        if decision is None:
            raise PermissionError("persistent system history is outside memory.read policy")

        record_ids = self.runtime.store.list_current_record_ids(
            source_ids=SYSTEM_HISTORY_SOURCE_IDS,
            allowed_scopes=decision.allowed_scopes,
            allowed_classifications=decision.allowed_classifications,
            limit=limit,
        )

        records: list[dict[str, object]] = []
        read_receipt_hashes: list[str] = []
        omitted = 0

        for index, record_id in enumerate(record_ids):
            result = self.runtime.get(record_id, task_id=f"{task_id}:{index + 1}")
            if result.status != "ok" or result.record is None:
                omitted += 1
                continue

            record = result.record
            if not _canonical_memory_record_integrity(record):
                omitted += 1
                continue
            try:
                payload = json.loads(record.text)
            except json.JSONDecodeError:
                omitted += 1
                continue
            if not isinstance(payload, dict):
                omitted += 1
                continue

            kind: str
            source_version: str
            if record.source_id == "phishell.system-state":
                receipt_digest = _validate_state_receipt(payload, verify_digest=False)
                if (
                    record.epistemic_kind != "source"
                    or record.record_id != _state_record_id(receipt_digest)
                    or f"sha256:{receipt_digest}" not in record.provenance_refs
                ):
                    omitted += 1
                    continue
                kind = "state"
                source_version = SYSTEM_STATE_SCHEMA
            elif record.source_id == "phishell.system-change":
                change_digest = _validate_change_receipt(payload, verify_digest=False)
                previous_digest = _sha256_hex(
                    payload.get("fromReceiptDigest"),
                    "fromReceiptDigest",
                )
                current_digest = _sha256_hex(
                    payload.get("toReceiptDigest"),
                    "toReceiptDigest",
                )
                expected_sources = (
                    _state_record_id(previous_digest),
                    _state_record_id(current_digest),
                )
                if (
                    record.epistemic_kind != "derived"
                    or record.exactness_class != "REVERSIBLE"
                    or record.record_id != _change_record_id(change_digest)
                    or record.derived_from != expected_sources
                    or f"sha256:{change_digest}" not in record.provenance_refs
                    or f"sha256:{previous_digest}" not in record.provenance_refs
                    or f"sha256:{current_digest}" not in record.provenance_refs
                ):
                    omitted += 1
                    continue
                kind = "change"
                source_version = SYSTEM_CHANGE_SCHEMA
            else:
                omitted += 1
                continue

            if not result.read_admissibility_receipts:
                omitted += 1
                continue
            read_receipt = result.read_admissibility_receipts[0]
            if (
                read_receipt.readable_as_context is not True
                or read_receipt.currentness != "current"
                or read_receipt.operational_authority is not False
                or read_receipt.action_authority is not False
                or read_receipt.execution_authority is not False
            ):
                omitted += 1
                continue

            evidence_ref = _evidence_ref_for_history_record(
                record,
                source_version=source_version,
            )
            read_receipt_hashes.append(read_receipt.receipt_sha256)
            records.append(
                {
                    "kind": kind,
                    "recordId": record.record_id,
                    "revision": record.revision,
                    "recordSha256": record.record_sha256,
                    "contentSha256": record.content_sha256,
                    "createdAt": record.created_at,
                    "scopeId": record.scope_id,
                    "classification": record.classification,
                    "retentionPolicyId": record.retention_policy_id,
                    "epistemicKind": record.epistemic_kind,
                    "exactnessClass": record.exactness_class,
                    "derivedFrom": list(record.derived_from),
                    "transformationLineageSha256s": list(
                        record.transformation_lineage_sha256s
                    ),
                    "evidenceRef": evidence_ref.to_dict(),
                    "readAdmissibilityReceiptSha256": read_receipt.receipt_sha256,
                    "payload": payload,
                }
            )

        return SystemHistoryProjection(
            generated_at=datetime.now(UTC).isoformat(),
            status="degraded" if omitted else "ok",
            limit=limit,
            records=tuple(records),
            omitted_record_count=omitted,
            read_admissibility_receipt_sha256s=tuple(read_receipt_hashes),
        )
