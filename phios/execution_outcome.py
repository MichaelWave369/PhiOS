"""Canonical execution-outcome reconciliation contract for PhiOS.

This contract separates executor control flow from claims about external reality.

Core law:

    EXECUTOR RETURN != EFFECT TRUTH
    EXECUTOR ERROR != EFFECT ABSENCE
    OUTCOME UNKNOWN != SAFE TO RETRY

Reconciliation receipts carry evidence about an uncertain attempt. They never
grant action or execution authority, including when evidence demonstrates that
a retry would be semantically safe.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from phios.evidence_ref import EvidenceRef
from phios.spine.models import ExecutionReceipt

EXECUTION_RECONCILIATION_SCHEMA_VERSION = "phios.execution_reconciliation.v0.1"
RECONCILIATION_DISPOSITIONS = (
    "effect_confirmed",
    "no_effect_confirmed",
    "inconclusive",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ExecutionReconciliationContractError(ValueError):
    """Raised when execution reconciliation inputs are unsafe or malformed."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionReconciliationContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise ExecutionReconciliationContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise ExecutionReconciliationContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ExecutionReconciliationContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionReconciliationContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionReconciliationContractError(
            f"{field} must include a timezone offset"
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
        raise ExecutionReconciliationContractError(
            "execution reconciliation payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def execution_receipt_sha256(receipt: ExecutionReceipt) -> str:
    """Return a deterministic digest for the exact execution receipt body."""

    if not isinstance(receipt, ExecutionReceipt):
        raise ExecutionReconciliationContractError(
            "execution receipt must be an ExecutionReceipt"
        )
    return _canonical_sha256(receipt.to_dict())


@dataclass(frozen=True, slots=True)
class ExecutionReconciliationReceipt:
    """Evidence-bound resolution attempt for one outcome-unknown execution."""

    execution_receipt_id: str
    execution_receipt_sha256: str
    disposition: str
    reconciler_id: str
    reconciled_at: str
    evidence_ref_sha256s: tuple[str, ...]
    effect_confirmed: bool | None
    retry_safe: bool
    reconciliation_required: bool
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = EXECUTION_RECONCILIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_RECONCILIATION_SCHEMA_VERSION:
            raise ExecutionReconciliationContractError(
                "unsupported execution reconciliation schema"
            )
        _require_text(self.execution_receipt_id, "execution_receipt_id")
        _require_sha256(
            self.execution_receipt_sha256,
            "execution_receipt_sha256",
        )
        if self.disposition not in RECONCILIATION_DISPOSITIONS:
            raise ExecutionReconciliationContractError(
                f"unsupported reconciliation disposition: {self.disposition}"
            )
        _require_text(self.reconciler_id, "reconciler_id")
        _require_timestamp(self.reconciled_at, "reconciled_at")
        if not self.evidence_ref_sha256s:
            raise ExecutionReconciliationContractError(
                "reconciliation requires at least one EvidenceRef"
            )
        if tuple(sorted(self.evidence_ref_sha256s)) != self.evidence_ref_sha256s:
            raise ExecutionReconciliationContractError(
                "evidence_ref_sha256s must be sorted"
            )
        if len(set(self.evidence_ref_sha256s)) != len(self.evidence_ref_sha256s):
            raise ExecutionReconciliationContractError(
                "evidence_ref_sha256s must not contain duplicates"
            )
        for digest in self.evidence_ref_sha256s:
            _require_sha256(digest, "EvidenceRef digest")

        expected = {
            "effect_confirmed": (True, False, False),
            "no_effect_confirmed": (False, True, False),
            "inconclusive": (None, False, True),
        }[self.disposition]
        actual = (
            self.effect_confirmed,
            self.retry_safe,
            self.reconciliation_required,
        )
        if actual != expected:
            raise ExecutionReconciliationContractError(
                "reconciliation disposition/state fields are inconsistent"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise ExecutionReconciliationContractError(
                "reconciliation evidence cannot carry operational or execution authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_receipt_id": self.execution_receipt_id,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "disposition": self.disposition,
            "reconciler_id": self.reconciler_id,
            "reconciled_at": self.reconciled_at,
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "effect_confirmed": self.effect_confirmed,
            "retry_safe": self.retry_safe,
            "reconciliation_required": self.reconciliation_required,
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


def reconcile_execution_outcome(
    *,
    execution: ExecutionReceipt,
    disposition: str,
    evidence_refs: tuple[EvidenceRef, ...],
    reconciler_id: str,
    reconciled_at: str,
) -> ExecutionReconciliationReceipt:
    """Reconcile one outcome-unknown execution using explicit EvidenceRefs.

    A no-effect confirmation can establish semantic retry safety, but it never
    grants the authority required to perform that retry.
    """

    if not isinstance(execution, ExecutionReceipt):
        raise ExecutionReconciliationContractError(
            "execution must be an ExecutionReceipt"
        )
    if execution.execution_status != "outcome_unknown":
        raise ExecutionReconciliationContractError(
            "only outcome_unknown executions can be reconciled"
        )
    if execution.executor_entered is not True:
        raise ExecutionReconciliationContractError(
            "outcome_unknown requires executor_entered=true"
        )
    if execution.reconciliation_status != "required":
        raise ExecutionReconciliationContractError(
            "outcome_unknown execution must require reconciliation"
        )
    if disposition not in RECONCILIATION_DISPOSITIONS:
        raise ExecutionReconciliationContractError(
            f"unsupported reconciliation disposition: {disposition}"
        )
    _require_text(reconciler_id, "reconciler_id")
    _require_timestamp(reconciled_at, "reconciled_at")

    if not evidence_refs:
        raise ExecutionReconciliationContractError(
            "reconciliation requires at least one EvidenceRef"
        )
    evidence_digests: list[str] = []
    for evidence in evidence_refs:
        if not isinstance(evidence, EvidenceRef):
            raise ExecutionReconciliationContractError(
                "evidence_refs must contain EvidenceRef objects"
            )
        evidence_digests.append(evidence.reference_sha256)
    canonical_evidence = tuple(sorted(set(evidence_digests)))

    effect_confirmed, retry_safe, reconciliation_required = {
        "effect_confirmed": (True, False, False),
        "no_effect_confirmed": (False, True, False),
        "inconclusive": (None, False, True),
    }[disposition]

    return ExecutionReconciliationReceipt(
        execution_receipt_id=execution.receipt_id,
        execution_receipt_sha256=execution_receipt_sha256(execution),
        disposition=disposition,
        reconciler_id=reconciler_id,
        reconciled_at=reconciled_at,
        evidence_ref_sha256s=canonical_evidence,
        effect_confirmed=effect_confirmed,
        retry_safe=retry_safe,
        reconciliation_required=reconciliation_required,
    )
