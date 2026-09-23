from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, Sequence

from phios.mandala import AuthorityContext

from .models import MemoryRecord
from .publisher import MemoryReceiptPublisher
from .service import GovernedMemoryService
from .validation import require_nonempty, require_utc_timestamp, strict_canonical_json

SYSTEM_STATE_SCHEMA_VERSION = "phios.system-state.v1"
SYSTEM_CHANGE_SCHEMA_VERSION = "phios.system-change.v1"
SYSTEM_HISTORY_RETENTION_DEFAULT = "phishell-system-history-v0.11"

_COMPONENTS = (
    ("host", "phios.host-observation.v1", "linux-readonly-node-probe"),
    ("services", "phios.service-observation.v1", "systemd-dbus-list-units"),
    ("processes", "phios.process-observation.v1", "procfs-current-user"),
    ("packages", "phios.package-observation.v1", "dpkg-status-file"),
    ("devices", "phios.device-observation.v1", "linux-sysfs-bounded"),
)
_SUMMARY_KEYS = (
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
_STATE_KEYS = (
    "schemaVersion",
    "source",
    "composedAt",
    "captureWindowStart",
    "captureWindowEnd",
    "captureSkewMs",
    "maxCoherentSkewMs",
    "coherence",
    "componentCount",
    "availableComponentCount",
    "readOnly",
    "executionAuthority",
    "effectPerformed",
    "components",
    "summary",
    "composeDurationMs",
    "receiptDigest",
)
_COMPONENT_KEYS = (
    "id",
    "schemaVersion",
    "source",
    "capturedAt",
    "availability",
    "digest",
    "readOnly",
    "executionAuthority",
    "effectPerformed",
)
_CHANGE_KEYS = (
    "schemaVersion",
    "source",
    "recordedAt",
    "sequence",
    "historyScope",
    "persistent",
    "historyLimit",
    "fromReceiptDigest",
    "toReceiptDigest",
    "fromComposedAt",
    "toComposedAt",
    "elapsedMs",
    "coherence",
    "changedComponentCount",
    "componentChanges",
    "changedSummaryMetricCount",
    "summaryChanges",
    "causeAssigned",
    "severityAssigned",
    "readOnly",
    "executionAuthority",
    "effectPerformed",
    "changeDigest",
)
_COMPONENT_CHANGE_KEYS = (
    "id",
    "fromAvailability",
    "toAvailability",
    "availabilityChanged",
    "fromDigest",
    "toDigest",
    "digestChanged",
)
_SUMMARY_CHANGE_KEYS = ("metric", "from", "to", "delta")


@dataclass(frozen=True, kw_only=True)
class SystemArchiveResult:
    status: Literal["saved", "exists", "blocked", "invalid", "unavailable"]
    record_id: str | None = None
    record_sha256: str | None = None
    memory_receipt_id: str | None = None
    error_code: str | None = None


def _exact_keys(payload: Mapping[str, object], expected: Sequence[str]) -> bool:
    return set(payload) == set(expected) and len(payload) == len(expected)


def _nonnegative_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value >= 0
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _nonnegative_integer(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _sha256_prefixed(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value[7:]
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return digest == digest.lower()


def _js_json_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _utc(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a UTC timestamp string")
    return require_utc_timestamp(value, field)


def _ordered_component(component: Mapping[str, object]) -> dict[str, object]:
    return {key: component[key] for key in _COMPONENT_KEYS}


def _ordered_summary(summary: Mapping[str, object]) -> dict[str, object]:
    return {key: summary[key] for key in _SUMMARY_KEYS}


def _state_digest_body(payload: Mapping[str, object]) -> dict[str, object]:
    components = payload["components"]
    summary = payload["summary"]
    if not isinstance(components, list) or not isinstance(summary, Mapping):
        raise ValueError("system-state body is malformed")
    return {
        "schemaVersion": payload["schemaVersion"],
        "source": payload["source"],
        "composedAt": payload["composedAt"],
        "captureWindowStart": payload["captureWindowStart"],
        "captureWindowEnd": payload["captureWindowEnd"],
        "captureSkewMs": payload["captureSkewMs"],
        "maxCoherentSkewMs": payload["maxCoherentSkewMs"],
        "coherence": payload["coherence"],
        "componentCount": payload["componentCount"],
        "availableComponentCount": payload["availableComponentCount"],
        "readOnly": payload["readOnly"],
        "executionAuthority": payload["executionAuthority"],
        "effectPerformed": payload["effectPerformed"],
        "components": [
            _ordered_component(item)
            for item in components
            if isinstance(item, Mapping)
        ],
        "summary": _ordered_summary(summary),
        "composeDurationMs": payload["composeDurationMs"],
    }


def validate_system_state_receipt(payload: Mapping[str, object]) -> None:
    if not _exact_keys(payload, _STATE_KEYS):
        raise ValueError("system-state fields do not match the v0.9 contract")
    if payload["schemaVersion"] != SYSTEM_STATE_SCHEMA_VERSION:
        raise ValueError("unsupported system-state schema")
    if payload["source"] != "phios-system-state-composer":
        raise ValueError("unexpected system-state source")
    composed_at = _utc(payload["composedAt"], "composedAt")
    window_start = _utc(payload["captureWindowStart"], "captureWindowStart")
    window_end = _utc(payload["captureWindowEnd"], "captureWindowEnd")
    if not _nonnegative_number(payload["captureSkewMs"]):
        raise ValueError("captureSkewMs must be nonnegative")
    if payload["maxCoherentSkewMs"] != 5000:
        raise ValueError("maxCoherentSkewMs must remain 5000")
    if payload["coherence"] not in {"coherent", "degraded"}:
        raise ValueError("invalid system-state coherence")
    if payload["componentCount"] != 5:
        raise ValueError("system-state componentCount must be 5")
    if (
        not _nonnegative_integer(payload["availableComponentCount"])
        or int(payload["availableComponentCount"]) > 5
    ):
        raise ValueError("availableComponentCount must be within 0..5")
    if (
        payload["readOnly"] is not True
        or payload["executionAuthority"] is not False
        or payload["effectPerformed"] is not False
    ):
        raise ValueError("system-state receipt cannot carry effect authority")
    if not _nonnegative_number(payload["composeDurationMs"]):
        raise ValueError("composeDurationMs must be nonnegative")
    if not _sha256_prefixed(payload["receiptDigest"]):
        raise ValueError("invalid system-state receipt digest")

    components = payload["components"]
    if not isinstance(components, list) or len(components) != 5:
        raise ValueError("system-state must contain exactly five components")
    capture_times: list[datetime] = []
    available = 0
    for index, expected in enumerate(_COMPONENTS):
        component = components[index]
        if not isinstance(component, Mapping) or not _exact_keys(component, _COMPONENT_KEYS):
            raise ValueError("system-state component fields are invalid")
        expected_id, expected_schema, expected_source = expected
        if component["id"] != expected_id:
            raise ValueError("system-state component order changed")
        if component["schemaVersion"] != expected_schema:
            raise ValueError(f"unexpected {expected_id} schema")
        if component["source"] != expected_source:
            raise ValueError(f"unexpected {expected_id} source")
        captured = _utc(component["capturedAt"], f"{expected_id}.capturedAt")
        capture_times.append(datetime.fromisoformat(captured))
        if component["availability"] not in {"available", "unavailable"}:
            raise ValueError("invalid component availability")
        if expected_id == "host" and component["availability"] != "available":
            raise ValueError("host component must be available")
        if component["availability"] == "available":
            available += 1
        if not _sha256_prefixed(component["digest"]):
            raise ValueError("invalid component digest")
        if (
            component["readOnly"] is not True
            or component["executionAuthority"] is not False
            or component["effectPerformed"] is not False
        ):
            raise ValueError("component cannot carry effect authority")

    summary = payload["summary"]
    if not isinstance(summary, Mapping) or not _exact_keys(summary, _SUMMARY_KEYS):
        raise ValueError("system-state summary fields are invalid")
    for key in _SUMMARY_KEYS:
        if not _nonnegative_number(summary[key]):
            raise ValueError(f"summary metric {key} must be nonnegative")
    if float(summary["activeServiceCount"]) > float(summary["observedServiceCount"]):
        raise ValueError("activeServiceCount cannot exceed observedServiceCount")

    expected_start = min(capture_times).isoformat()
    expected_end = max(capture_times).isoformat()
    expected_skew = int(
        (max(capture_times) - min(capture_times)).total_seconds() * 1000
    )
    if window_start != expected_start or window_end != expected_end:
        raise ValueError("system-state capture window does not match components")
    if payload["captureSkewMs"] != expected_skew:
        raise ValueError("system-state capture skew does not match components")
    if payload["availableComponentCount"] != available:
        raise ValueError("availableComponentCount does not match components")
    expected_coherence = (
        "coherent" if available == 5 and expected_skew <= 5000 else "degraded"
    )
    if payload["coherence"] != expected_coherence:
        raise ValueError("system-state coherence derivation is invalid")

    expected_digest = _js_json_sha256(_state_digest_body(payload))
    if payload["receiptDigest"] != expected_digest:
        raise ValueError("system-state receipt digest mismatch")


def _change_digest_body(payload: Mapping[str, object]) -> dict[str, object]:
    coherence = payload["coherence"]
    component_changes = payload["componentChanges"]
    summary_changes = payload["summaryChanges"]
    if (
        not isinstance(coherence, Mapping)
        or not isinstance(component_changes, list)
        or not isinstance(summary_changes, list)
    ):
        raise ValueError("system-change body is malformed")
    return {
        "schemaVersion": payload["schemaVersion"],
        "source": payload["source"],
        "recordedAt": payload["recordedAt"],
        "sequence": payload["sequence"],
        "historyScope": payload["historyScope"],
        "persistent": payload["persistent"],
        "historyLimit": payload["historyLimit"],
        "fromReceiptDigest": payload["fromReceiptDigest"],
        "toReceiptDigest": payload["toReceiptDigest"],
        "fromComposedAt": payload["fromComposedAt"],
        "toComposedAt": payload["toComposedAt"],
        "elapsedMs": payload["elapsedMs"],
        "coherence": {
            "from": coherence["from"],
            "to": coherence["to"],
            "changed": coherence["changed"],
        },
        "changedComponentCount": payload["changedComponentCount"],
        "componentChanges": [
            {key: item[key] for key in _COMPONENT_CHANGE_KEYS}
            for item in component_changes
            if isinstance(item, Mapping)
        ],
        "changedSummaryMetricCount": payload["changedSummaryMetricCount"],
        "summaryChanges": [
            {key: item[key] for key in _SUMMARY_CHANGE_KEYS}
            for item in summary_changes
            if isinstance(item, Mapping)
        ],
        "causeAssigned": payload["causeAssigned"],
        "severityAssigned": payload["severityAssigned"],
        "readOnly": payload["readOnly"],
        "executionAuthority": payload["executionAuthority"],
        "effectPerformed": payload["effectPerformed"],
    }


def validate_system_change_receipt(payload: Mapping[str, object]) -> None:
    if not _exact_keys(payload, _CHANGE_KEYS):
        raise ValueError("system-change fields do not match the v0.10 contract")
    if payload["schemaVersion"] != SYSTEM_CHANGE_SCHEMA_VERSION:
        raise ValueError("unsupported system-change schema")
    if payload["source"] != "phios-system-change-deriver":
        raise ValueError("unexpected system-change source")
    _utc(payload["recordedAt"], "recordedAt")
    from_time = datetime.fromisoformat(_utc(payload["fromComposedAt"], "fromComposedAt"))
    to_time = datetime.fromisoformat(_utc(payload["toComposedAt"], "toComposedAt"))
    if not isinstance(payload["sequence"], int) or isinstance(payload["sequence"], bool) or payload["sequence"] < 1:
        raise ValueError("system-change sequence must be >= 1")
    if (
        payload["historyScope"] != "session-memory"
        or payload["persistent"] is not False
        or payload["historyLimit"] != 16
    ):
        raise ValueError("system-change history boundary is invalid")
    for key in ("fromReceiptDigest", "toReceiptDigest", "changeDigest"):
        if not _sha256_prefixed(payload[key]):
            raise ValueError(f"invalid {key}")
    expected_elapsed = max(0, int((to_time - from_time).total_seconds() * 1000))
    if payload["elapsedMs"] != expected_elapsed:
        raise ValueError("system-change elapsedMs derivation is invalid")

    coherence = payload["coherence"]
    if not isinstance(coherence, Mapping) or not _exact_keys(
        coherence, ("from", "to", "changed")
    ):
        raise ValueError("system-change coherence fields are invalid")
    if coherence["from"] not in {"coherent", "degraded"} or coherence["to"] not in {
        "coherent",
        "degraded",
    }:
        raise ValueError("invalid system-change coherence value")
    if coherence["changed"] is not (coherence["from"] != coherence["to"]):
        raise ValueError("system-change coherence transition is invalid")

    component_changes = payload["componentChanges"]
    if not isinstance(component_changes, list) or len(component_changes) != 5:
        raise ValueError("system-change must contain five component changes")
    changed_components = 0
    for index, expected in enumerate(_COMPONENTS):
        item = component_changes[index]
        if not isinstance(item, Mapping) or not _exact_keys(
            item, _COMPONENT_CHANGE_KEYS
        ):
            raise ValueError("invalid component-change fields")
        expected_id = expected[0]
        if item["id"] != expected_id:
            raise ValueError("component-change order changed")
        if item["fromAvailability"] not in {"available", "unavailable"} or item[
            "toAvailability"
        ] not in {"available", "unavailable"}:
            raise ValueError("invalid component-change availability")
        expected_availability_changed = (
            item["fromAvailability"] != item["toAvailability"]
        )
        if item["availabilityChanged"] is not expected_availability_changed:
            raise ValueError("component availability transition is invalid")
        if not _sha256_prefixed(item["fromDigest"]) or not _sha256_prefixed(
            item["toDigest"]
        ):
            raise ValueError("invalid component digest transition")
        expected_digest_changed = item["fromDigest"] != item["toDigest"]
        if item["digestChanged"] is not expected_digest_changed:
            raise ValueError("component digest transition is invalid")
        if expected_availability_changed or expected_digest_changed:
            changed_components += 1
    if payload["changedComponentCount"] != changed_components:
        raise ValueError("changedComponentCount is invalid")

    summary_changes = payload["summaryChanges"]
    if not isinstance(summary_changes, list):
        raise ValueError("summaryChanges must be an array")
    if payload["changedSummaryMetricCount"] != len(summary_changes):
        raise ValueError("changedSummaryMetricCount is invalid")
    if len(summary_changes) > len(_SUMMARY_KEYS):
        raise ValueError("too many summary changes")
    prior_index = -1
    seen: set[str] = set()
    for item in summary_changes:
        if not isinstance(item, Mapping) or not _exact_keys(
            item, _SUMMARY_CHANGE_KEYS
        ):
            raise ValueError("invalid summary-change fields")
        metric = item["metric"]
        if not isinstance(metric, str) or metric not in _SUMMARY_KEYS or metric in seen:
            raise ValueError("invalid or duplicate summary-change metric")
        metric_index = _SUMMARY_KEYS.index(metric)
        if metric_index <= prior_index:
            raise ValueError("summary changes are not in canonical metric order")
        prior_index = metric_index
        seen.add(metric)
        if not _nonnegative_number(item["from"]) or not _nonnegative_number(item["to"]):
            raise ValueError("summary-change values must be nonnegative")
        if not _nonnegative_number(abs(float(item["delta"]))):
            raise ValueError("summary-change delta must be finite")
        if item["delta"] != item["to"] - item["from"]:
            raise ValueError("summary-change delta derivation is invalid")

    if (
        payload["causeAssigned"] is not False
        or payload["severityAssigned"] is not False
        or payload["readOnly"] is not True
        or payload["executionAuthority"] is not False
        or payload["effectPerformed"] is not False
    ):
        raise ValueError("system-change receipt crosses the descriptive boundary")

    expected_digest = _js_json_sha256(_change_digest_body(payload))
    if payload["changeDigest"] != expected_digest:
        raise ValueError("system-change digest mismatch")


class SystemObservationArchive:
    """Persist PhiShell observation receipts through governed canonical memory."""

    def __init__(
        self,
        *,
        service: GovernedMemoryService,
        publisher: MemoryReceiptPublisher,
        principal_id: str,
        authority: AuthorityContext,
        scope_id: str,
        classification: str,
        retention_policy_id: str = SYSTEM_HISTORY_RETENTION_DEFAULT,
    ) -> None:
        self.service = service
        self.publisher = publisher
        self.principal_id = require_nonempty(principal_id, "principal_id")
        self.authority = authority
        self.scope_id = require_nonempty(scope_id, "scope_id")
        self.classification = require_nonempty(classification, "classification")
        self.retention_policy_id = require_nonempty(
            retention_policy_id, "retention_policy_id"
        )

    def archive_state(
        self,
        receipt: Mapping[str, object],
        *,
        task_id: str,
    ) -> SystemArchiveResult:
        try:
            validate_system_state_receipt(receipt)
        except (TypeError, ValueError, KeyError) as exc:
            return SystemArchiveResult(
                status="invalid",
                error_code=f"SYSTEM_STATE_INVALID:{exc}",
            )
        digest = str(receipt["receiptDigest"])
        return self._archive(
            receipt,
            kind="state",
            digest=digest,
            created_at=str(receipt["composedAt"]),
            provenance_refs=(
                f"system-state:{digest}",
                *(
                    f"component:{item['id']}:{item['digest']}"
                    for item in receipt["components"]
                    if isinstance(item, Mapping)
                ),
            ),
            task_id=task_id,
        )

    def archive_change(
        self,
        receipt: Mapping[str, object],
        *,
        task_id: str,
    ) -> SystemArchiveResult:
        try:
            validate_system_change_receipt(receipt)
        except (TypeError, ValueError, KeyError) as exc:
            return SystemArchiveResult(
                status="invalid",
                error_code=f"SYSTEM_CHANGE_INVALID:{exc}",
            )
        digest = str(receipt["changeDigest"])
        return self._archive(
            receipt,
            kind="change",
            digest=digest,
            created_at=str(receipt["recordedAt"]),
            provenance_refs=(
                f"system-change:{digest}",
                f"system-state:{receipt['fromReceiptDigest']}",
                f"system-state:{receipt['toReceiptDigest']}",
            ),
            task_id=task_id,
        )

    def _archive(
        self,
        payload: Mapping[str, object],
        *,
        kind: Literal["state", "change"],
        digest: str,
        created_at: str,
        provenance_refs: tuple[str, ...],
        task_id: str,
    ) -> SystemArchiveResult:
        task_id = require_nonempty(task_id, "task_id")
        hex_digest = digest.removeprefix("sha256:")
        record_id = f"phishell-system-{kind}:{hex_digest}"
        text = strict_canonical_json(dict(payload))
        record = MemoryRecord.build(
            record_id=record_id,
            revision=1,
            source_id=f"phishell.system-{kind}",
            source_kind="subsystem",
            provenance_refs=provenance_refs,
            created_at=created_at,
            scope_id=self.scope_id,
            classification=self.classification,
            retention_policy_id=self.retention_policy_id,
            expires_at=None,
            epistemic_kind="source",
            text=text,
        )

        existing = self.service.store.get(
            record_id,
            now=datetime.fromisoformat(record.created_at),
        )
        if existing is not None:
            if existing.record_sha256 != record.record_sha256:
                return SystemArchiveResult(
                    status="invalid",
                    record_id=record_id,
                    error_code="SYSTEM_HISTORY_RECORD_COLLISION",
                )
            return SystemArchiveResult(
                status="exists",
                record_id=existing.record_id,
                record_sha256=existing.record_sha256,
            )

        operation_id = f"system-history:{kind}:{hex_digest}"
        result = self.service.put(
            record,
            principal_id=self.principal_id,
            task_id=task_id,
            authority=self.authority,
            operation_id=operation_id,
        )
        if result.status != "ok":
            mapped = (
                "blocked"
                if result.status == "blocked"
                else "invalid"
                if result.status == "invalid"
                else "unavailable"
            )
            return SystemArchiveResult(
                status=mapped,
                record_id=record_id,
                error_code=result.error_code,
            )

        try:
            self.publisher.publish_pending()
        except Exception:
            return SystemArchiveResult(
                status="unavailable",
                record_id=record_id,
                memory_receipt_id=result.receipt_id,
                error_code="SYSTEM_HISTORY_PUBLICATION_FAILED",
            )

        published = self.service.store.get(
            record_id,
            now=datetime.fromisoformat(record.created_at),
        )
        if published is None or published.record_sha256 != record.record_sha256:
            return SystemArchiveResult(
                status="unavailable",
                record_id=record_id,
                memory_receipt_id=result.receipt_id,
                error_code="SYSTEM_HISTORY_PUBLICATION_UNCONFIRMED",
            )
        return SystemArchiveResult(
            status="saved",
            record_id=published.record_id,
            record_sha256=published.record_sha256,
            memory_receipt_id=result.receipt_id,
        )
