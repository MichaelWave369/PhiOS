from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from phios.memory.validation import strict_canonical_json

from .models import MemoryRecord
from .operator import MemoryOperatorRuntime
from .system_history import (
    _canonical_memory_record_integrity,
    _sha256_hex,
    _state_record_id,
    _validate_state_receipt,
)

SYSTEM_HISTORY_COMPARISON_SCHEMA = "phios.system-history-comparison.v0.13"
SYSTEM_HISTORY_COMPARISON_SOURCE = "governed-memory-system-history-comparator"

COMPONENT_IDS = ("host", "services", "processes", "packages", "devices")
COMPONENT_CONTRACTS = {
    "host": ("phios.host-observation.v1", "linux-readonly-node-probe"),
    "services": ("phios.service-observation.v1", "systemd-dbus-list-units"),
    "processes": ("phios.process-observation.v1", "procfs-current-user"),
    "packages": ("phios.package-observation.v1", "dpkg-status-file"),
    "devices": ("phios.device-observation.v1", "linux-sysfs-bounded"),
}
SUMMARY_METRICS = (
    "cpuLogicalCores",
    "memoryTotalBytes",
    "rootStorageTotalBytes",
    "observedServiceCount",
    "activeServiceCount",
    "currentUserProcessCount",
    "installedPackageCount",
    "blockDeviceCount",
    "networkDeviceCount",
    "pciDeviceCount",
    "usbDeviceCount",
    "drmDeviceCount",
    "powerDeviceCount",
)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: object, field: str) -> str:
    raw = _string(value, field)
    try:
        datetime.fromisoformat(raw).astimezone(UTC)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    return raw


