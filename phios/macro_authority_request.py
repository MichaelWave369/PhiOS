"""Immutable zero-authority Ghost-Walk AuthorityRequest for v0.31.

An AuthorityRequest records that bounded action authority was requested for one
exact accepted semantic intent under one exact ALLOW_REQUEST admission receipt.

A request is not authorization, not an ActionLease, and not execution.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_policy_admission import (
    GhostWalkPolicyAdmissionError,
    GhostWalkPolicyAdmissionReceipt,
    GhostWalkPolicyAdmissionService,
    GhostWalkPolicyDecision,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_AUTHORITY_REQUEST_SCHEMA_VERSION = (
    "phios.ghostwalk_authority_request.v0.31"
)
GHOSTWALK_AUTHORITY_REQUEST_READINESS_SCHEMA_VERSION = (
    "phios.ghostwalk_authority_request_readiness.v0.31"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INTENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


class GhostWalkAuthorityRequestError(ValueError):
    """Raised when AuthorityRequest evidence or provenance is invalid."""


class GhostWalkRequestedAuthorityKind(StrEnum):
    ACTION_AUTHORITY = "ACTION_AUTHORITY"


class GhostWalkRequestScopeKind(StrEnum):
    ACCEPTED_INTENT = "ACCEPTED_INTENT"


class GhostWalkAuthorityRequestState(StrEnum):
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"


class GhostWalkAuthorityRequestReadinessReason(StrEnum):
    READY = "READY"
    POLICY_NOT_ALLOW_REQUEST = "POLICY_NOT_ALLOW_REQUEST"
    ADMISSION_RECEIPT_REQUIRED = "ADMISSION_RECEIPT_REQUIRED"
    ADMISSION_RECEIPT_STALE = "ADMISSION_RECEIPT_STALE"
    REQUEST_ALREADY_EXISTS = "REQUEST_ALREADY_EXISTS"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkAuthorityRequestError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkAuthorityRequestError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkAuthorityRequestError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkAuthorityRequestError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkAuthorityRequestError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkAuthorityRequestError(
            f"{field} must include a timezone"
        )
    return text


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkAuthorityRequestError(
            f"{field} must be Boolean"
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
        raise GhostWalkAuthorityRequestError(
            "AuthorityRequest payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GhostWalkAuthorityRequest:
    admission_receipt_sha256: str
    target_inference_receipt_sha256: str
    accepted_intent_revision_sha256: str
    policy_profile_sha256: str
    intent_family: str
    intent_code: str
    requester_id: str
    requested_authority_kind: GhostWalkRequestedAuthorityKind
    requested_scope_kind: GhostWalkRequestScopeKind
    requested_scope_value: str
    request_state: GhostWalkAuthorityRequestState
    requested_at: str
    authorization_granted: bool = False
    action_lease_created: bool = False
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_AUTHORITY_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_AUTHORITY_REQUEST_SCHEMA_VERSION:
            raise GhostWalkAuthorityRequestError(
                "unsupported AuthorityRequest schema"
            )
        for field, digest in (
            ("admission_receipt_sha256", self.admission_receipt_sha256),
            (
                "target_inference_receipt_sha256",
                self.target_inference_receipt_sha256,
            ),
            (
                "accepted_intent_revision_sha256",
                self.accepted_intent_revision_sha256,
            ),
            ("policy_profile_sha256", self.policy_profile_sha256),
        ):
            _require_sha256(digest, field)
        _require_text(self.intent_family, "intent_family", maximum=64)
        code = _require_text(self.intent_code, "intent_code", maximum=128)
        if not _INTENT_CODE_RE.fullmatch(code):
            raise GhostWalkAuthorityRequestError(
                "intent_code must be an uppercase symbolic identifier"
            )
        _require_text(self.requester_id, "requester_id", maximum=512)
        if self.requested_scope_value != self.intent_code:
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest scope must equal the accepted intent code"
            )
        _require_timestamp(self.requested_at, "requested_at")
        if (
            self.authorization_granted
            or self.action_lease_created
            or self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest cannot carry grants, leases, effects, or authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "admission_receipt_sha256": self.admission_receipt_sha256,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "accepted_intent_revision_sha256": (
                self.accepted_intent_revision_sha256
            ),
            "policy_profile_sha256": self.policy_profile_sha256,
            "intent_family": self.intent_family,
            "intent_code": self.intent_code,
            "requester_id": self.requester_id,
            "requested_authority_kind": self.requested_authority_kind.value,
            "requested_scope_kind": self.requested_scope_kind.value,
            "requested_scope_value": self.requested_scope_value,
            "request_state": self.request_state.value,
            "requested_at": self.requested_at,
            "authorization_granted": self.authorization_granted,
            "action_lease_created": self.action_lease_created,
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def authority_request_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["authority_request_sha256"] = (
            self.authority_request_sha256
        )
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkAuthorityRequest":
        expected = {
            "schema_version",
            "admission_receipt_sha256",
            "target_inference_receipt_sha256",
            "accepted_intent_revision_sha256",
            "policy_profile_sha256",
            "intent_family",
            "intent_code",
            "requester_id",
            "requested_authority_kind",
            "requested_scope_kind",
            "requested_scope_value",
            "request_state",
            "requested_at",
            "authorization_granted",
            "action_lease_created",
            "effect_performed",
            "policy_authority",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "authority_request_sha256",
        }
        if set(payload) != expected:
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest fields do not match contract"
            )
        claimed = _require_sha256(
            payload.get("authority_request_sha256"),
            "authority_request_sha256",
        )
        try:
            authority_kind = GhostWalkRequestedAuthorityKind(
                _require_text(
                    payload.get("requested_authority_kind"),
                    "requested_authority_kind",
                    maximum=64,
                )
            )
            scope_kind = GhostWalkRequestScopeKind(
                _require_text(
                    payload.get("requested_scope_kind"),
                    "requested_scope_kind",
                    maximum=64,
                )
            )
            request_state = GhostWalkAuthorityRequestState(
                _require_text(
                    payload.get("request_state"),
                    "request_state",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest enum value is unsupported"
            ) from exc

        request = cls(
            admission_receipt_sha256=_require_sha256(
                payload.get("admission_receipt_sha256"),
                "admission_receipt_sha256",
            ),
            target_inference_receipt_sha256=_require_sha256(
                payload.get("target_inference_receipt_sha256"),
                "target_inference_receipt_sha256",
            ),
            accepted_intent_revision_sha256=_require_sha256(
                payload.get("accepted_intent_revision_sha256"),
                "accepted_intent_revision_sha256",
            ),
            policy_profile_sha256=_require_sha256(
                payload.get("policy_profile_sha256"),
                "policy_profile_sha256",
            ),
            intent_family=_require_text(
                payload.get("intent_family"),
                "intent_family",
                maximum=64,
            ),
            intent_code=_require_text(
                payload.get("intent_code"),
                "intent_code",
                maximum=128,
            ),
            requester_id=_require_text(
                payload.get("requester_id"),
                "requester_id",
                maximum=512,
            ),
            requested_authority_kind=authority_kind,
            requested_scope_kind=scope_kind,
            requested_scope_value=_require_text(
                payload.get("requested_scope_value"),
                "requested_scope_value",
                maximum=128,
            ),
            request_state=request_state,
            requested_at=_require_timestamp(
                payload.get("requested_at"),
                "requested_at",
            ),
            authorization_granted=_require_bool(
                payload.get("authorization_granted"),
                "authorization_granted",
            ),
            action_lease_created=_require_bool(
                payload.get("action_lease_created"),
                "action_lease_created",
            ),
            effect_performed=_require_bool(
                payload.get("effect_performed"),
                "effect_performed",
            ),
            policy_authority=_require_bool(
                payload.get("policy_authority"),
                "policy_authority",
            ),
            operational_authority=_require_bool(
                payload.get("operational_authority"),
                "operational_authority",
            ),
            action_authority=_require_bool(
                payload.get("action_authority"),
                "action_authority",
            ),
            execution_authority=_require_bool(
                payload.get("execution_authority"),
                "execution_authority",
            ),
            schema_version=_require_text(
                payload.get("schema_version"),
                "schema_version",
                maximum=128,
            ),
        )
        if request.authority_request_sha256 != claimed:
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest hash mismatch"
            )
        return request


@dataclass(frozen=True, slots=True)
class GhostWalkAuthorityRequestReadiness:
    target_inference_receipt_sha256: str
    accepted_intent_revision_sha256: str
    policy_profile_sha256: str
    policy_decision: str
    ready: bool
    reason: GhostWalkAuthorityRequestReadinessReason
    admission_receipt_sha256: str | None
    existing_authority_request_sha256: str | None
    authorization_granted: bool = False
    action_lease_created: bool = False
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = (
        GHOSTWALK_AUTHORITY_REQUEST_READINESS_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GHOSTWALK_AUTHORITY_REQUEST_READINESS_SCHEMA_VERSION
        ):
            raise GhostWalkAuthorityRequestError(
                "unsupported AuthorityRequest readiness schema"
            )
        for field, digest in (
            (
                "target_inference_receipt_sha256",
                self.target_inference_receipt_sha256,
            ),
            (
                "accepted_intent_revision_sha256",
                self.accepted_intent_revision_sha256,
            ),
            ("policy_profile_sha256", self.policy_profile_sha256),
        ):
            _require_sha256(digest, field)
        _require_text(self.policy_decision, "policy_decision", maximum=64)
        _optional_sha256(
            self.admission_receipt_sha256,
            "admission_receipt_sha256",
        )
        _optional_sha256(
            self.existing_authority_request_sha256,
            "existing_authority_request_sha256",
        )
        if self.ready is not (
            self.reason is GhostWalkAuthorityRequestReadinessReason.READY
        ):
            raise GhostWalkAuthorityRequestError(
                "readiness Boolean must match readiness reason"
            )
        if (
            self.authorization_granted
            or self.action_lease_created
            or self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest readiness cannot carry grants, effects, or authority"
            )

    def to_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "accepted_intent_revision_sha256": (
                self.accepted_intent_revision_sha256
            ),
            "policy_profile_sha256": self.policy_profile_sha256,
            "policy_decision": self.policy_decision,
            "ready": self.ready,
            "reason": self.reason.value,
            "admission_receipt_sha256": self.admission_receipt_sha256,
            "existing_authority_request_sha256": (
                self.existing_authority_request_sha256
            ),
            "authorization_granted": self.authorization_granted,
            "action_lease_created": self.action_lease_created,
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }
        payload["readiness_sha256"] = _canonical_sha256(payload)
        return payload


class GhostWalkAuthorityRequestService:
    """Create one immutable zero-authority request per admission receipt."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        policy_admission: GhostWalkPolicyAdmissionService,
        requester_id: str,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkAuthorityRequestError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._policy_admission = policy_admission
        self.requester_id = _require_text(
            requester_id,
            "requester_id",
            maximum=512,
        )
        self._lock = threading.RLock()

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorityRequestReadiness:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        try:
            projection = self._policy_admission.project(
                target_inference_receipt_sha256=target
            )
        except GhostWalkPolicyAdmissionError as exc:
            raise GhostWalkAuthorityRequestError(str(exc)) from exc

        if projection.decision is not GhostWalkPolicyDecision.ALLOW_REQUEST:
            return GhostWalkAuthorityRequestReadiness(
                target_inference_receipt_sha256=target,
                accepted_intent_revision_sha256=(
                    projection.accepted_intent_revision_sha256
                ),
                policy_profile_sha256=projection.policy_profile_sha256,
                policy_decision=projection.decision.value,
                ready=False,
                reason=(
                    GhostWalkAuthorityRequestReadinessReason
                    .POLICY_NOT_ALLOW_REQUEST
                ),
                admission_receipt_sha256=None,
                existing_authority_request_sha256=None,
            )

        matching, any_receipt = self._matching_admission_receipt(
            target=target,
            accepted_intent_revision_sha256=(
                projection.accepted_intent_revision_sha256
            ),
            policy_profile_sha256=projection.policy_profile_sha256,
        )
        if matching is None:
            reason = (
                GhostWalkAuthorityRequestReadinessReason
                .ADMISSION_RECEIPT_STALE
                if any_receipt
                else GhostWalkAuthorityRequestReadinessReason
                .ADMISSION_RECEIPT_REQUIRED
            )
            return GhostWalkAuthorityRequestReadiness(
                target_inference_receipt_sha256=target,
                accepted_intent_revision_sha256=(
                    projection.accepted_intent_revision_sha256
                ),
                policy_profile_sha256=projection.policy_profile_sha256,
                policy_decision=projection.decision.value,
                ready=False,
                reason=reason,
                admission_receipt_sha256=None,
                existing_authority_request_sha256=None,
            )

        existing = self._request_for_admission(
            matching.admission_receipt_sha256
        )
        if existing is not None:
            return GhostWalkAuthorityRequestReadiness(
                target_inference_receipt_sha256=target,
                accepted_intent_revision_sha256=(
                    projection.accepted_intent_revision_sha256
                ),
                policy_profile_sha256=projection.policy_profile_sha256,
                policy_decision=projection.decision.value,
                ready=False,
                reason=(
                    GhostWalkAuthorityRequestReadinessReason
                    .REQUEST_ALREADY_EXISTS
                ),
                admission_receipt_sha256=(
                    matching.admission_receipt_sha256
                ),
                existing_authority_request_sha256=(
                    existing.authority_request_sha256
                ),
            )

        return GhostWalkAuthorityRequestReadiness(
            target_inference_receipt_sha256=target,
            accepted_intent_revision_sha256=(
                projection.accepted_intent_revision_sha256
            ),
            policy_profile_sha256=projection.policy_profile_sha256,
            policy_decision=projection.decision.value,
            ready=True,
            reason=GhostWalkAuthorityRequestReadinessReason.READY,
            admission_receipt_sha256=matching.admission_receipt_sha256,
            existing_authority_request_sha256=None,
        )

    def create(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_admission_receipt_sha256: str,
        requested_at: str | None = None,
    ) -> GhostWalkAuthorityRequest:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        expected_admission = _require_sha256(
            expected_admission_receipt_sha256,
            "expected_admission_receipt_sha256",
        )
        timestamp = _require_timestamp(
            _utc_now() if requested_at is None else requested_at,
            "requested_at",
        )

        with self._lock:
            readiness = self.readiness(
                target_inference_receipt_sha256=target
            )
            if not readiness.ready:
                raise GhostWalkAuthorityRequestError(
                    f"AuthorityRequest not ready: {readiness.reason.value}"
                )
            if readiness.admission_receipt_sha256 != expected_admission:
                raise GhostWalkAuthorityRequestError(
                    "admission receipt changed before AuthorityRequest creation"
                )

            receipt = self._receipt_by_sha256(expected_admission)
            if receipt is None:
                raise GhostWalkAuthorityRequestError(
                    "admission receipt disappeared before AuthorityRequest creation"
                )
            projection = self._policy_admission.project(
                target_inference_receipt_sha256=target
            )
            request = GhostWalkAuthorityRequest(
                admission_receipt_sha256=(
                    receipt.admission_receipt_sha256
                ),
                target_inference_receipt_sha256=target,
                accepted_intent_revision_sha256=(
                    receipt.accepted_intent_revision_sha256
                ),
                policy_profile_sha256=receipt.policy_profile_sha256,
                intent_family=projection.intent_family,
                intent_code=projection.intent_code,
                requester_id=self.requester_id,
                requested_authority_kind=(
                    GhostWalkRequestedAuthorityKind.ACTION_AUTHORITY
                ),
                requested_scope_kind=(
                    GhostWalkRequestScopeKind.ACCEPTED_INTENT
                ),
                requested_scope_value=projection.intent_code,
                request_state=(
                    GhostWalkAuthorityRequestState.PENDING_AUTHORIZATION
                ),
                requested_at=timestamp,
            )
            self._ledger.append_ghostwalk_authority_request(request)
            return request

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorityRequest | None:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        rows = self._ledger.ghostwalk_authority_requests(
            target_inference_receipt_sha256=target
        )
        requests = [
            self._parse_request_row(row)
            for row in rows
        ]
        return requests[-1] if requests else None

    def _matching_admission_receipt(
        self,
        *,
        target: str,
        accepted_intent_revision_sha256: str,
        policy_profile_sha256: str,
    ) -> tuple[GhostWalkPolicyAdmissionReceipt | None, bool]:
        rows = self._ledger.ghostwalk_policy_admission_receipts(
            target_inference_receipt_sha256=target
        )
        any_receipt = bool(rows)
        parsed: list[GhostWalkPolicyAdmissionReceipt] = []
        for row in rows:
            try:
                parsed.append(
                    GhostWalkPolicyAdmissionReceipt.from_dict(row)
                )
            except GhostWalkPolicyAdmissionError as exc:
                raise GhostWalkAuthorityRequestError(
                    "persisted policy admission receipt is invalid"
                ) from exc

        for receipt in reversed(parsed):
            if (
                receipt.decision is GhostWalkPolicyDecision.ALLOW_REQUEST
                and receipt.request_authority_eligible
                and (
                    receipt.accepted_intent_revision_sha256
                    == accepted_intent_revision_sha256
                )
                and receipt.policy_profile_sha256 == policy_profile_sha256
            ):
                return receipt, any_receipt
        return None, any_receipt

    def _receipt_by_sha256(
        self,
        receipt_sha256: str,
    ) -> GhostWalkPolicyAdmissionReceipt | None:
        for row in self._ledger.ghostwalk_policy_admission_receipts():
            try:
                receipt = GhostWalkPolicyAdmissionReceipt.from_dict(row)
            except GhostWalkPolicyAdmissionError as exc:
                raise GhostWalkAuthorityRequestError(
                    "persisted policy admission receipt is invalid"
                ) from exc
            if receipt.admission_receipt_sha256 == receipt_sha256:
                return receipt
        return None

    def _request_for_admission(
        self,
        admission_receipt_sha256: str,
    ) -> GhostWalkAuthorityRequest | None:
        matches: list[GhostWalkAuthorityRequest] = []
        for row in self._ledger.ghostwalk_authority_requests():
            request = self._parse_request_row(row)
            if (
                request.admission_receipt_sha256
                == admission_receipt_sha256
            ):
                matches.append(request)
        if len(matches) > 1:
            raise GhostWalkAuthorityRequestError(
                "multiple AuthorityRequests exist for one admission receipt"
            )
        return matches[0] if matches else None

    def _parse_request_row(
        self,
        row: Mapping[str, object],
    ) -> GhostWalkAuthorityRequest:
        try:
            request = GhostWalkAuthorityRequest.from_dict(row)
        except GhostWalkAuthorityRequestError as exc:
            raise GhostWalkAuthorityRequestError(
                "persisted AuthorityRequest is invalid"
            ) from exc
        self._validate_request_provenance(request)
        return request

    def _validate_request_provenance(
        self,
        request: GhostWalkAuthorityRequest,
    ) -> None:
        receipt = self._receipt_by_sha256(
            request.admission_receipt_sha256
        )
        if receipt is None:
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest admission receipt is missing"
            )
        if (
            receipt.target_inference_receipt_sha256
            != request.target_inference_receipt_sha256
        ):
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest target does not match admission receipt"
            )
        if (
            receipt.accepted_intent_revision_sha256
            != request.accepted_intent_revision_sha256
        ):
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest accepted intent does not match admission receipt"
            )
        if (
            receipt.policy_profile_sha256
            != request.policy_profile_sha256
        ):
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest policy profile does not match admission receipt"
            )
        if (
            receipt.decision is not GhostWalkPolicyDecision.ALLOW_REQUEST
            or not receipt.request_authority_eligible
        ):
            raise GhostWalkAuthorityRequestError(
                "AuthorityRequest admission receipt is not ALLOW_REQUEST"
            )
