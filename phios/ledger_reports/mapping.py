from __future__ import annotations

from typing import Any

from .models import ProjectedRow
from .policy import LedgerSnapshotPolicy
from .validation import sha256_bytes

MAPPING_VERSION = "phios.ledger_projection.v0.1"
EXECUTION_SCHEMA_VERSION = "phios.execution_receipt.v0.1"
MANDALA_CONTRACT_VERSION = "phios.mandala.v0.1"

MANDALA_RECEIPT_TYPES = {
    "GateReceipt",
    "RouteReceipt",
    "PerceptionReceipt",
    "OcrReceipt",
    "RealityReceipt",
    "ActionReceipt",
    "EffectBoundaryReceipt",
    "IndependenceReceipt",
    "DisagreementDecompositionReceipt",
    "VerifierSemanticsReceipt",
    "GovernanceEscalationReceipt",
    "MemoryOperationReceipt",
    "MemoryPromotionReceipt",
    "AbortReceipt",
}


def project_execution_row(
    payload: dict[str, Any],
    *,
    raw_row: bytes,
    line_number: int,
    byte_start: int,
    byte_end: int,
    policy: LedgerSnapshotPolicy,
) -> ProjectedRow:
    if payload.get("schema_version") != EXECUTION_SCHEMA_VERSION:
        raise ValueError("unknown execution receipt schema_version")
    receipt_id = _required_str(payload, "receipt_id")
    projected: dict[str, Any] = {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "timestamp_utc": _required_str(payload, "timestamp_utc"),
        "capability_id": _required_str(payload, "capability_id"),
        "planner": _required_str(payload, "planner"),
        "input_sha256": _required_str(payload, "input_sha256"),
        "permissions_requested": _string_list(payload.get("permissions_requested"), "permissions_requested"),
        "permission_status": _required_str(payload, "permission_status"),
        "execution_status": _required_str(payload, "execution_status"),
        "artifact_sha256": (
            str(payload["artifact_sha256"])
            if policy.include_execution_artifact_sha256
            and isinstance(payload.get("artifact_sha256"), str)
            else None
        ),
        "packet_id": _optional_str(payload.get("packet_id"), "packet_id"),
        "gate_receipt_id": _optional_str(payload.get("gate_receipt_id"), "gate_receipt_id"),
        "action_receipt_id": _optional_str(
            payload.get("action_receipt_id"),
            "action_receipt_id",
        ),
        "mandala_status": _optional_str(payload.get("mandala_status"), "mandala_status"),
    }
    provenance = payload.get("governed_provenance")
    if provenance is None:
        projected["governed_provenance"] = None
    elif isinstance(provenance, dict):
        projected["governed_provenance"] = {
            "schema_version": _required_str(provenance, "schema_version"),
            "plan_id": _required_str(provenance, "plan_id"),
            "plan_state_sha256": _required_str(provenance, "plan_state_sha256"),
            "plan_revision": _required_int(provenance, "plan_revision"),
            "transition_index": _required_int(provenance, "transition_index"),
            "source_state_id": _required_str(provenance, "source_state_id"),
            "target_state_id": _required_str(provenance, "target_state_id"),
            "action_binding_sha256": _required_str(provenance, "action_binding_sha256"),
        }
    else:
        raise ValueError("governed_provenance must be an object or null")

    if policy.include_execution_artifact_path:
        projected["artifact_path"] = _optional_str(
            payload.get("artifact_path"),
            "artifact_path",
        )
    if policy.include_execution_error:
        projected["error"] = _optional_str(payload.get("error"), "error")

    return ProjectedRow(
        payload=projected,
        source_receipt_id=receipt_id,
        source_line=line_number,
        source_byte_start=byte_start,
        source_byte_end=byte_end,
        source_row_sha256=sha256_bytes(raw_row),
    )