def _number(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _comparison_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("comparisonDigest", None)
    encoded = strict_canonical_json(body).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _comparable_state_payload(
    record: MemoryRecord,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    receipt_digest = _validate_state_receipt(payload, verify_digest=False)
    if (
        record.source_id != "phishell.system-state"
        or record.epistemic_kind != "source"
        or record.record_id != _state_record_id(receipt_digest)
        or f"sha256:{receipt_digest}" not in record.provenance_refs
        or not _canonical_memory_record_integrity(record)
    ):
        raise ValueError("canonical state record integrity check failed")

    composed_at = _timestamp(payload.get("composedAt"), "system-state composedAt")
    coherence = _string(payload.get("coherence"), "system-state coherence")
    if coherence not in {"coherent", "degraded"}:
        raise ValueError("system-state coherence must be coherent or degraded")

    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or len(raw_components) != len(COMPONENT_IDS):
        raise ValueError("system-state components are not comparable")

    components: list[dict[str, object]] = []
    for index, expected_id in enumerate(COMPONENT_IDS):
        component = _mapping(raw_components[index], f"component {expected_id}")
        component_id = _string(component.get("id"), f"component {expected_id} id")
        if component_id != expected_id:
            raise ValueError("system-state component order is not canonical")
        expected_schema, expected_source = COMPONENT_CONTRACTS[expected_id]
        if component.get("schemaVersion") != expected_schema:
            raise ValueError(f"component {expected_id} schema is not canonical")
        if component.get("source") != expected_source:
            raise ValueError(f"component {expected_id} source is not canonical")
        _timestamp(component.get("capturedAt"), f"component {expected_id} capturedAt")
        if component.get("readOnly") is not True:
            raise ValueError(f"component {expected_id} readOnly must be true")
        if component.get("executionAuthority") is not False:
            raise ValueError(f"component {expected_id} executionAuthority must be false")
        if component.get("effectPerformed") is not False:
            raise ValueError(f"component {expected_id} effectPerformed must be false")
        availability = _string(
            component.get("availability"),
            f"component {expected_id} availability",
        )
        if availability not in {"available", "unavailable"}:
            raise ValueError(f"component {expected_id} availability is invalid")
        digest = _string(component.get("digest"), f"component {expected_id} digest")
        _sha256_hex(digest, f"component {expected_id} digest")
        components.append(
            {
                "id": component_id,
                "availability": availability,
                "digest": digest,
            }
        )

    summary = _mapping(payload.get("summary"), "system-state summary")
    if set(summary) != set(SUMMARY_METRICS):
        raise ValueError("system-state summary fields are not canonical")
    summary_values: dict[str, int] = {}
    for metric in SUMMARY_METRICS:
        summary_values[metric] = _number(summary.get(metric), f"summary {metric}")

    return {
        "receiptDigest": f"sha256:{receipt_digest}",
        "composedAt": composed_at,
        "coherence": coherence,
        "components": components,
        "summary": summary_values,
    }


@dataclass(frozen=True, kw_only=True)
class SystemHistoryComparison:
    body: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.body)


class SystemHistoryComparisonService:
    """Derive a non-persistent comparison from two governed canonical state reads."""

    def __init__(self, runtime: MemoryOperatorRuntime) -> None:
        self.runtime = runtime

    def compare(
        self,
        *,
        from_record_id: str,
        to_record_id: str,
        task_id: str = "phishell-system-history-compare",
    ) -> SystemHistoryComparison:
        self.runtime.require_enabled()
        if not self.runtime.authority.allows("history.read"):
            raise PermissionError(
                "canonical history comparison requires explicit history.read authority"
            )
        if not self.runtime.authority.allows("memory.read"):
            raise PermissionError(
                "canonical history comparison requires explicit memory.read authority"
            )
        if not self.runtime.authority.allows("history.compare"):
            raise PermissionError(
                "canonical history comparison requires explicit history.compare authority"
            )

        from_record_id = _string(from_record_id, "from_record_id")
        to_record_id = _string(to_record_id, "to_record_id")
        if from_record_id == to_record_id:
            raise ValueError("canonical history comparison requires two distinct state records")
        for value in (from_record_id, to_record_id):
            if not value.startswith("phishell.system-state."):
                raise ValueError(
                    "canonical history comparison accepts only PhiShell system-state records"
                )
            digest = value.removeprefix("phishell.system-state.")
            _sha256_hex(digest, "system-state record id digest")

        from_result = self.runtime.get(
            from_record_id,
            task_id=f"{task_id}:from",
        )
        to_result = self.runtime.get(
            to_record_id,
            task_id=f"{task_id}:to",
        )
        if from_result.status != "ok" or from_result.record is None:
            raise LookupError("from canonical system-state record is not read-admissible")
        if to_result.status != "ok" or to_result.record is None:
            raise LookupError("to canonical system-state record is not read-admissible")
        if not from_result.read_admissibility_receipts:
            raise LookupError("from canonical system-state record lacks read admissibility")
        if not to_result.read_admissibility_receipts:
            raise LookupError("to canonical system-state record lacks read admissibility")

        from_read = from_result.read_admissibility_receipts[0]
        to_read = to_result.read_admissibility_receipts[0]
        for label, receipt in (("from", from_read), ("to", to_read)):
            if (
                receipt.readable_as_context is not True
                or receipt.currentness != "current"
                or receipt.operational_authority is not False
                or receipt.action_authority is not False
                or receipt.execution_authority is not False
            ):
                raise LookupError(f"{label} canonical system-state read is not admissible")

        try:
            from_payload_raw = json.loads(from_result.record.text)
            to_payload_raw = json.loads(to_result.record.text)
        except json.JSONDecodeError as exc:
            raise ValueError("canonical system-state payload is not valid JSON") from exc
        if not isinstance(from_payload_raw, dict) or not isinstance(to_payload_raw, dict):
            raise ValueError("canonical system-state payload must be an object")

        from_state = _comparable_state_payload(from_result.record, from_payload_raw)
        to_state = _comparable_state_payload(to_result.record, to_payload_raw)

        component_changes: list[dict[str, object]] = []
        from_components = from_state["components"]
        to_components = to_state["components"]
        assert isinstance(from_components, list)
        assert isinstance(to_components, list)
        for index, component_id in enumerate(COMPONENT_IDS):
            from_component = _mapping(from_components[index], f"from {component_id}")
            to_component = _mapping(to_components[index], f"to {component_id}")
            from_availability = _string(
                from_component.get("availability"),
                "from availability",
            )
            to_availability = _string(
                to_component.get("availability"),
                "to availability",
            )
            from_digest = _string(from_component.get("digest"), "from digest")
            to_digest = _string(to_component.get("digest"), "to digest")
            component_changes.append(
                {
                    "id": component_id,
                    "fromAvailability": from_availability,
                    "toAvailability": to_availability,
                    "availabilityChanged": from_availability != to_availability,
                    "fromDigest": from_digest,
                    "toDigest": to_digest,
                    "digestChanged": from_digest != to_digest,
                }
            )

        from_summary = _mapping(from_state["summary"], "from summary")
        to_summary = _mapping(to_state["summary"], "to summary")
        summary_changes: list[dict[str, object]] = []
        for metric in SUMMARY_METRICS:
            from_value = _number(
                from_summary.get(metric),
                f"from summary {metric}",
            )
            to_value = _number(
                to_summary.get(metric),
                f"to summary {metric}",
            )
            if from_value != to_value:
                summary_changes.append(
                    {
                        "metric": metric,
                        "from": from_value,
                        "to": to_value,
                        "delta": to_value - from_value,
                    }
                )

        from_composed_at = _timestamp(from_state["composedAt"], "from composedAt")
        to_composed_at = _timestamp(to_state["composedAt"], "to composedAt")
        time_delta_ms = int(
            (
                datetime.fromisoformat(to_composed_at).astimezone(UTC)
                - datetime.fromisoformat(from_composed_at).astimezone(UTC)
            ).total_seconds()
            * 1000
        )
        chronological_order = (
            "forward"
            if time_delta_ms > 0
            else "reverse"
            if time_delta_ms < 0
            else "same-time"
        )

        body: dict[str, object] = {
            "schemaVersion": SYSTEM_HISTORY_COMPARISON_SCHEMA,
            "source": SYSTEM_HISTORY_COMPARISON_SOURCE,
            "generatedAt": datetime.now(UTC).isoformat(),
            "comparisonScope": "canonical-state-pair",
            "persistent": False,
            "fromRecordId": from_result.record.record_id,
            "toRecordId": to_result.record.record_id,
            "fromRecordSha256": from_result.record.record_sha256,
            "toRecordSha256": to_result.record.record_sha256,
            "fromReadAdmissibilityReceiptSha256": from_read.receipt_sha256,
            "toReadAdmissibilityReceiptSha256": to_read.receipt_sha256,
            "fromReceiptDigest": from_state["receiptDigest"],
            "toReceiptDigest": to_state["receiptDigest"],
            "fromComposedAt": from_composed_at,
            "toComposedAt": to_composed_at,
            "timeDeltaMs": time_delta_ms,
            "chronologicalOrder": chronological_order,
            "coherence": {
                "from": from_state["coherence"],
                "to": to_state["coherence"],
                "changed": from_state["coherence"] != to_state["coherence"],
            },
            "changedComponentCount": sum(
                1
                for row in component_changes
                if row["availabilityChanged"] or row["digestChanged"]
            ),
            "componentChanges": component_changes,
            "changedSummaryMetricCount": len(summary_changes),
            "summaryChanges": summary_changes,
            "consecutiveClaimed": False,
            "causeAssigned": False,
            "severityAssigned": False,
            "readOnly": True,
            "operationalAuthority": False,
            "actionAuthority": False,
            "executionAuthority": False,
            "effectPerformed": False,
            "comparisonDigest": "",
        }
        body["comparisonDigest"] = f"sha256:{_comparison_digest(body)}"
        return SystemHistoryComparison(body=body)
