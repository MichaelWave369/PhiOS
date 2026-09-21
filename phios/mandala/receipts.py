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
    derived_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    observation_evidence_ref: str | None = None
    derivation_chain: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    recovery_backend: str | None = None
    transformation_lineage_sha256s: tuple[str, ...] = field(default_factory=tuple)
    exactness_class: str | None = None
    taint_labels: tuple[str, ...] = field(default_factory=tuple)
    burst_frame_refs: tuple[str, ...] = field(default_factory=tuple)
    burst_frame_records: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    selected_evidence_ref: str | None = None
    selection_method: str | None = None
    input_evidence_ref: str | None = None
    enhancement_method: str | None = None
    enhancement_parameters: dict[str, Any] = field(default_factory=dict)
    enhancement_backend: str | None = None
    receipt_type: str = field(init=False, default="PerceptionReceipt")


@dataclass(frozen=True, kw_only=True)
class OcrReceipt(ReceiptEnvelope):
    source_evidence_ref: str
    output_evidence_ref: str | None
    engine: str
    engine_version: str | None
    language: str
    page_segmentation_mode: int
    text_sha256: str | None = None
    character_count: int = 0
    token_count: int = 0
    confidence_count: int = 0
    confidence_mean: float | None = None
    confidence_min: float | None = None
    confidence_max: float | None = None
    limitations: tuple[str, ...] = field(default_factory=tuple)
    interpretation_status: str = "unknown"
    transformation_lineage_sha256s: tuple[str, ...] = field(default_factory=tuple)
    exactness_class: str | None = None
    taint_labels: tuple[str, ...] = field(default_factory=tuple)
    receipt_type: str = field(init=False, default="OcrReceipt")


@dataclass(frozen=True, kw_only=True)
class RealityReceipt(ReceiptEnvelope):
    claims_checked: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    evidence_used: tuple[str, ...] = field(default_factory=tuple)
    unresolved_contradictions: tuple[str, ...] = field(default_factory=tuple)
    unresolved_claims: tuple[str, ...] = field(default_factory=tuple)
    verdict_summary: dict[str, int] = field(default_factory=dict)
    verification_method: str | None = None
    promotion_status: str = "not_promoted"
    limitations: tuple[str, ...] = field(default_factory=tuple)
    observation_frontier_sha256: str | None = None
    observability_receipt_sha256: str | None = None
    observability_status: str = "not_evaluated"
    receipt_type: str = field(init=False, default="RealityReceipt")


@dataclass(frozen=True, kw_only=True)
class EffectBoundaryReceipt(ReceiptEnvelope):
    capability_id: str
    capability_version: str
    capability_risk: str
    capability_effects: tuple[str, ...] = field(default_factory=tuple)
    executor_effects: tuple[str, ...] = field(default_factory=tuple)
    active_effects: tuple[str, ...] = field(default_factory=tuple)
    effect_contract_match: bool = False
    classification_complete: bool = False
    semantic_read_label_conflict: bool = False
    effect_policy_sha256: str = ""
    reason: str = ""
    action_authority: bool = False
    execution_authority: bool = False
    receipt_sha256: str = ""
    receipt_type: str = field(init=False, default="EffectBoundaryReceipt")


@dataclass(frozen=True, kw_only=True)
class ActionReceipt(ReceiptEnvelope):
    approved_grant: tuple[str, ...] = field(default_factory=tuple)
    side_effect: dict[str, Any] = field(default_factory=dict)
    outcome: str
    external_identifiers: dict[str, str] = field(default_factory=dict)
    receipt_type: str = field(init=False, default="ActionReceipt")


@dataclass(frozen=True, kw_only=True)
class ReadAdmissibilityReceipt(ReceiptEnvelope):
    operation_id: str
    principal_id: str
    record_id: str
    revision: int
    record_sha256: str
    readable_as_context: bool
    currentness: str
    scope_id: str
    classification: str
    authorization_policy_sha256: str
    authority_context_sha256: str
    epistemic_kind: str
    exactness_class: str | None = None
    transformation_lineage_sha256s: tuple[str, ...] = field(default_factory=tuple)
    taint_labels: tuple[str, ...] = field(default_factory=tuple)
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    receipt_sha256: str = ""
    receipt_type: str = field(init=False, default="ReadAdmissibilityReceipt")


@dataclass(frozen=True, kw_only=True)
class MemoryOperationReceipt(ReceiptEnvelope):
    operation_id: str
    operation: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    record_versions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    authorization_policy_sha256: str = ""
    input_sha256: str = ""
    canonical_status: str = "unchanged"
    index_status: str = "unavailable"
    embedding_identity: dict[str, Any] | None = None
    index_generation: str | None = None
    error_code: str | None = None
    transformation_lineage: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    transformation_lineage_sha256s: tuple[str, ...] = field(default_factory=tuple)
    exactness_classes: tuple[str, ...] = field(default_factory=tuple)
    taint_labels: tuple[str, ...] = field(default_factory=tuple)
    promotion_status: str = "not_promoted"
    action_authority: bool = False
    execution_authority: bool = False
    receipt_sha256: str = ""
    receipt_type: str = field(init=False, default="MemoryOperationReceipt")


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
