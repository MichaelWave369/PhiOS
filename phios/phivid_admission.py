"""Policy-bound PHIVid evidence admission without ledger persistence.

A validated PHIVid envelope may be evaluated for *eligibility* to enter a later
ledger-admission workflow. This module never appends to the Reality Ledger and
never grants operational, action, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from phios.covenant.models import (
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_bool,
    require_sha256,
    require_text,
)
from phios.phivid_evidence import PHIVidEvidenceIntake

PHIVID_ADMISSION_POLICY_SCHEMA_VERSION = "phios.phivid_admission_policy.v0.1"
PHIVID_ADMISSION_RECEIPT_SCHEMA_VERSION = "phios.phivid_admission_receipt.v0.1"


class PHIVidAdmissionDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    HOLD = "HOLD"


class PHIVidAdmissionReason(StrEnum):
    POLICY_SATISFIED = "POLICY_SATISFIED"
    SOURCE_KIND_NOT_ALLOWED = "SOURCE_KIND_NOT_ALLOWED"
    EXACTNESS_NOT_ALLOWED = "EXACTNESS_NOT_ALLOWED"
    WARNING_NOT_ALLOWED = "WARNING_NOT_ALLOWED"
    PREVIOUS_ADMISSION_BINDING_PRESENT = "PREVIOUS_ADMISSION_BINDING_PRESENT"


def _require_timestamp(value: object, field: str) -> str:
    text = require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return text


def _canonical_strings(
    values: tuple[str, ...],
    field: str,
    *,
    maximum_items: int = 64,
    maximum_text: int = 128,
) -> tuple[str, ...]:
    if len(values) > maximum_items:
        raise ValueError(f"{field} exceeds {maximum_items} items")
    normalized = tuple(
        require_text(item, f"{field} item", maximum=maximum_text) for item in values
    )
    if tuple(sorted(set(normalized))) != normalized:
        raise ValueError(f"{field} must be sorted and unique")
    return normalized


@dataclass(frozen=True, slots=True)
class PHIVidAdmissionPolicy:
    profile_id: str
    allowed_source_kinds: tuple[str, ...]
    allowed_exactness_classes: tuple[str, ...]
    allowed_warnings: tuple[str, ...]
    require_unadmitted_refs: bool = True
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = PHIVID_ADMISSION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PHIVID_ADMISSION_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported PHIVid admission policy schema")
        require_text(self.profile_id, "profile_id", maximum=256)
        _canonical_strings(self.allowed_source_kinds, "allowed_source_kinds")
        _canonical_strings(
            self.allowed_exactness_classes,
            "allowed_exactness_classes",
        )
        _canonical_strings(
            self.allowed_warnings,
            "allowed_warnings",
            maximum_text=512,
        )
        require_bool(self.require_unadmitted_refs, "require_unadmitted_refs")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise ValueError("PHIVid admission policy cannot carry authority")

    @classmethod
    def strict_default(cls) -> "PHIVidAdmissionPolicy":
        return cls(
            profile_id="phivid-admission:strict-local-v0.1",
            allowed_source_kinds=(
                "phivid.video.render",
                "phivid.video.source",
            ),
            allowed_exactness_classes=("byte_exact",),
            allowed_warnings=("render_used_cpu_encoder",),
        )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "allowed_source_kinds": list(self.allowed_source_kinds),
            "allowed_exactness_classes": list(self.allowed_exactness_classes),
            "allowed_warnings": list(self.allowed_warnings),
            "require_unadmitted_refs": self.require_unadmitted_refs,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def profile_sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["profile_sha256"] = self.profile_sha256
        return payload


@dataclass(frozen=True, slots=True)
class PHIVidAdmissionReceipt:
    envelope_sha256: str
    source_receipt_sha256: str
    policy_profile_sha256: str
    plan_id: str
    output_evidence_ref: str
    decision: PHIVidAdmissionDecision
    reason: PHIVidAdmissionReason
    eligible_for_ledger_admission: bool
    evaluated_at: str
    ledger_write_performed: bool = False
    admission_effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = PHIVID_ADMISSION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PHIVID_ADMISSION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported PHIVid admission receipt schema")
        require_sha256(self.envelope_sha256, "envelope_sha256")
        require_sha256(self.source_receipt_sha256, "source_receipt_sha256")
        require_sha256(self.policy_profile_sha256, "policy_profile_sha256")
        require_text(self.plan_id, "plan_id", maximum=256)
        require_text(self.output_evidence_ref, "output_evidence_ref", maximum=256)
        _require_timestamp(self.evaluated_at, "evaluated_at")
        require_bool(
            self.eligible_for_ledger_admission,
            "eligible_for_ledger_admission",
        )
        if self.eligible_for_ledger_admission is not (
            self.decision is PHIVidAdmissionDecision.ELIGIBLE
        ):
            raise ValueError("eligibility must match admission decision")
        if (
            self.ledger_write_performed
            or self.admission_effect_performed
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise ValueError(
                "PHIVid admission receipt cannot record ledger writes, effects, or authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "envelope_sha256": self.envelope_sha256,
            "source_receipt_sha256": self.source_receipt_sha256,
            "policy_profile_sha256": self.policy_profile_sha256,
            "plan_id": self.plan_id,
            "output_evidence_ref": self.output_evidence_ref,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "eligible_for_ledger_admission": self.eligible_for_ledger_admission,
            "evaluated_at": self.evaluated_at,
            "ledger_write_performed": self.ledger_write_performed,
            "admission_effect_performed": self.admission_effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def admission_receipt_sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["admission_receipt_sha256"] = self.admission_receipt_sha256
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "PHIVidAdmissionReceipt":
        data = expect_mapping(value, "PHIVid admission receipt")
        expected = {
            "schema_version",
            "envelope_sha256",
            "source_receipt_sha256",
            "policy_profile_sha256",
            "plan_id",
            "output_evidence_ref",
            "decision",
            "reason",
            "eligible_for_ledger_admission",
            "evaluated_at",
            "ledger_write_performed",
            "admission_effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "admission_receipt_sha256",
        }
        expect_exact_keys(data, expected, "PHIVid admission receipt")
        claimed = require_sha256(
            data["admission_receipt_sha256"],
            "admission_receipt_sha256",
        )

        for field in (
            "eligible_for_ledger_admission",
            "ledger_write_performed",
            "admission_effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            require_bool(data[field], field)

        try:
            decision = PHIVidAdmissionDecision(
                require_text(data["decision"], "decision", maximum=32)
            )
            reason = PHIVidAdmissionReason(
                require_text(data["reason"], "reason", maximum=64)
            )
        except ValueError as exc:
            raise ValueError("unsupported PHIVid admission receipt enum") from exc

        receipt = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            envelope_sha256=require_sha256(
                data["envelope_sha256"],
                "envelope_sha256",
            ),
            source_receipt_sha256=require_sha256(
                data["source_receipt_sha256"],
                "source_receipt_sha256",
            ),
            policy_profile_sha256=require_sha256(
                data["policy_profile_sha256"],
                "policy_profile_sha256",
            ),
            plan_id=require_text(data["plan_id"], "plan_id", maximum=256),
            output_evidence_ref=require_text(
                data["output_evidence_ref"],
                "output_evidence_ref",
                maximum=256,
            ),
            decision=decision,
            reason=reason,
            eligible_for_ledger_admission=data["eligible_for_ledger_admission"],
            evaluated_at=_require_timestamp(data["evaluated_at"], "evaluated_at"),
            ledger_write_performed=data["ledger_write_performed"],
            admission_effect_performed=data["admission_effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )
        if receipt.admission_receipt_sha256 != claimed:
            raise ValueError("PHIVid admission receipt hash mismatch")
        return receipt


def evaluate_phivid_admission(
    intake: PHIVidEvidenceIntake,
    *,
    policy: PHIVidAdmissionPolicy,
    evaluated_at: str,
) -> PHIVidAdmissionReceipt:
    _require_timestamp(evaluated_at, "evaluated_at")

    decision = PHIVidAdmissionDecision.ELIGIBLE
    reason = PHIVidAdmissionReason.POLICY_SATISFIED

    allowed_kinds = set(policy.allowed_source_kinds)
    if any(ref.source_kind not in allowed_kinds for ref in intake.evidence_refs):
        decision = PHIVidAdmissionDecision.HOLD
        reason = PHIVidAdmissionReason.SOURCE_KIND_NOT_ALLOWED
    elif any(
        ref.exactness_class not in set(policy.allowed_exactness_classes)
        for ref in intake.evidence_refs
    ):
        decision = PHIVidAdmissionDecision.HOLD
        reason = PHIVidAdmissionReason.EXACTNESS_NOT_ALLOWED
    elif policy.require_unadmitted_refs and any(
        ref.admissibility_receipt_sha256 is not None
        for ref in intake.evidence_refs
    ):
        decision = PHIVidAdmissionDecision.HOLD
        reason = PHIVidAdmissionReason.PREVIOUS_ADMISSION_BINDING_PRESENT
    elif any(warning not in set(policy.allowed_warnings) for warning in intake.warnings):
        decision = PHIVidAdmissionDecision.HOLD
        reason = PHIVidAdmissionReason.WARNING_NOT_ALLOWED

    return PHIVidAdmissionReceipt(
        envelope_sha256=intake.envelope_sha256,
        source_receipt_sha256=intake.source_receipt_sha256,
        policy_profile_sha256=policy.profile_sha256,
        plan_id=intake.plan_id,
        output_evidence_ref=intake.output_evidence_ref,
        decision=decision,
        reason=reason,
        eligible_for_ledger_admission=(
            decision is PHIVidAdmissionDecision.ELIGIBLE
        ),
        evaluated_at=evaluated_at,
    )