def project_mandala_row(
    payload: dict[str, Any],
    *,
    raw_row: bytes,
    line_number: int,
    byte_start: int,
    byte_end: int,
    policy: LedgerSnapshotPolicy,
) -> ProjectedRow:
    if payload.get("contract_version") != MANDALA_CONTRACT_VERSION:
        raise ValueError("unknown Mandala contract_version")
    receipt_type = _required_str(payload, "receipt_type")
    if receipt_type not in MANDALA_RECEIPT_TYPES:
        raise ValueError(f"unknown Mandala receipt_type: {receipt_type}")

    receipt_id = _required_str(payload, "receipt_id")
    projected: dict[str, Any] = {
        "contract_version": MANDALA_CONTRACT_VERSION,
        "receipt_type": receipt_type,
        "receipt_id": receipt_id,
        "packet_id": _required_str(payload, "packet_id"),
        "task_id": _required_str(payload, "task_id"),
        "status": _required_str(payload, "status"),
        "produced_by": _required_str(payload, "produced_by"),
        "timestamp_utc": _required_str(payload, "timestamp_utc"),
        "parent_receipt_id": _optional_str(
            payload.get("parent_receipt_id"),
            "parent_receipt_id",
        ),
    }

    if receipt_type == "GateReceipt":
        projected["gate"] = _required_str(payload, "gate")
        if policy.include_mandala_reason:
            projected["reason"] = _required_str(payload, "reason")
    elif receipt_type == "RouteReceipt":
        projected["route_mode"] = _required_str(payload, "route_mode")
        projected["fallback_count"] = len(
            _string_list(payload.get("fallbacks", []), "fallbacks")
        )
    elif receipt_type == "PerceptionReceipt":
        projected["acuity_status"] = _required_str(payload, "acuity_status")
        projected["media_type"] = _optional_str(payload.get("media_type"), "media_type")
        projected["acquisition_method"] = _optional_str(
            payload.get("acquisition_method"),
            "acquisition_method",
        )
        projected["acquisition_status"] = _optional_str(
            payload.get("acquisition_status"),
            "acquisition_status",
        )
        projected["capture_attempts"] = _required_int(payload, "capture_attempts")
        projected["recovery_step_count"] = len(
            _string_list(payload.get("recovery_steps", []), "recovery_steps")
        )
        projected["transformation_lineage_sha256s"] = _string_list(
            payload.get("transformation_lineage_sha256s", []),
            "transformation_lineage_sha256s",
        )
        projected["exactness_class"] = _optional_str(
            payload.get("exactness_class"),
            "exactness_class",
        )
        projected["taint_labels"] = _string_list(
            payload.get("taint_labels", []),
            "taint_labels",
        )
    elif receipt_type == "OcrReceipt":
        projected["engine"] = _required_str(payload, "engine")
        projected["engine_version"] = _optional_str(
            payload.get("engine_version"),
            "engine_version",
        )
        projected["language"] = _required_str(payload, "language")
        projected["page_segmentation_mode"] = _required_int(
            payload,
            "page_segmentation_mode",
        )
        projected["character_count"] = _required_int(payload, "character_count")
        projected["token_count"] = _required_int(payload, "token_count")
        projected["confidence_count"] = _required_int(payload, "confidence_count")
        projected["interpretation_status"] = _required_str(
            payload,
            "interpretation_status",
        )
        projected["transformation_lineage_sha256s"] = _string_list(
            payload.get("transformation_lineage_sha256s", []),
            "transformation_lineage_sha256s",
        )
        projected["exactness_class"] = _optional_str(
            payload.get("exactness_class"),
            "exactness_class",
        )
        projected["taint_labels"] = _string_list(
            payload.get("taint_labels", []),
            "taint_labels",
        )
    elif receipt_type == "RealityReceipt":
        verdict_summary = payload.get("verdict_summary")
        if not isinstance(verdict_summary, dict):
            raise ValueError("verdict_summary must be an object")
        projected["verdict_summary"] = {
            str(key): _coerce_nonnegative_int(value, f"verdict_summary.{key}")
            for key, value in sorted(verdict_summary.items())
        }
        projected["verification_method"] = _optional_str(
            payload.get("verification_method"),
            "verification_method",
        )
        projected["promotion_status"] = _required_str(payload, "promotion_status")
        projected["observation_frontier_sha256"] = _optional_str(
            payload.get("observation_frontier_sha256"),
            "observation_frontier_sha256",
        )
        projected["observability_receipt_sha256"] = _optional_str(
            payload.get("observability_receipt_sha256"),
            "observability_receipt_sha256",
        )
        projected["observability_status"] = _optional_str(
            payload.get("observability_status"),
            "observability_status",
        )
    elif receipt_type == "EffectBoundaryReceipt":
        projected["capability_id"] = _required_str(payload, "capability_id")
        projected["capability_version"] = _required_str(
            payload,
            "capability_version",
        )
        projected["capability_risk"] = _required_str(payload, "capability_risk")
        projected["capability_effects"] = _string_list(
            payload.get("capability_effects", []),
            "capability_effects",
        )
        projected["executor_effects"] = _string_list(
            payload.get("executor_effects", []),
            "executor_effects",
        )
        projected["active_effects"] = _string_list(
            payload.get("active_effects", []),
            "active_effects",
        )
        projected["effect_contract_match"] = _required_bool(
            payload,
            "effect_contract_match",
        )
        projected["classification_complete"] = _required_bool(
            payload,
            "classification_complete",
        )
        projected["semantic_read_label_conflict"] = _required_bool(
            payload,
            "semantic_read_label_conflict",
        )
        projected["effect_policy_sha256"] = _required_str(
            payload,
            "effect_policy_sha256",
        )
        projected["reason"] = _required_str(payload, "reason")
        projected["action_authority"] = _required_bool(
            payload,
            "action_authority",
        )
        projected["execution_authority"] = _required_bool(
            payload,
            "execution_authority",
        )
    elif receipt_type == "IndependenceReceipt":
        projected["claim_id"] = _required_str(payload, "claim_id")
        projected["independence_status"] = _required_str(
            payload,
            "independence_status",
        )
        projected["independent_pair_count"] = _required_int(
            payload,
            "independent_pair_count",
        )
        projected["dependent_pair_count"] = _required_int(
            payload,
            "dependent_pair_count",
        )
        projected["unknown_pair_count"] = _required_int(
            payload,
            "unknown_pair_count",
        )
        projected["demonstrated_independent_group_count"] = _required_int(
            payload,
            "demonstrated_independent_group_count",
        )
        projected["agreement_without_independence"] = _required_bool(
            payload,
            "agreement_without_independence",
        )
        projected["assessment_sha256"] = _required_str(
            payload,
            "assessment_sha256",
        )
        projected["operational_authority"] = _required_bool(
            payload,
            "operational_authority",
        )
        projected["action_authority"] = _required_bool(
            payload,
            "action_authority",
        )
        projected["execution_authority"] = _required_bool(
            payload,
            "execution_authority",
        )
    elif receipt_type == "DisagreementDecompositionReceipt":
        projected["claim_id"] = _required_str(payload, "claim_id")
        projected["independence_receipt_sha256"] = _required_str(
            payload,
            "independence_receipt_sha256",
        )
        projected["disagreement_status"] = _required_str(
            payload,
            "disagreement_status",
        )
        projected["contested_group_count"] = _required_int(
            payload,
            "contested_group_count",
        )
        projected["independence_qualified_agreement"] = _required_bool(
            payload,
            "independence_qualified_agreement",
        )
        projected["consensus_authority"] = _required_bool(
            payload,
            "consensus_authority",
        )
        projected["promotion_status"] = _required_str(
            payload,
            "promotion_status",
        )
        projected["assessment_sha256"] = _required_str(
            payload,
            "assessment_sha256",
        )
        projected["operational_authority"] = _required_bool(
            payload,
            "operational_authority",
        )
        projected["action_authority"] = _required_bool(
            payload,
            "action_authority",
        )
        projected["execution_authority"] = _required_bool(
            payload,
            "execution_authority",
        )
    elif receipt_type == "VerifierSemanticsReceipt":
        projected["semantics_schema_version"] = _required_str(
            payload,
            "semantics_schema_version",
        )
        projected["source_reality_receipt_id"] = _required_str(
            payload,
            "source_reality_receipt_id",
        )
        projected["source_reality_receipt_sha256"] = _required_str(
            payload,
            "source_reality_receipt_sha256",
        )
        projected["verifier_id"] = _required_str(payload, "verifier_id")
        projected["verification_method"] = _required_str(
            payload,
            "verification_method",
        )
        projected["source_status"] = _required_str(payload, "source_status")
        verdict_summary = payload.get("verdict_summary")
        if not isinstance(verdict_summary, dict):
            raise ValueError("verdict_summary must be an object")
        projected["verdict_summary"] = {
            str(key): _coerce_nonnegative_int(value, f"verdict_summary.{key}")
            for key, value in sorted(verdict_summary.items())
        }
        for field in (
            "detects_evidence_state",
            "may_emit_escalation_request",
            "may_authorize_remediation",
            "may_execute_remediation",
            "may_promote",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            projected[field] = _required_bool(payload, field)
    elif receipt_type == "GovernanceEscalationReceipt":
        projected["escalation_schema_version"] = _required_str(
            payload,
            "escalation_schema_version",
        )
        projected["source_reality_receipt_id"] = _required_str(
            payload,
            "source_reality_receipt_id",
        )
        projected["source_reality_receipt_sha256"] = _required_str(
            payload,
            "source_reality_receipt_sha256",
        )
        projected["verifier_semantics_receipt_sha256"] = _required_str(
            payload,
            "verifier_semantics_receipt_sha256",
        )
        projected["request_id"] = _required_str(payload, "request_id")
        projected["disposition"] = _required_str(payload, "disposition")
        projected["routing_status"] = _required_str(payload, "routing_status")
        projected["target_ref"] = _required_str(payload, "target_ref")
        projected["trigger_claim_count"] = len(
            _string_list(payload.get("trigger_claim_ids", []), "trigger_claim_ids")
        )
        projected["candidate_capability_id"] = _optional_str(
            payload.get("candidate_capability_id"),
            "candidate_capability_id",
        )
        projected["candidate_capability_version"] = _optional_str(
            payload.get("candidate_capability_version"),
            "candidate_capability_version",
        )
        projected["candidate_capability_risk"] = _optional_str(
            payload.get("candidate_capability_risk"),
            "candidate_capability_risk",
        )
        projected["candidate_capability_contract_sha256"] = _optional_str(
            payload.get("candidate_capability_contract_sha256"),
            "candidate_capability_contract_sha256",
        )
        projected["candidate_payload_sha256"] = _optional_str(
            payload.get("candidate_payload_sha256"),
            "candidate_payload_sha256",
        )
        projected["requested_permission_count"] = len(
            _string_list(
                payload.get("requested_permissions", []),
                "requested_permissions",
            )
        )
        projected["requested_effect_count"] = len(
            _string_list(payload.get("requested_effects", []), "requested_effects")
        )
        for field in (
            "downstream_authority_required",
            "remediation_authorized",
            "remediation_executed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            projected[field] = _required_bool(payload, field)
        projected["promotion_status"] = _required_str(payload, "promotion_status")
    elif receipt_type == "ActionReceipt":
        projected["outcome"] = _required_str(payload, "outcome")
        side_effect = payload.get("side_effect")
        if not isinstance(side_effect, dict):
            raise ValueError("side_effect must be an object")
        projected["capability_id"] = (
            str(side_effect["capability_id"])
            if isinstance(side_effect.get("capability_id"), str)
            else None
        )
        projected["approved_grant"] = _string_list(
            payload.get("approved_grant", []),
            "approved_grant",
        )
    elif receipt_type == "MemoryOperationReceipt":
        projected["operation"] = _required_str(payload, "operation")
        projected["canonical_status"] = _required_str(payload, "canonical_status")
        projected["index_status"] = _required_str(payload, "index_status")
        projected["error_code"] = _optional_str(payload.get("error_code"), "error_code")
        projected["promotion_status"] = _required_str(payload, "promotion_status")
        projected["action_authority"] = _required_bool(payload, "action_authority")
        projected["execution_authority"] = _required_bool(payload, "execution_authority")
        projected["index_generation"] = _optional_str(
            payload.get("index_generation"),
            "index_generation",
        )
        projected["transformation_lineage_sha256s"] = _string_list(
            payload.get("transformation_lineage_sha256s", []),
            "transformation_lineage_sha256s",
        )
        projected["exactness_classes"] = _string_list(
            payload.get("exactness_classes", []),
            "exactness_classes",
        )
        projected["taint_labels"] = _string_list(
            payload.get("taint_labels", []),
            "taint_labels",
        )
    elif receipt_type == "MemoryPromotionReceipt":
        projected["durability_reason"] = _required_str(payload, "durability_reason")
        projected["conflict_result"] = _required_str(payload, "conflict_result")
        projected["promotion_status"] = _required_str(payload, "promotion_status")
    elif receipt_type == "AbortReceipt":
        projected["terminal_reason_present"] = bool(
            isinstance(payload.get("terminal_reason"), str)
            and str(payload.get("terminal_reason")).strip()
        )

    return ProjectedRow(
        payload=projected,
        source_receipt_id=receipt_id,
        source_line=line_number,
        source_byte_start=byte_start,
        source_byte_end=byte_end,
        source_row_sha256=sha256_bytes(raw_row),
    )


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} entries must be strings")
        out.append(item)
    return out


def _coerce_nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value
