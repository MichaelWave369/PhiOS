"""Temporal context-admissibility for governed PhiOS memory.

Retention and retrievability are deliberately distinct from present-tense contextual
admissibility. A canonical memory record can remain stored and auditable after it is too
old to enter ordinary reasoning without fresh reconsolidating evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .models import MemoryRecord
from .validation import require_nonempty, require_utc_timestamp, sha256_json

EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION = "phios.memory.evidence_horizon_policy.v0.1"
EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION = "phios.memory.evidence_horizon_receipt.v0.1"
REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION = (
    "phios.memory.reactivation_window_receipt.v0.1"
)


class EvidenceHorizonError(ValueError):
    """Raised when an evidence-horizon contract cannot be evaluated safely."""


@dataclass(frozen=True, kw_only=True)
class EvidenceHorizonPolicy:
    policy_id: str
    active_window_seconds: float
    reactivation_window_seconds: float
    fresh_evidence_window_seconds: float
    policy_version: str = "0.1"

    def __post_init__(self) -> None:
        require_nonempty(self.policy_id, "policy_id")
        require_nonempty(self.policy_version, "policy_version")
        active = _positive(self.active_window_seconds, "active_window_seconds")
        reactivation = _positive(
            self.reactivation_window_seconds,
            "reactivation_window_seconds",
        )
        fresh = _positive(
            self.fresh_evidence_window_seconds,
            "fresh_evidence_window_seconds",
        )
        if reactivation <= active:
            raise EvidenceHorizonError(
                "reactivation_window_seconds must exceed active_window_seconds"
            )
        if fresh > active:
            raise EvidenceHorizonError(
                "fresh_evidence_window_seconds cannot exceed active_window_seconds"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "active_window_seconds": self.active_window_seconds,
            "reactivation_window_seconds": self.reactivation_window_seconds,
            "fresh_evidence_window_seconds": self.fresh_evidence_window_seconds,
        }

    @property
    def policy_sha256(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True, kw_only=True)
class ReactivationWindowReceipt:
    schema: str
    status: str
    reason: str
    record_id: str
    revision: int
    record_sha256: str
    reactivation_record_id: str
    reactivation_revision: int
    reactivation_record_sha256: str
    reactivation_record_ref: str
    evaluated_at_utc: str
    evidence_age_seconds: float
    policy_sha256: str
    context_reactivated: bool
    canonical_record_mutated: bool
    retention_mutated: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "record_id": self.record_id,
            "revision": self.revision,
            "record_sha256": self.record_sha256,
            "reactivation_record_id": self.reactivation_record_id,
            "reactivation_revision": self.reactivation_revision,
            "reactivation_record_sha256": self.reactivation_record_sha256,
            "reactivation_record_ref": self.reactivation_record_ref,
            "evaluated_at_utc": self.evaluated_at_utc,
            "evidence_age_seconds": self.evidence_age_seconds,
            "policy_sha256": self.policy_sha256,
            "context_reactivated": self.context_reactivated,
            "canonical_record_mutated": self.canonical_record_mutated,
            "retention_mutated": self.retention_mutated,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class EvidenceHorizonReceipt:
    schema: str
    status: str
    reason: str
    record_id: str
    revision: int
    record_sha256: str
    record_created_at_utc: str
    evaluated_at_utc: str
    record_age_seconds: float
    policy_id: str
    policy_sha256: str
    active_window_seconds: float
    reactivation_window_seconds: float
    reactivation_required: bool
    reactivation_receipt_sha256: str | None
    context_admissible: bool
    retrievable_record_unchanged: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "record_id": self.record_id,
            "revision": self.revision,
            "record_sha256": self.record_sha256,
            "record_created_at_utc": self.record_created_at_utc,
            "evaluated_at_utc": self.evaluated_at_utc,
            "record_age_seconds": self.record_age_seconds,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "active_window_seconds": self.active_window_seconds,
            "reactivation_window_seconds": self.reactivation_window_seconds,
            "reactivation_required": self.reactivation_required,
            "reactivation_receipt_sha256": self.reactivation_receipt_sha256,
            "context_admissible": self.context_admissible,
            "retrievable_record_unchanged": self.retrievable_record_unchanged,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class EvidenceHorizonEvaluation:
    horizon_receipt: EvidenceHorizonReceipt
    reactivation_receipt: ReactivationWindowReceipt | None = None

    @property
    def context_admissible(self) -> bool:
        return self.horizon_receipt.context_admissible


def memory_record_ref(record: MemoryRecord) -> str:
    return (
        f"memory:{record.record_id}:{record.revision}:"
        f"{record.record_sha256}"
    )


class ReconsolidationGate:
    """Use one newer canonical memory record as bounded reactivation evidence."""

    def __init__(self, policy: EvidenceHorizonPolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        record: MemoryRecord,
        reactivation_record: MemoryRecord,
        *,
        evaluated_at_utc: str,
    ) -> ReactivationWindowReceipt:
        observed = _time(evaluated_at_utc, "evaluated_at_utc")
        original_created = _time(record.created_at, "record.created_at")
        evidence_created = _time(
            reactivation_record.created_at,
            "reactivation_record.created_at",
        )
        if original_created > observed:
            raise EvidenceHorizonError("memory record cannot be created in the future")
        if evidence_created > observed:
            raise EvidenceHorizonError(
                "reactivation evidence cannot be created in the future"
            )

        age = (observed - original_created).total_seconds()
        if age <= self.policy.active_window_seconds:
            return self._receipt(
                status="HELD",
                reason="reactivation_not_required",
                record=record,
                evidence=reactivation_record,
                evaluated_at_utc=observed.isoformat(),
                evidence_age_seconds=(observed - evidence_created).total_seconds(),
                accepted=False,
            )
        if age > self.policy.reactivation_window_seconds:
            return self._receipt(
                status="HELD",
                reason="record_outside_reactivation_window",
                record=record,
                evidence=reactivation_record,
                evaluated_at_utc=observed.isoformat(),
                evidence_age_seconds=(observed - evidence_created).total_seconds(),
                accepted=False,
            )

        evidence_age = (observed - evidence_created).total_seconds()
        reason = "fresh_linked_evidence_accepted"
        accepted = True

        if reactivation_record.record_id == record.record_id:
            accepted = False
            reason = "self_reactivation_forbidden"
        elif evidence_created <= original_created:
            accepted = False
            reason = "reactivation_evidence_not_newer"
        elif evidence_age > self.policy.fresh_evidence_window_seconds:
            accepted = False
            reason = "reactivation_evidence_not_fresh"
        elif (
            reactivation_record.scope_id != record.scope_id
            or reactivation_record.classification != record.classification
        ):
            accepted = False
            reason = "reactivation_evidence_policy_domain_mismatch"
        else:
            target_ref = memory_record_ref(record)
            contradiction_refs = set(reactivation_record.contradicts)
            if record.record_id in contradiction_refs or target_ref in contradiction_refs:
                accepted = False
                reason = "reactivation_evidence_contradicts_record"
            elif target_ref not in set(reactivation_record.provenance_refs):
                accepted = False
                reason = "reactivation_evidence_missing_exact_record_ref"

        return self._receipt(
            status="ACCEPTED" if accepted else "HELD",
            reason=reason,
            record=record,
            evidence=reactivation_record,
            evaluated_at_utc=observed.isoformat(),
            evidence_age_seconds=evidence_age,
            accepted=accepted,
        )

    def _receipt(
        self,
        *,
        status: str,
        reason: str,
        record: MemoryRecord,
        evidence: MemoryRecord,
        evaluated_at_utc: str,
        evidence_age_seconds: float,
        accepted: bool,
    ) -> ReactivationWindowReceipt:
        payload: dict[str, object] = {
            "schema": REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION,
            "status": status,
            "reason": reason,
            "record_id": record.record_id,
            "revision": record.revision,
            "record_sha256": record.record_sha256,
            "reactivation_record_id": evidence.record_id,
            "reactivation_revision": evidence.revision,
            "reactivation_record_sha256": evidence.record_sha256,
            "reactivation_record_ref": memory_record_ref(record),
            "evaluated_at_utc": evaluated_at_utc,
            "evidence_age_seconds": _stable(evidence_age_seconds),
            "policy_sha256": self.policy.policy_sha256,
            "context_reactivated": accepted,
            "canonical_record_mutated": False,
            "retention_mutated": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReactivationWindowReceipt(
            schema=REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            record_id=record.record_id,
            revision=record.revision,
            record_sha256=record.record_sha256,
            reactivation_record_id=evidence.record_id,
            reactivation_revision=evidence.revision,
            reactivation_record_sha256=evidence.record_sha256,
            reactivation_record_ref=memory_record_ref(record),
            evaluated_at_utc=evaluated_at_utc,
            evidence_age_seconds=_stable(evidence_age_seconds),
            policy_sha256=self.policy.policy_sha256,
            context_reactivated=accepted,
            canonical_record_mutated=False,
            retention_mutated=False,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=sha256_json(payload),
        )


class MemoryEvidenceHorizon:
    """Separate canonical retrievability from present-context admissibility."""

    def __init__(self, policy: EvidenceHorizonPolicy) -> None:
        self.policy = policy
        self.reconsolidation_gate = ReconsolidationGate(policy)

    def evaluate(
        self,
        record: MemoryRecord,
        *,
        evaluated_at_utc: str,
        reactivation_record: MemoryRecord | None = None,
    ) -> EvidenceHorizonEvaluation:
        observed = _time(evaluated_at_utc, "evaluated_at_utc")
        created = _time(record.created_at, "record.created_at")
        if created > observed:
            raise EvidenceHorizonError("memory record cannot be created in the future")

        age = (observed - created).total_seconds()
        reactivation: ReactivationWindowReceipt | None = None

        if age <= self.policy.active_window_seconds:
            status = "ACTIVE"
            reason = "record_inside_active_context_window"
            admissible = True
            required = False
        elif age <= self.policy.reactivation_window_seconds:
            required = True
            if reactivation_record is None:
                status = "REACTIVATION_REQUIRED"
                reason = "fresh_linked_evidence_required"
                admissible = False
            else:
                reactivation = self.reconsolidation_gate.evaluate(
                    record,
                    reactivation_record,
                    evaluated_at_utc=observed.isoformat(),
                )
                if reactivation.context_reactivated:
                    status = "REACTIVATED"
                    reason = "fresh_linked_evidence_accepted"
                    admissible = True
                else:
                    status = "REACTIVATION_HELD"
                    reason = reactivation.reason
                    admissible = False
        else:
            status = "OUTSIDE_HORIZON"
            reason = "record_age_exceeds_reactivation_window"
            admissible = False
            required = False

        payload: dict[str, object] = {
            "schema": EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION,
            "status": status,
            "reason": reason,
            "record_id": record.record_id,
            "revision": record.revision,
            "record_sha256": record.record_sha256,
            "record_created_at_utc": created.isoformat(),
            "evaluated_at_utc": observed.isoformat(),
            "record_age_seconds": _stable(age),
            "policy_id": self.policy.policy_id,
            "policy_sha256": self.policy.policy_sha256,
            "active_window_seconds": self.policy.active_window_seconds,
            "reactivation_window_seconds": self.policy.reactivation_window_seconds,
            "reactivation_required": required,
            "reactivation_receipt_sha256": (
                reactivation.receipt_sha256 if reactivation is not None else None
            ),
            "context_admissible": admissible,
            "retrievable_record_unchanged": True,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        horizon = EvidenceHorizonReceipt(
            schema=EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            record_id=record.record_id,
            revision=record.revision,
            record_sha256=record.record_sha256,
            record_created_at_utc=created.isoformat(),
            evaluated_at_utc=observed.isoformat(),
            record_age_seconds=_stable(age),
            policy_id=self.policy.policy_id,
            policy_sha256=self.policy.policy_sha256,
            active_window_seconds=self.policy.active_window_seconds,
            reactivation_window_seconds=self.policy.reactivation_window_seconds,
            reactivation_required=required,
            reactivation_receipt_sha256=(
                reactivation.receipt_sha256 if reactivation is not None else None
            ),
            context_admissible=admissible,
            retrievable_record_unchanged=True,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=sha256_json(payload),
        )
        return EvidenceHorizonEvaluation(
            horizon_receipt=horizon,
            reactivation_receipt=reactivation,
        )


def _time(value: str, label: str) -> datetime:
    normalized = require_utc_timestamp(value, label)
    return datetime.fromisoformat(normalized).astimezone(UTC)


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceHorizonError(f"{label} must be numeric")
    number = float(value)
    if number <= 0.0 or number != number or number in (float("inf"), float("-inf")):
        raise EvidenceHorizonError(f"{label} must be finite and > 0")
    return number


def _stable(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION",
    "EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION",
    "REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION",
    "EvidenceHorizonError",
    "EvidenceHorizonPolicy",
    "EvidenceHorizonReceipt",
    "EvidenceHorizonEvaluation",
    "MemoryEvidenceHorizon",
    "ReactivationWindowReceipt",
    "ReconsolidationGate",
    "memory_record_ref",
]
