"""Reality-bound reconciliation policies for PhiOS uncertain executions.

This layer binds an exact capability contract and declared effect scope to the
Reality Verification claim kinds that are permitted to reconcile its uncertain
execution outcomes.

Core law:

    OBSERVATION != RECONCILIATION
    RECONCILIATION POLICY != AUTHORITY
    RETRY SAFE != RETRY AUTHORIZED
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from phios.evidence_ref import EvidenceRef
from phios.execution_outcome import (
    ExecutionReconciliationReceipt,
    reconcile_execution_outcome,
)
from phios.reality import (
    RealityClaimKind,
    RealityVerificationResult,
    RealityVerdict,
)
from phios.spine.effects import EffectBoundaryContractError, normalize_effects
from phios.spine.models import Capability, ExecutionReceipt

REALITY_RECONCILIATION_POLICY_SCHEMA_VERSION = (
    "phios.reality_reconciliation_policy.v0.1"
)
REALITY_BOUND_RECONCILIATION_SCHEMA_VERSION = (
    "phios.reality_bound_reconciliation.v0.1"
)
_ALLOWED_CONTRADICTED_DISPOSITIONS = (
    "no_effect_confirmed",
    "inconclusive",
)


class RealityReconciliationContractError(ValueError):
    """Raised when Reality-bound reconciliation cannot fail closed safely."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise RealityReconciliationContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise RealityReconciliationContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise RealityReconciliationContractError(
            f"{field} contains control characters"
        )
    return value


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
        raise RealityReconciliationContractError(
            "Reality reconciliation payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_claim_kinds(
    values: Iterable[RealityClaimKind | str],
) -> tuple[str, ...]:
    allowed = {item.value for item in RealityClaimKind}
    normalized: list[str] = []
    for raw in values:
        value = raw.value if isinstance(raw, RealityClaimKind) else raw
        if not isinstance(value, str) or value not in allowed:
            raise RealityReconciliationContractError(
                f"unsupported Reality claim kind: {value}"
            )
        if value not in normalized:
            normalized.append(value)
    result = tuple(sorted(normalized))
    if not result:
        raise RealityReconciliationContractError(
            "allowed_claim_kinds must not be empty"
        )
    return result


