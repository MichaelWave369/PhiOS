from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Iterable

from .contracts import MandalaStatus
from .ledger import MandalaReceiptLedger
from .receipts import (
    GovernanceEscalationReceipt,
    RealityReceipt,
    VerifierSemanticsReceipt,
)

VERIFIER_SEMANTICS_SCHEMA_VERSION = "phios.verifier_semantics.v0.1"
GOVERNANCE_ESCALATION_SCHEMA_VERSION = "phios.governance_escalation.v0.1"

_ALLOWED_DISPOSITIONS = ("REVIEW", "REVERIFY", "REMEDIATE")
_ALLOWED_VERDICTS = ("SUPPORTED", "CONTRADICTED", "UNRESOLVED", "BLOCKED")


class GovernanceEscalationError(ValueError):
    """Raised when a verifier/escalation contract cannot be evaluated safely."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GovernanceEscalationError(
            "governance escalation payload must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceEscalationError(f"{label} must be non-empty")
    return value.strip()


def _require_sha256(value: str, label: str) -> str:
    value = _require_text(value, label).lower()
    if len(value) != 64:
        raise GovernanceEscalationError(f"{label} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise GovernanceEscalationError(f"{label} must be SHA-256 hex") from exc
    return value


def _labels(values: Iterable[str], label: str) -> tuple[str, ...]:
    return tuple(sorted({_require_text(value, label) for value in values}))


@dataclass(frozen=True, slots=True)
class EscalationRequest:
    request_id: str
    disposition: str
    reason: str
    target_ref: str
    trigger_claim_ids: tuple[str, ...]
    candidate_capability_id: str | None = None
    candidate_payload_sha256: str | None = None
    requested_permissions: tuple[str, ...] = ()
    requested_effects: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        disposition: str,
        reason: str,
        target_ref: str,
        trigger_claim_ids: tuple[str, ...],
        candidate_capability_id: str | None = None,
        candidate_payload_sha256: str | None = None,
        requested_permissions: tuple[str, ...] = (),
        requested_effects: tuple[str, ...] = (),
    ) -> "EscalationRequest":
        normalized_disposition = _require_text(
            disposition,
            "disposition",
        ).upper()
        if normalized_disposition not in _ALLOWED_DISPOSITIONS:
            raise GovernanceEscalationError(
                f"disposition must be one of {_ALLOWED_DISPOSITIONS}"
            )
        normalized_reason = _require_text(reason, "reason")
        normalized_target = _require_text(target_ref, "target_ref")
        normalized_claims = _labels(trigger_claim_ids, "trigger_claim_id")
        if not normalized_claims:
            raise GovernanceEscalationError(
                "trigger_claim_ids must not be empty"
            )
        permissions = _labels(requested_permissions, "requested_permission")
        effects = _labels(requested_effects, "requested_effect")

        capability_id: str | None
        payload_sha256: str | None
        if normalized_disposition == "REMEDIATE":
            capability_id = _require_text(
                candidate_capability_id or "",
                "candidate_capability_id",
            )
            payload_sha256 = _require_sha256(
                candidate_payload_sha256 or "",
                "candidate_payload_sha256",
            )
            if not permissions:
                raise GovernanceEscalationError(
                    "REMEDIATE requires requested_permissions"
                )
            if not effects or effects == ("none",):
                raise GovernanceEscalationError(
                    "REMEDIATE requires consequential requested_effects"
                )
        else:
            if (
                candidate_capability_id is not None
                or candidate_payload_sha256 is not None
                or permissions
                or effects
            ):
                raise GovernanceEscalationError(
                    "non-remediation escalation cannot carry an action contract"
                )
            capability_id = None
            payload_sha256 = None

        seed = {
            "schema_version": GOVERNANCE_ESCALATION_SCHEMA_VERSION,
            "disposition": normalized_disposition,
            "reason": normalized_reason,
            "target_ref": normalized_target,
            "trigger_claim_ids": list(normalized_claims),
            "candidate_capability_id": capability_id,
            "candidate_payload_sha256": payload_sha256,
            "requested_permissions": list(permissions),
            "requested_effects": list(effects),
        }
        request_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "phios.governance-escalation-request:" + _sha256(seed),
            )
        )
        return cls(
            request_id=request_id,
            disposition=normalized_disposition,
            reason=normalized_reason,
            target_ref=normalized_target,
            trigger_claim_ids=normalized_claims,
            candidate_capability_id=capability_id,
            candidate_payload_sha256=payload_sha256,
            requested_permissions=permissions,
            requested_effects=effects,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "disposition": self.disposition,
            "reason": self.reason,
            "target_ref": self.target_ref,
            "trigger_claim_ids": list(self.trigger_claim_ids),
            "candidate_capability_id": self.candidate_capability_id,
            "candidate_payload_sha256": self.candidate_payload_sha256,
            "requested_permissions": list(self.requested_permissions),
            "requested_effects": list(self.requested_effects),
        }


@dataclass(frozen=True, slots=True)
class GovernanceEscalationResult:
    verifier_semantics: VerifierSemanticsReceipt
    escalation: GovernanceEscalationReceipt


class GovernanceEscalationService:
    """Turn verifier findings into bounded requests, never remediation authority."""

    def __init__(self, ledger: MandalaReceiptLedger | None = None) -> None:
        self.ledger = ledger

    def assess(
        self,
        *,
        source_receipt: RealityReceipt,
        request: EscalationRequest,
    ) -> GovernanceEscalationResult:
        source_sha = self._validate_source_receipt(source_receipt)
        semantics = self._verifier_semantics(
            source_receipt=source_receipt,
            source_sha256=source_sha,
        )
        trigger_verdicts = self._trigger_verdicts(
            source_receipt=source_receipt,
            trigger_claim_ids=request.trigger_claim_ids,
        )
        routing_status, reason, status = self._route(
            request=request,
            trigger_verdicts=trigger_verdicts,
        )
        escalation = self._escalation_receipt(
            source_receipt=source_receipt,
            source_sha256=source_sha,
            semantics=semantics,
            request=request,
            trigger_verdicts=trigger_verdicts,
            routing_status=routing_status,
            reason=reason,
            status=status,
        )
        if self.ledger is not None:
            self.ledger.append(semantics)
            self.ledger.append(escalation)
        return GovernanceEscalationResult(
            verifier_semantics=semantics,
            escalation=escalation,
        )

    def _validate_source_receipt(self, receipt: RealityReceipt) -> str:
        if receipt.produced_by != "reality.verifier":
            raise GovernanceEscalationError(
                "source receipt must be produced by reality.verifier"
            )
        if not receipt.verification_method:
            raise GovernanceEscalationError(
                "source receipt requires verification_method"
            )
        if receipt.promotion_status != "not_promoted":
            raise GovernanceEscalationError(
                "source verifier receipt must remain not_promoted"
            )
        source_payload = receipt.to_dict()
        source_sha = _sha256(source_payload)

        if self.ledger is not None:
            persisted = self.ledger.get_receipt(receipt.receipt_id)
            if persisted is None:
                raise GovernanceEscalationError(
                    "source verifier receipt is not present in the Mandala ledger"
                )
            if _sha256(persisted) != source_sha:
                raise GovernanceEscalationError(
                    "source verifier receipt does not match persisted evidence"
                )
        return source_sha

    @staticmethod
    def _trigger_verdicts(
        *,
        source_receipt: RealityReceipt,
        trigger_claim_ids: tuple[str, ...],
    ) -> tuple[dict[str, str], ...]:
        results: dict[str, str] = {}
        for item in source_receipt.claims_checked:
            claim_id = item.get("claim_id")
            verdict = item.get("verdict")
            if not isinstance(claim_id, str) or not claim_id.strip():
                raise GovernanceEscalationError(
                    "source verifier receipt contains invalid claim_id"
                )
            if not isinstance(verdict, str) or verdict not in _ALLOWED_VERDICTS:
                raise GovernanceEscalationError(
                    "source verifier receipt contains invalid verdict"
                )
            if claim_id in results:
                raise GovernanceEscalationError(
                    "source verifier receipt contains duplicate claim_id"
                )
            results[claim_id] = verdict

        selected: list[dict[str, str]] = []
        for claim_id in trigger_claim_ids:
            verdict = results.get(claim_id)
            if verdict is None:
                raise GovernanceEscalationError(
                    "trigger_claim_ids must reference verified claims"
                )
            selected.append({"claim_id": claim_id, "verdict": verdict})
        return tuple(selected)

    @staticmethod
    def _route(
        *,
        request: EscalationRequest,
        trigger_verdicts: tuple[dict[str, str], ...],
    ) -> tuple[str, str, MandalaStatus]:
        verdicts = tuple(item["verdict"] for item in trigger_verdicts)
        problematic = {
            "CONTRADICTED",
            "UNRESOLVED",
            "BLOCKED",
        }
        if not any(verdict in problematic for verdict in verdicts):
            return (
                "HELD",
                "escalation_requires_problematic_verifier_result",
                MandalaStatus.BLOCKED,
            )

        if request.disposition == "REVIEW":
            return (
                "ROUTED_FOR_REVIEW",
                "verifier_finding_routed_for_governance_review",
                MandalaStatus.ACCEPTED,
            )
        if request.disposition == "REVERIFY":
            return (
                "ROUTED_FOR_REVERIFICATION",
                "verifier_finding_routed_for_reverification",
                MandalaStatus.ACCEPTED,
            )

        if any(verdict != "CONTRADICTED" for verdict in verdicts):
            return (
                "HELD",
                "remediation_requires_only_contradicted_trigger_claims",
                MandalaStatus.BLOCKED,
            )
        return (
            "ROUTED_FOR_AUTHORIZATION",
            "remediation_candidate_requires_downstream_authority",
            MandalaStatus.ACCEPTED,
        )

    @staticmethod
    def _verifier_semantics(
        *,
        source_receipt: RealityReceipt,
        source_sha256: str,
    ) -> VerifierSemanticsReceipt:
        receipt = VerifierSemanticsReceipt(
            **_child_meta(
                source_receipt,
                status=MandalaStatus.ACCEPTED,
                produced_by="phios.verifier_semantics",
                parent_receipt_id=source_receipt.receipt_id,
            ),
            source_reality_receipt_id=source_receipt.receipt_id,
            source_reality_receipt_sha256=source_sha256,
            verifier_id=source_receipt.produced_by,
            verification_method=source_receipt.verification_method or "",
            source_status=source_receipt.status.value,
            verdict_summary=dict(sorted(source_receipt.verdict_summary.items())),
        )
        return _with_receipt_sha(receipt)

    @staticmethod
    def _escalation_receipt(
        *,
        source_receipt: RealityReceipt,
        source_sha256: str,
        semantics: VerifierSemanticsReceipt,
        request: EscalationRequest,
        trigger_verdicts: tuple[dict[str, str], ...],
        routing_status: str,
        reason: str,
        status: MandalaStatus,
    ) -> GovernanceEscalationReceipt:
        receipt = GovernanceEscalationReceipt(
            **_child_meta(
                source_receipt,
                status=status,
                produced_by="phios.governance_escalation",
                parent_receipt_id=semantics.receipt_id,
            ),
            source_reality_receipt_id=source_receipt.receipt_id,
            source_reality_receipt_sha256=source_sha256,
            verifier_semantics_receipt_sha256=semantics.receipt_sha256,
            request_id=request.request_id,
            disposition=request.disposition,
            routing_status=routing_status,
            reason=reason,
            target_ref=request.target_ref,
            trigger_claim_ids=request.trigger_claim_ids,
            trigger_verdicts=trigger_verdicts,
            candidate_capability_id=request.candidate_capability_id,
            candidate_payload_sha256=request.candidate_payload_sha256,
            requested_permissions=request.requested_permissions,
            requested_effects=request.requested_effects,
        )
        return _with_receipt_sha(receipt)


def _child_meta(
    source_receipt: RealityReceipt,
    *,
    status: MandalaStatus,
    produced_by: str,
    parent_receipt_id: str,
) -> dict[str, object]:
    return {
        "receipt_id": str(uuid.uuid4()),
        "packet_id": source_receipt.packet_id,
        "task_id": source_receipt.task_id,
        "status": status,
        "produced_by": produced_by,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "contract_version": source_receipt.contract_version,
        "parent_receipt_id": parent_receipt_id,
    }


def _with_receipt_sha(receipt):
    payload = receipt.to_dict()
    payload["receipt_sha256"] = ""
    return replace(receipt, receipt_sha256=_sha256(payload))
