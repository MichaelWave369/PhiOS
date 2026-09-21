"""Deterministic Covenant transition receipts for CR-01."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import (
    BoundaryTransitionRequest,
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_bool,
    require_sha256,
    require_string_tuple,
    require_text,
)
from .zones import TrustZone, require_actor_zone, require_transition

BOUNDARY_TRANSITION_RECEIPT_SCHEMA_VERSION = "phios.boundary_transition_receipt.v0.1"


class TransitionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    HELD = "HELD"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BoundaryTransitionReceipt:
    """Record one evaluated boundary crossing without carrying authority."""

    status: TransitionStatus
    source_zone: TrustZone
    target_zone: TrustZone
    subject_seal_sha256: str
    boundary_transition_request_sha256: str
    evidence_refs: tuple[str, ...]
    requirements_satisfied: bool
    reason: str
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = BOUNDARY_TRANSITION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BOUNDARY_TRANSITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported boundary transition receipt schema: {self.schema_version}"
            )
        if not isinstance(self.status, TransitionStatus):
            raise ValueError("status must be a supported TransitionStatus")
        require_actor_zone(self.source_zone)
        require_actor_zone(self.target_zone)
        require_transition(self.source_zone, self.target_zone)
        require_sha256(self.subject_seal_sha256, "subject_seal_sha256")
        require_sha256(
            self.boundary_transition_request_sha256,
            "boundary_transition_request_sha256",
        )
        if tuple(sorted(self.evidence_refs)) != self.evidence_refs:
            raise ValueError("evidence_refs must be sorted")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must not contain duplicates")
        if len(self.evidence_refs) > 64:
            raise ValueError("evidence_refs exceeds 64 items")
        for item in self.evidence_refs:
            require_text(item, "evidence reference", maximum=256)
        require_bool(self.requirements_satisfied, "requirements_satisfied")
        require_text(self.reason, "reason", maximum=512)
        if self.status is TransitionStatus.ACCEPTED and not self.requirements_satisfied:
            raise ValueError("ACCEPTED transition requires requirements_satisfied=true")
        if self.status in {TransitionStatus.HELD, TransitionStatus.BLOCKED} and (
            self.requirements_satisfied
        ):
            raise ValueError(
                f"{self.status.value} transition requires requirements_satisfied=false"
            )
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError("boundary transition receipt cannot carry authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "source_zone": self.source_zone.value,
            "target_zone": self.target_zone.value,
            "subject_seal_sha256": self.subject_seal_sha256,
            "boundary_transition_request_sha256": (
                self.boundary_transition_request_sha256
            ),
            "evidence_refs": list(self.evidence_refs),
            "requirements_satisfied": self.requirements_satisfied,
            "reason": self.reason,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BoundaryTransitionReceipt:
        data = expect_mapping(value, "boundary transition receipt")
        expected = {
            "schema_version",
            "status",
            "source_zone",
            "target_zone",
            "subject_seal_sha256",
            "boundary_transition_request_sha256",
            "evidence_refs",
            "requirements_satisfied",
            "reason",
            "action_authority",
            "execution_authority",
            "receipt_sha256",
        }
        expect_exact_keys(data, expected, "boundary transition receipt")
        try:
            status = TransitionStatus(
                require_text(data["status"], "status", maximum=16)
            )
        except ValueError as exc:
            raise ValueError(f"Unsupported transition status: {data['status']}") from exc
        try:
            source_zone = TrustZone(
                require_text(data["source_zone"], "source_zone", maximum=32)
            )
            target_zone = TrustZone(
                require_text(data["target_zone"], "target_zone", maximum=32)
            )
        except ValueError as exc:
            raise ValueError("boundary transition receipt contains unsupported zone") from exc
        receipt = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            status=status,
            source_zone=source_zone,
            target_zone=target_zone,
            subject_seal_sha256=require_sha256(
                data["subject_seal_sha256"],
                "subject_seal_sha256",
            ),
            boundary_transition_request_sha256=require_sha256(
                data["boundary_transition_request_sha256"],
                "boundary_transition_request_sha256",
            ),
            evidence_refs=require_string_tuple(data["evidence_refs"], "evidence_refs"),
            requirements_satisfied=require_bool(
                data["requirements_satisfied"],
                "requirements_satisfied",
            ),
            reason=require_text(data["reason"], "reason", maximum=512),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "boundary transition receipt digest does not match canonical receipt"
            )
        return receipt


def transition_receipt(
    request: BoundaryTransitionRequest,
    *,
    status: TransitionStatus,
    requirements_satisfied: bool,
    reason: str,
) -> BoundaryTransitionReceipt:
    """Create a deterministic receipt from one already-valid transition request."""

    return BoundaryTransitionReceipt(
        status=status,
        source_zone=request.source_zone,
        target_zone=request.target_zone,
        subject_seal_sha256=request.subject_seal_sha256,
        boundary_transition_request_sha256=request.sha256(),
        evidence_refs=request.evidence_refs,
        requirements_satisfied=requirements_satisfied,
        reason=reason,
        action_authority=False,
        execution_authority=False,
    )
