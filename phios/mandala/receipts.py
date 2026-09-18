from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .contracts import MANDALA_CONTRACT_VERSION, Gate, MandalaPacket, MandalaStatus


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def receipt_meta(
    packet: MandalaPacket,
    *,
    status: MandalaStatus,
    produced_by: str,
    parent_receipt_id: str | None = None,
) -> dict[str, Any]:
    return {
        "receipt_id": str(uuid.uuid4()),
        "packet_id": packet.packet_id,
        "task_id": packet.task_id,
        "status": status,
        "produced_by": produced_by,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "contract_version": packet.contract_version,
        "parent_receipt_id": parent_receipt_id,
    }


@dataclass(frozen=True, kw_only=True)
class ReceiptEnvelope:
    receipt_id: str
    packet_id: str
    task_id: str
    status: MandalaStatus
    produced_by: str
    timestamp_utc: str
    contract_version: str = MANDALA_CONTRACT_VERSION
    parent_receipt_id: str | None = None
    receipt_type: str = field(init=False, default="ReceiptEnvelope")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True, kw_only=True)
class GateReceipt(ReceiptEnvelope):
    gate: Gate
    reason: str
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    authority: dict[str, Any] = field(default_factory=dict)
    receipt_type: str = field(init=False, default="GateReceipt")


@dataclass(frozen=True, kw_only=True)
class RouteReceipt(ReceiptEnvelope):
    roles_models: dict[str, str]
    route_mode: str
    score_inputs: dict[str, Any] = field(default_factory=dict)
    resource_state: dict[str, Any] = field(default_factory=dict)
    fallbacks: tuple[str, ...] = field(default_factory=tuple)
    receipt_type: str = field(init=False, default="RouteReceipt")


@dataclass(frozen=True, kw_only=True)
class PerceptionReceipt(ReceiptEnvelope):
    native_evidence_ref: str | None
    transforms: tuple[str, ...] = field(default_factory=tuple)
    acuity_status: str = "unknown"
    limitations: tuple[str, ...] = field(default_factory=tuple)
    source_id: str | None = None
    native_sha256: str | None = None
    observation_sha256: str | None = None
    native_preserved: bool = False
    media_type: str | None = None
    acquisition_method: str | None = None
    acquisition_status: str | None = None
    source_locator: str | None = None
    source_root_ref: str | None = None
    capture_region: dict[str, int] = field(default_factory=dict)
    capture_backend: str | None = None
    capture_attempts: int = 0
    recovery_steps: tuple[str, ...] = field(default_factory=tuple)
    receipt_type: str = field(init=False, default="PerceptionReceipt")


@dataclass(frozen=True, kw_only=True)
class RealityReceipt(ReceiptEnvelope):
    claims_checked: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    evidence_used: tuple[str, ...] = field(default_factory=tuple)
    unresolved_contradictions: tuple[str, ...] = field(default_factory=tuple)
    receipt_type: str = field(init=False, default="RealityReceipt")


@dataclass(frozen=True, kw_only=True)
class ActionReceipt(ReceiptEnvelope):
    approved_grant: tuple[str, ...] = field(default_factory=tuple)
    side_effect: dict[str, Any] = field(default_factory=dict)
    outcome: str
    external_identifiers: dict[str, str] = field(default_factory=dict)
    receipt_type: str = field(init=False, default="ActionReceipt")


@dataclass(frozen=True, kw_only=True)
class MemoryPromotionReceipt(ReceiptEnvelope):
    candidate_memory: dict[str, Any] = field(default_factory=dict)
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    durability_reason: str
    conflict_result: str
    promotion_status: str
    receipt_type: str = field(init=False, default="MemoryPromotionReceipt")


@dataclass(frozen=True, kw_only=True)
class AbortReceipt(ReceiptEnvelope):
    terminal_reason: str
    eligible_artifacts: tuple[str, ...] = field(default_factory=tuple)
    quarantined_artifacts: tuple[str, ...] = field(default_factory=tuple)
    receipt_type: str = field(init=False, default="AbortReceipt")
