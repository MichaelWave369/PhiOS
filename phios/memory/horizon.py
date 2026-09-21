from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .models import MemoryRecord

EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION = "phios.evidence_horizon_policy.v0.1"
EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION = "phios.evidence_horizon_receipt.v0.1"
REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION = "phios.reactivation_window_receipt.v0.1"
RECONSOLIDATION_GATE_SCHEMA_VERSION = "phios.reconsolidation_gate.v0.1"


class EvidenceHorizonError(ValueError):
    """Raised when memory temporal-admissibility evidence is invalid."""


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
        raise EvidenceHorizonError(
            "evidence-horizon payload must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceHorizonError(f"{label} must be non-empty")
    return value.strip()


def _require_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceHorizonError(f"{label} must be numeric")
    result = float(value)
    if result < 0.0 or result == float("inf") or result != result:
        raise EvidenceHorizonError(f"{label} must be finite and non-negative")
    return round(result, 12)


def _parse_time(value: str, label: str) -> datetime:
    raw = _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceHorizonError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceHorizonError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _labels(values: Iterable[str], label: str) -> tuple[str, ...]:
    return tuple(sorted({_require_text(value, label) for value in values}))


@dataclass(frozen=True, slots=True)
class EvidenceHorizonPolicy:
    policy_id: str
    version: str
    max_context_age_seconds: float
    reactivation_window_seconds: float

    def normalized(self) -> "EvidenceHorizonPolicy":
        policy_id = _require_text(self.policy_id, "policy_id")
        version = _require_text(self.version, "version")
        max_age = _require_nonnegative(
            self.max_context_age_seconds,
            "max_context_age_seconds",
        )
        if max_age <= 0.0:
            raise EvidenceHorizonError("max_context_age_seconds must be > 0")
        return EvidenceHorizonPolicy(
            policy_id=policy_id,
            version=version,
            max_context_age_seconds=max_age,
            reactivation_window_seconds=_require_nonnegative(
                self.reactivation_window_seconds,
                "reactivation_window_seconds",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "version": self.version,
            "max_context_age_seconds": self.max_context_age_seconds,
            "reactivation_window_seconds": self.reactivation_window_seconds,
        }

    @property
    def policy_sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class EvidenceHorizonReceipt:
    schema: str
    receipt_id: str
    policy_id: str
    policy_sha256: str
    record_id: str
    revision: int
    record_sha256: str
    created_at_utc: str
    evaluated_at_utc: str
    age_seconds: float
    max_context_age_seconds: float
    status: str
    readable_as_context: bool
    reactivation_required: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "record_id": self.record_id,
            "revision": self.revision,
            "record_sha256": self.record_sha256,
            "created_at_utc": self.created_at_utc,
            "evaluated_at_utc": self.evaluated_at_utc,
            "age_seconds": self.age_seconds,
            "max_context_age_seconds": self.max_context_age_seconds,
            "status": self.status,
            "readable_as_context": self.readable_as_context,
            "reactivation_required": self.reactivation_required,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReactivationWindowReceipt:
    schema: str
    receipt_id: str
    policy_id: str
    policy_sha256: str
    record_id: str
    revision: int
    record_sha256: str
    evaluated_at_utc: str
    window_opens_at_utc: str
    window_closes_at_utc: str
    within_window: bool
    reactivation_authorized: bool
    reactivation_completed: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "record_id": self.record_id,
            "revision": self.revision,
            "record_sha256": self.record_sha256,
            "evaluated_at_utc": self.evaluated_at_utc,
            "window_opens_at_utc": self.window_opens_at_utc,
            "window_closes_at_utc": self.window_closes_at_utc,
            "within_window": self.within_window,
            "reactivation_authorized": self.reactivation_authorized,
            "reactivation_completed": self.reactivation_completed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class EvidenceHorizonEvaluation:
    horizon: EvidenceHorizonReceipt
    reactivation: ReactivationWindowReceipt | None = None


@dataclass(frozen=True, slots=True)
class ReconsolidationGateDecision:
    schema: str
    status: str
    reason: str
    previous_record_sha256: str
    candidate_record_sha256: str
    fresh_provenance_refs: tuple[str, ...]
    promotion_status: str
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    decision_sha256: str

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPTED"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "previous_record_sha256": self.previous_record_sha256,
            "candidate_record_sha256": self.candidate_record_sha256,
            "fresh_provenance_refs": list(self.fresh_provenance_refs),
            "promotion_status": self.promotion_status,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "decision_sha256": self.decision_sha256,
        }


class EvidenceHorizonController:
    """Compute memory context admissibility without deleting canonical history."""

    def __init__(self, policy: EvidenceHorizonPolicy) -> None:
        self._policy = policy.normalized()

    @property
    def policy(self) -> EvidenceHorizonPolicy:
        return self._policy

    def evaluate(
        self,
        record: "MemoryRecord",
        *,
        evaluated_at_utc: str,
    ) -> EvidenceHorizonEvaluation:
        created = _parse_time(record.created_at, "record.created_at")
        evaluated = _parse_time(evaluated_at_utc, "evaluated_at_utc")
        if evaluated < created:
            raise EvidenceHorizonError(
                "evaluated_at_utc cannot precede record.created_at"
            )
        age = round((evaluated - created).total_seconds(), 12)
        max_age = self._policy.max_context_age_seconds
        window = self._policy.reactivation_window_seconds

        if age <= max_age:
            status = "ADMISSIBLE"
            readable = True
            reactivation_required = False
            reactivation = None
        elif age <= max_age + window:
            status = "REACTIVATION_REQUIRED"
            readable = False
            reactivation_required = True
            reactivation = self._reactivation_receipt(
                record,
                evaluated_at=evaluated,
                within_window=True,
            )
        else:
            status = "OUTSIDE_HORIZON"
            readable = False
            reactivation_required = True
            reactivation = self._reactivation_receipt(
                record,
                evaluated_at=evaluated,
                within_window=False,
            )

        payload: dict[str, object] = {
            "schema": EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION,
            "receipt_id": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    (
                        "phios.evidence-horizon:"
                        f"{record.record_sha256}:{evaluated.isoformat()}:"
                        f"{self._policy.policy_sha256}"
                    ),
                )
            ),
            "policy_id": self._policy.policy_id,
            "policy_sha256": self._policy.policy_sha256,
            "record_id": record.record_id,
            "revision": record.revision,
            "record_sha256": record.record_sha256,
            "created_at_utc": created.isoformat(),
            "evaluated_at_utc": evaluated.isoformat(),
            "age_seconds": age,
            "max_context_age_seconds": max_age,
            "status": status,
            "readable_as_context": readable,
            "reactivation_required": reactivation_required,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        receipt = EvidenceHorizonReceipt(
            **payload,
            receipt_sha256=_sha256(payload),
        )
        return EvidenceHorizonEvaluation(
            horizon=receipt,
            reactivation=reactivation,
        )

    def _reactivation_receipt(
        self,
        record: "MemoryRecord",
        *,
        evaluated_at: datetime,
        within_window: bool,
    ) -> ReactivationWindowReceipt:
        created = _parse_time(record.created_at, "record.created_at")
        opens = created.timestamp() + self._policy.max_context_age_seconds
        closes = opens + self._policy.reactivation_window_seconds
        opens_at = datetime.fromtimestamp(opens, tz=UTC).isoformat()
        closes_at = datetime.fromtimestamp(closes, tz=UTC).isoformat()
        payload: dict[str, object] = {
            "schema": REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION,
            "receipt_id": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    (
                        "phios.reactivation-window:"
                        f"{record.record_sha256}:{evaluated_at.isoformat()}:"
                        f"{self._policy.policy_sha256}"
                    ),
                )
            ),
            "policy_id": self._policy.policy_id,
            "policy_sha256": self._policy.policy_sha256,
            "record_id": record.record_id,
            "revision": record.revision,
            "record_sha256": record.record_sha256,
            "evaluated_at_utc": evaluated_at.isoformat(),
            "window_opens_at_utc": opens_at,
            "window_closes_at_utc": closes_at,
            "within_window": within_window,
            "reactivation_authorized": False,
            "reactivation_completed": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReactivationWindowReceipt(
            **payload,
            receipt_sha256=_sha256(payload),
        )


