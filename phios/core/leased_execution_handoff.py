"""Runtime ActionLease gate for the existing governed execution handoff.

This layer accepts externally verified lease-authority evidence, revalidates one
ActionLease against current authority state and runtime binding scope, reserves
the single-use lease atomically, then delegates all existing permission/effect/
executor checks to GovernedExecutionHandoff.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from phios.action_lease import (
    ActionLease,
    ActionLeaseContractError,
    ActionLeaseEvaluation,
    evaluate_action_lease,
)
from phios.core.governed_action_binding import PlanActionBinding
from phios.core.governed_execution_handoff import (
    ExecutionHandoffReceipt,
    GovernedExecutionHandoff,
)
from phios.core.governed_plan_adoption import PlanState
from phios.spine.runtime import PhiOSSpine

LEASE_VERIFICATION_EVIDENCE_SCHEMA_VERSION = (
    "phios.lease_verification_evidence.v0.1"
)
LEASED_EXECUTION_HANDOFF_RECEIPT_SCHEMA_VERSION = (
    "phios.leased_execution_handoff_receipt.v0.1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LeasedExecutionHandoffError(ValueError):
    """Raised when leased execution inputs cannot be verified safely."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise LeasedExecutionHandoffError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise LeasedExecutionHandoffError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise LeasedExecutionHandoffError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise LeasedExecutionHandoffError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


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
        raise LeasedExecutionHandoffError(
            "leased execution receipt must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LeaseVerificationEvidence:
    """Caller-supplied evidence that the lease issuer decision was verified.

    This record does not perform cryptographic verification itself. It binds the
    result of an external configured verifier so the runtime can refuse leases
    whose verified issuer/authorization receipt does not match the lease.
    """

    lease_sha256: str
    issuer_id: str
    authorization_receipt_sha256: str
    verifier_id: str
    verification_receipt_sha256: str
    accepted: bool
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = LEASE_VERIFICATION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LEASE_VERIFICATION_EVIDENCE_SCHEMA_VERSION:
            raise LeasedExecutionHandoffError(
                "unsupported lease verification evidence schema"
            )
        _require_sha256(self.lease_sha256, "lease_sha256")
        _require_text(self.issuer_id, "issuer_id")
        _require_sha256(
            self.authorization_receipt_sha256,
            "authorization_receipt_sha256",
        )
        _require_text(self.verifier_id, "verifier_id")
        _require_sha256(
            self.verification_receipt_sha256,
            "verification_receipt_sha256",
        )
        if not isinstance(self.accepted, bool):
            raise LeasedExecutionHandoffError(
                "accepted must be Boolean"
            )
        if (
            self.action_authority is not False
            or self.execution_authority is not False
            or self.effect_performed is not False
        ):
            raise LeasedExecutionHandoffError(
                "lease verification evidence cannot carry authority or effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lease_sha256": self.lease_sha256,
            "issuer_id": self.issuer_id,
            "authorization_receipt_sha256": (
                self.authorization_receipt_sha256
            ),
            "verifier_id": self.verifier_id,
            "verification_receipt_sha256": (
                self.verification_receipt_sha256
            ),
            "accepted": self.accepted,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }

    @property
    def verification_evidence_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["verification_evidence_sha256"] = (
            self.verification_evidence_sha256
        )
        return payload


@dataclass(frozen=True, slots=True)
class LeasedExecutionHandoffReceipt:
    """Receipt for ActionLease gating plus the existing governed handoff."""

    status: str
    reason: str
    action_lease_sha256: str
    authority_epoch_sha256: str
    verification_evidence_sha256: str
    lease_evaluation: dict[str, object] | None
    lease_claimed: bool
    lease_consumed: bool
    replay_blocked: bool
    inner_handoff: dict[str, object] | None
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = LEASED_EXECUTION_HANDOFF_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "action_lease_sha256": self.action_lease_sha256,
            "authority_epoch_sha256": self.authority_epoch_sha256,
            "verification_evidence_sha256": (
                self.verification_evidence_sha256
            ),
            "lease_evaluation": self.lease_evaluation,
            "lease_claimed": self.lease_claimed,
            "lease_consumed": self.lease_consumed,
            "replay_blocked": self.replay_blocked,
            "inner_handoff": self.inner_handoff,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


class GovernedLeasedExecutionHandoff:
    """Gate one existing governed execution with one verified ActionLease."""

    def __init__(self) -> None:
        self._handoff = GovernedExecutionHandoff()

    def execute(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        spine: PhiOSSpine,
        lease: ActionLease,
        verification: LeaseVerificationEvidence,
        current_authority_epoch_sha256: str,
        checked_at: str,
    ) -> LeasedExecutionHandoffReceipt:
        lease_sha = lease.action_lease_sha256
        current_epoch = _require_sha256(
            current_authority_epoch_sha256,
            "current_authority_epoch_sha256",
        )

        verification_reason = self._verification_reason(
            lease=lease,
            verification=verification,
        )
        if verification_reason is not None:
            return self._held(
                lease=lease,
                verification=verification,
                current_epoch=current_epoch,
                reason=verification_reason,
                evaluation=None,
            )

        scope_reason = self._scope_reason(
            lease=lease,
            binding=binding,
        )
        if scope_reason is not None:
            return self._held(
                lease=lease,
                verification=verification,
                current_epoch=current_epoch,
                reason=scope_reason,
                evaluation=None,
            )

        try:
            consumed = spine.ledger.has_consumed_action_lease(lease_sha)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise LeasedExecutionHandoffError(
                "ActionLease consumption state could not be verified safely"
            ) from exc

        try:
            evaluation = evaluate_action_lease(
                lease=lease,
                checked_at=checked_at,
                current_authority_epoch_sha256=current_epoch,
                uses_consumed=1 if consumed else 0,
            )
        except ActionLeaseContractError as exc:
            raise LeasedExecutionHandoffError(str(exc)) from exc

        if not evaluation.usable:
            return self._held(
                lease=lease,
                verification=verification,
                current_epoch=current_epoch,
                reason=evaluation.reason,
                evaluation=evaluation,
                replay_blocked=evaluation.reason == "lease_consumed",
            )

        try:
            claimed = spine.ledger.claim_action_lease(lease_sha)
        except (OSError, ValueError) as exc:
            raise LeasedExecutionHandoffError(
                "ActionLease could not be claimed safely"
            ) from exc
        if not claimed:
            return self._held(
                lease=lease,
                verification=verification,
                current_epoch=current_epoch,
                reason="lease_execution_claim_unavailable",
                evaluation=evaluation,
                replay_blocked=True,
            )

        inner = self._handoff.execute(
            plan=plan,
            binding=binding,
            payload=payload,
            spine=spine,
            action_lease_sha256=lease_sha,
            authority_epoch_sha256=lease.authority_epoch_sha256,
            authorization_receipt_sha256=(
                lease.authorization_receipt_sha256
            ),
            lease_verification_sha256=(
                verification.verification_evidence_sha256
            ),
        )

        lease_consumed = inner.binding_consumed
        if not lease_consumed:
            spine.ledger.release_action_lease_claim(lease_sha)

        return LeasedExecutionHandoffReceipt(
            status=inner.status,
            reason=inner.reason,
            action_lease_sha256=lease_sha,
            authority_epoch_sha256=current_epoch,
            verification_evidence_sha256=(
                verification.verification_evidence_sha256
            ),
            lease_evaluation=evaluation.to_dict(),
            lease_claimed=True,
            lease_consumed=lease_consumed,
            replay_blocked=inner.replay_blocked,
            inner_handoff=inner.to_dict(),
        )

    @staticmethod
    def _verification_reason(
        *,
        lease: ActionLease,
        verification: LeaseVerificationEvidence,
    ) -> str | None:
        if not verification.accepted:
            return "lease_authorization_not_verified"
        if verification.lease_sha256 != lease.action_lease_sha256:
            return "lease_verification_scope_mismatch"
        if verification.issuer_id != lease.issuer_id:
            return "lease_issuer_verification_mismatch"
        if (
            verification.authorization_receipt_sha256
            != lease.authorization_receipt_sha256
        ):
            return "lease_authorization_receipt_verification_mismatch"
        return None

    @staticmethod
    def _scope_reason(
        *,
        lease: ActionLease,
        binding: PlanActionBinding,
    ) -> str | None:
        if lease.capability_id != binding.capability_id:
            return "lease_capability_scope_mismatch"
        if lease.capability_version != binding.capability_version:
            return "lease_capability_version_scope_mismatch"
        if lease.payload_sha256 != binding.payload_sha256:
            return "lease_payload_scope_mismatch"
        if lease.effects_declared != binding.effects_declared:
            return "lease_effect_scope_mismatch"
        if lease.permissions_authorized != binding.permissions_requested:
            return "lease_permission_scope_mismatch"
        return None

    @staticmethod
    def _held(
        *,
        lease: ActionLease,
        verification: LeaseVerificationEvidence,
        current_epoch: str,
        reason: str,
        evaluation: ActionLeaseEvaluation | None,
        replay_blocked: bool = False,
    ) -> LeasedExecutionHandoffReceipt:
        return LeasedExecutionHandoffReceipt(
            status="HELD",
            reason=reason,
            action_lease_sha256=lease.action_lease_sha256,
            authority_epoch_sha256=current_epoch,
            verification_evidence_sha256=(
                verification.verification_evidence_sha256
            ),
            lease_evaluation=(
                evaluation.to_dict() if evaluation is not None else None
            ),
            lease_claimed=False,
            lease_consumed=False,
            replay_blocked=replay_blocked,
            inner_handoff=None,
        )