@dataclass(frozen=True, slots=True)
class RealityReconciliationPolicy:
    """Exact capability/effect binding for Reality-based reconciliation."""

    policy_id: str
    capability_id: str
    capability_version: str
    effect_scope: tuple[str, ...]
    allowed_claim_kinds: tuple[str, ...]
    contradicted_disposition: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = REALITY_RECONCILIATION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REALITY_RECONCILIATION_POLICY_SCHEMA_VERSION:
            raise RealityReconciliationContractError(
                "unsupported Reality reconciliation policy schema"
            )
        _require_text(self.policy_id, "policy_id")
        _require_text(self.capability_id, "capability_id")
        _require_text(self.capability_version, "capability_version", maximum=64)
        try:
            normalized_effects = normalize_effects(
                self.effect_scope,
                label="reconciliation policy effect scope",
            )
        except EffectBoundaryContractError as exc:
            raise RealityReconciliationContractError(str(exc)) from exc
        if normalized_effects != self.effect_scope:
            raise RealityReconciliationContractError(
                "effect_scope must be canonical and sorted"
            )
        if _normalize_claim_kinds(self.allowed_claim_kinds) != (
            self.allowed_claim_kinds
        ):
            raise RealityReconciliationContractError(
                "allowed_claim_kinds must be canonical and sorted"
            )
        if self.contradicted_disposition not in (
            _ALLOWED_CONTRADICTED_DISPOSITIONS
        ):
            raise RealityReconciliationContractError(
                "contradicted_disposition must be no_effect_confirmed or inconclusive"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise RealityReconciliationContractError(
                "reconciliation policy cannot carry authority"
            )

    @classmethod
    def build(
        cls,
        *,
        policy_id: str,
        capability: Capability,
        allowed_claim_kinds: tuple[RealityClaimKind | str, ...],
        contradicted_disposition: str = "inconclusive",
    ) -> "RealityReconciliationPolicy":
        try:
            effects = normalize_effects(
                capability.effects,
                label="capability effects",
            )
        except EffectBoundaryContractError as exc:
            raise RealityReconciliationContractError(str(exc)) from exc
        return cls(
            policy_id=policy_id,
            capability_id=capability.id,
            capability_version=capability.version,
            effect_scope=effects,
            allowed_claim_kinds=_normalize_claim_kinds(allowed_claim_kinds),
            contradicted_disposition=contradicted_disposition,
        )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "effect_scope": list(self.effect_scope),
            "allowed_claim_kinds": list(self.allowed_claim_kinds),
            "contradicted_disposition": self.contradicted_disposition,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def policy_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["policy_sha256"] = self.policy_sha256
        return payload


@dataclass(frozen=True, slots=True)
class RealityBoundReconciliationReceipt:
    """Binds one reconciliation result to exact Reality evidence and policy."""

    policy_sha256: str
    capability_id: str
    capability_version: str
    effect_scope: tuple[str, ...]
    reality_receipt_id: str
    reality_receipt_sha256: str
    claim_verdicts: tuple[dict[str, str], ...]
    execution_reconciliation: dict[str, Any]
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = REALITY_BOUND_RECONCILIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REALITY_BOUND_RECONCILIATION_SCHEMA_VERSION:
            raise RealityReconciliationContractError(
                "unsupported Reality-bound reconciliation schema"
            )
        _require_text(self.policy_sha256, "policy_sha256", maximum=64)
        if (
            len(self.policy_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.policy_sha256)
        ):
            raise RealityReconciliationContractError(
                "policy_sha256 must be a lowercase SHA-256 digest"
            )
        _require_text(self.capability_id, "capability_id")
        _require_text(self.capability_version, "capability_version", maximum=64)
        _require_text(self.reality_receipt_id, "reality_receipt_id")
        _require_text(
            self.reality_receipt_sha256,
            "reality_receipt_sha256",
            maximum=64,
        )
        if (
            len(self.reality_receipt_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in self.reality_receipt_sha256
            )
        ):
            raise RealityReconciliationContractError(
                "reality_receipt_sha256 must be a lowercase SHA-256 digest"
            )
        if not self.claim_verdicts:
            raise RealityReconciliationContractError(
                "claim_verdicts must not be empty"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise RealityReconciliationContractError(
                "Reality-bound reconciliation cannot carry authority"
            )

    @property
    def disposition(self) -> str:
        return str(self.execution_reconciliation["disposition"])

    @property
    def retry_safe(self) -> bool:
        return bool(self.execution_reconciliation["retry_safe"])

    @property
    def effect_confirmed(self) -> bool | None:
        value = self.execution_reconciliation["effect_confirmed"]
        if value is None or isinstance(value, bool):
            return value
        raise RealityReconciliationContractError(
            "execution reconciliation effect_confirmed is malformed"
        )

    @property
    def reconciliation_required(self) -> bool:
        return bool(self.execution_reconciliation["reconciliation_required"])

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_sha256": self.policy_sha256,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "effect_scope": list(self.effect_scope),
            "reality_receipt_id": self.reality_receipt_id,
            "reality_receipt_sha256": self.reality_receipt_sha256,
            "claim_verdicts": [dict(item) for item in self.claim_verdicts],
            "execution_reconciliation": dict(self.execution_reconciliation),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


def _validate_policy_binding(
    *,
    execution: ExecutionReceipt,
    capability: Capability,
    policy: RealityReconciliationPolicy,
) -> None:
    if execution.capability_id != capability.id:
        raise RealityReconciliationContractError(
            "execution capability does not match current capability"
        )
    if policy.capability_id != capability.id:
        raise RealityReconciliationContractError(
            "reconciliation policy capability mismatch"
        )
    if policy.capability_version != capability.version:
        raise RealityReconciliationContractError(
            "reconciliation policy capability version mismatch"
        )
    try:
        current_effects = normalize_effects(
            capability.effects,
            label="current capability effects",
        )
    except EffectBoundaryContractError as exc:
        raise RealityReconciliationContractError(str(exc)) from exc
    if current_effects != policy.effect_scope:
        raise RealityReconciliationContractError(
            "reconciliation policy effect scope mismatch"
        )


def _validate_verification_integrity(
    verification: RealityVerificationResult,
) -> None:
    if verification.receipt.packet_id != verification.packet.packet_id:
        raise RealityReconciliationContractError(
            "Reality verification packet/receipt identity mismatch"
        )
    if verification.receipt.task_id != verification.packet.task_id:
        raise RealityReconciliationContractError(
            "Reality verification task identity mismatch"
        )

    claim_results = [dict(item) for item in verification.claim_results]
    receipt_claims = [dict(item) for item in verification.receipt.claims_checked]
    if _canonical_json(claim_results) != _canonical_json(receipt_claims):
        raise RealityReconciliationContractError(
            "Reality receipt claims_checked does not match claim_results"
        )

    packet_claim_ids = {
        item.get("claim_id")
        for item in verification.packet.claims
        if isinstance(item, dict)
    }
    result_claim_ids = {
        item.get("claim_id")
        for item in verification.claim_results
        if isinstance(item, dict)
    }
    if packet_claim_ids != result_claim_ids:
        raise RealityReconciliationContractError(
            "Reality packet claims do not match verification claim results"
        )

    expected_summary: dict[str, int] = {}
    for item in verification.claim_results:
        verdict = item.get("verdict")
        if isinstance(verdict, str):
            expected_summary[verdict] = expected_summary.get(verdict, 0) + 1
    if expected_summary != verification.receipt.verdict_summary:
        raise RealityReconciliationContractError(
            "Reality verdict summary does not match claim results"
        )


def _claim_verdicts(
    *,
    verification: RealityVerificationResult,
    policy: RealityReconciliationPolicy,
) -> tuple[dict[str, str], ...]:
    if not verification.claim_results:
        raise RealityReconciliationContractError(
            "Reality verification must contain at least one claim result"
        )

    allowed_verdicts = {item.value for item in RealityVerdict}
    seen_ids: set[str] = set()
    normalized: list[dict[str, str]] = []
    for result in verification.claim_results:
        claim_id = result.get("claim_id")
        kind = result.get("kind")
        verdict = result.get("verdict")
        if not isinstance(claim_id, str) or not claim_id:
            raise RealityReconciliationContractError(
                "Reality claim result has invalid claim_id"
            )
        if claim_id in seen_ids:
            raise RealityReconciliationContractError(
                "Reality claim results contain duplicate claim_id"
            )
        seen_ids.add(claim_id)
        if not isinstance(kind, str) or kind not in policy.allowed_claim_kinds:
            raise RealityReconciliationContractError(
                f"Reality claim kind is not permitted by policy: {kind}"
            )
        if not isinstance(verdict, str) or verdict not in allowed_verdicts:
            raise RealityReconciliationContractError(
                f"Reality claim verdict is invalid: {verdict}"
            )
        normalized.append(
            {
                "claim_id": claim_id,
                "kind": kind,
                "verdict": verdict,
            }
        )
    return tuple(sorted(normalized, key=lambda item: item["claim_id"]))


def _validate_evidence_binding(
    *,
    verification: RealityVerificationResult,
    evidence_refs: tuple[EvidenceRef, ...],
) -> tuple[EvidenceRef, ...]:
    if not evidence_refs:
        raise RealityReconciliationContractError(
            "Reality reconciliation requires canonical EvidenceRef records"
        )
    canonical_by_uri: dict[str, EvidenceRef] = {}
    for evidence in evidence_refs:
        if not isinstance(evidence, EvidenceRef):
            raise RealityReconciliationContractError(
                "evidence_refs must contain EvidenceRef objects"
            )
        if evidence.evidence_ref in canonical_by_uri:
            raise RealityReconciliationContractError(
                "duplicate canonical EvidenceRef URI"
            )
        canonical_by_uri[evidence.evidence_ref] = evidence

    used = tuple(dict.fromkeys(verification.receipt.evidence_used))
    if not used:
        raise RealityReconciliationContractError(
            "Reality verification used no bindable evidence"
        )
    if set(used) != set(canonical_by_uri):
        raise RealityReconciliationContractError(
            "canonical EvidenceRefs must exactly cover Reality evidence_used"
        )
    return tuple(
        canonical_by_uri[uri]
        for uri in sorted(canonical_by_uri)
    )


def _disposition(
    *,
    claim_verdicts: tuple[dict[str, str], ...],
    policy: RealityReconciliationPolicy,
) -> str:
    verdicts = {item["verdict"] for item in claim_verdicts}
    if verdicts == {RealityVerdict.SUPPORTED.value}:
        return "effect_confirmed"
    if verdicts == {RealityVerdict.CONTRADICTED.value}:
        return policy.contradicted_disposition
    return "inconclusive"


def reconcile_execution_with_reality(
    *,
    execution: ExecutionReceipt,
    capability: Capability,
    policy: RealityReconciliationPolicy,
    verification: RealityVerificationResult,
    evidence_refs: tuple[EvidenceRef, ...],
    reconciler_id: str,
    reconciled_at: str,
) -> RealityBoundReconciliationReceipt:
    """Resolve one uncertain execution only through policy-bound Reality evidence."""

    _validate_policy_binding(
        execution=execution,
        capability=capability,
        policy=policy,
    )
    _validate_verification_integrity(verification)
    verdicts = _claim_verdicts(
        verification=verification,
        policy=policy,
    )
    canonical_evidence = _validate_evidence_binding(
        verification=verification,
        evidence_refs=evidence_refs,
    )
    disposition = _disposition(
        claim_verdicts=verdicts,
        policy=policy,
    )
    reconciliation: ExecutionReconciliationReceipt = (
        reconcile_execution_outcome(
            execution=execution,
            disposition=disposition,
            evidence_refs=canonical_evidence,
            reconciler_id=reconciler_id,
            reconciled_at=reconciled_at,
        )
    )
    reality_receipt_body = verification.receipt.to_dict()
    return RealityBoundReconciliationReceipt(
        policy_sha256=policy.policy_sha256,
        capability_id=capability.id,
        capability_version=capability.version,
        effect_scope=policy.effect_scope,
        reality_receipt_id=verification.receipt.receipt_id,
        reality_receipt_sha256=_canonical_sha256(reality_receipt_body),
        claim_verdicts=verdicts,
        execution_reconciliation=reconciliation.to_dict(),
    )