class ReconsolidationGate:
    """Require fresh provenance before a stale canonical head is revised."""

    def evaluate(
        self,
        *,
        previous: "MemoryRecord",
        candidate: "MemoryRecord",
        evidence_refs: tuple[str, ...],
    ) -> ReconsolidationGateDecision:
        fresh_refs = _labels(evidence_refs, "reconsolidation_evidence_ref")
        reason = "reconsolidation_requirements_satisfied"
        status = "ACCEPTED"

        if candidate.record_id != previous.record_id:
            status = "BLOCKED"
            reason = "record_identity_mismatch"
        elif candidate.revision != previous.revision + 1:
            status = "BLOCKED"
            reason = "candidate_revision_not_next"
        elif _parse_time(candidate.created_at, "candidate.created_at") <= _parse_time(
            previous.created_at,
            "previous.created_at",
        ):
            status = "BLOCKED"
            reason = "candidate_not_newer_than_previous"
        elif not fresh_refs:
            status = "BLOCKED"
            reason = "fresh_reconsolidation_evidence_required"
        elif not set(fresh_refs).issubset(set(candidate.provenance_refs)):
            status = "BLOCKED"
            reason = "reconsolidation_evidence_not_bound_to_candidate"
        elif not (set(fresh_refs) - set(previous.provenance_refs)):
            status = "BLOCKED"
            reason = "reconsolidation_requires_new_provenance"

        payload: dict[str, object] = {
            "schema": RECONSOLIDATION_GATE_SCHEMA_VERSION,
            "status": status,
            "reason": reason,
            "previous_record_sha256": previous.record_sha256,
            "candidate_record_sha256": candidate.record_sha256,
            "fresh_provenance_refs": list(fresh_refs),
            "promotion_status": "not_promoted",
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReconsolidationGateDecision(
            **payload,
            decision_sha256=_sha256(payload),
        )
