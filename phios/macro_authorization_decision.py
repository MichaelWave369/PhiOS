"""Immutable zero-authority Ghost-Walk AuthorizationDecision for v0.32.

An AuthorizationDecision records one explicit operator decision about one exact
current AuthorityRequest. APPROVE records authorization as a fact, but does not
mint an ActionLease, bind an executable capability, or perform an effect.
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

from phios.macro_authority_request import (
    GhostWalkAuthorityRequest,
    GhostWalkAuthorityRequestError,
    GhostWalkAuthorityRequestReadinessReason,
    GhostWalkAuthorityRequestService,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_AUTHORIZATION_DECISION_SCHEMA_VERSION = (
    "phios.ghostwalk_authorization_decision.v0.32"
)
GHOSTWALK_AUTHORIZATION_READINESS_SCHEMA_VERSION = (
    "phios.ghostwalk_authorization_readiness.v0.32"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkAuthorizationDecisionError(ValueError):
    """Raised when authorization-decision evidence or provenance is invalid."""


class GhostWalkAuthorizationDecisionKind(StrEnum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    HOLD = "HOLD"


class GhostWalkAuthorizationReadinessReason(StrEnum):
    READY = "READY"
    AUTHORITY_REQUEST_REQUIRED = "AUTHORITY_REQUEST_REQUIRED"
    AUTHORITY_REQUEST_STALE = "AUTHORITY_REQUEST_STALE"
    DECISION_FINAL = "DECISION_FINAL"


def _require_text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkAuthorizationDecisionError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkAuthorizationDecisionError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkAuthorizationDecisionError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkAuthorizationDecisionError(
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
        raise GhostWalkAuthorizationDecisionError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkAuthorizationDecisionError(
            f"{field} must include a timezone"
        )
    return text


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkAuthorizationDecisionError(
            f"{field} must be Boolean"
        )
    return value


def _require_sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GhostWalkAuthorizationDecisionError(
            "decision_sequence must be a non-negative integer"
        )
    return value


def _optional_note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GhostWalkAuthorizationDecisionError(
            "decision_note must be string or null"
        )
    if len(value) > 2048:
        raise GhostWalkAuthorizationDecisionError(
            "decision_note exceeds 2048 characters"
        )
    if "\x00" in value:
        raise GhostWalkAuthorizationDecisionError(
            "decision_note contains NUL"
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
        raise GhostWalkAuthorizationDecisionError(
            "AuthorizationDecision payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GhostWalkAuthorizationDecision:
    authority_request_sha256: str
    target_inference_receipt_sha256: str
    admission_receipt_sha256: str
    accepted_intent_revision_sha256: str
    policy_profile_sha256: str
    intent_code: str
    authorizer_id: str
    decision: GhostWalkAuthorizationDecisionKind
    decision_sequence: int
    previous_decision_sha256: str | None
    decided_at: str
    decision_note: str | None = None
    authorization_granted: bool = False
    request_resolved: bool = False
    capability_binding_created: bool = False
    action_lease_created: bool = False
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_AUTHORIZATION_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_AUTHORIZATION_DECISION_SCHEMA_VERSION:
            raise GhostWalkAuthorizationDecisionError(
                "unsupported AuthorizationDecision schema"
            )
        for field, digest in (
            ("authority_request_sha256", self.authority_request_sha256),
            (
                "target_inference_receipt_sha256",
                self.target_inference_receipt_sha256,
            ),
            ("admission_receipt_sha256", self.admission_receipt_sha256),
            (
                "accepted_intent_revision_sha256",
                self.accepted_intent_revision_sha256,
            ),
            ("policy_profile_sha256", self.policy_profile_sha256),
        ):
            _require_sha256(digest, field)
        _require_text(self.intent_code, "intent_code", maximum=128)
        _require_text(self.authorizer_id, "authorizer_id", maximum=512)
        sequence = _require_sequence(self.decision_sequence)
        previous = _optional_sha256(
            self.previous_decision_sha256,
            "previous_decision_sha256",
        )
        if (sequence == 0) is not (previous is None):
            raise GhostWalkAuthorizationDecisionError(
                "decision sequence and previous decision hash disagree"
            )
        _require_timestamp(self.decided_at, "decided_at")
        _optional_note(self.decision_note)
        expected_granted = self.decision is GhostWalkAuthorizationDecisionKind.APPROVE
        expected_resolved = self.decision in {
            GhostWalkAuthorizationDecisionKind.APPROVE,
            GhostWalkAuthorizationDecisionKind.DENY,
        }
        if self.authorization_granted is not expected_granted:
            raise GhostWalkAuthorizationDecisionError(
                "authorization_granted must match decision"
            )
        if self.request_resolved is not expected_resolved:
            raise GhostWalkAuthorizationDecisionError(
                "request_resolved must match decision"
            )
        if (
            self.capability_binding_created
            or self.action_lease_created
            or self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkAuthorizationDecisionError(
                "AuthorizationDecision cannot carry bindings, leases, effects, or authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authority_request_sha256": self.authority_request_sha256,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "admission_receipt_sha256": self.admission_receipt_sha256,
            "accepted_intent_revision_sha256": (
                self.accepted_intent_revision_sha256
            ),
            "policy_profile_sha256": self.policy_profile_sha256,
            "intent_code": self.intent_code,
            "authorizer_id": self.authorizer_id,
            "decision": self.decision.value,
            "decision_sequence": self.decision_sequence,
            "previous_decision_sha256": self.previous_decision_sha256,
            "decided_at": self.decided_at,
            "decision_note": self.decision_note,
            "authorization_granted": self.authorization_granted,
            "request_resolved": self.request_resolved,
            "capability_binding_created": self.capability_binding_created,
            "action_lease_created": self.action_lease_created,
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def authorization_decision_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["authorization_decision_sha256"] = (
            self.authorization_decision_sha256
        )
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkAuthorizationDecision":
        expected = {
            "schema_version",
            "authority_request_sha256",
            "target_inference_receipt_sha256",
            "admission_receipt_sha256",
            "accepted_intent_revision_sha256",
            "policy_profile_sha256",
            "intent_code",
            "authorizer_id",
            "decision",
            "decision_sequence",
            "previous_decision_sha256",
            "decided_at",
            "decision_note",
            "authorization_granted",
            "request_resolved",
            "capability_binding_created",
            "action_lease_created",
            "effect_performed",
            "policy_authority",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "authorization_decision_sha256",
        }
        if set(payload) != expected:
            raise GhostWalkAuthorizationDecisionError(
                "AuthorizationDecision fields do not match contract"
            )
        claimed = _require_sha256(
            payload.get("authorization_decision_sha256"),
            "authorization_decision_sha256",
        )
        try:
            decision = GhostWalkAuthorizationDecisionKind(
                _require_text(
                    payload.get("decision"),
                    "decision",
                    maximum=32,
                )
            )
        except ValueError as exc:
            raise GhostWalkAuthorizationDecisionError(
                "AuthorizationDecision value is unsupported"
            ) from exc
        item = cls(
            authority_request_sha256=_require_sha256(
                payload.get("authority_request_sha256"),
                "authority_request_sha256",
            ),
            target_inference_receipt_sha256=_require_sha256(
                payload.get("target_inference_receipt_sha256"),
                "target_inference_receipt_sha256",
            ),
            admission_receipt_sha256=_require_sha256(
                payload.get("admission_receipt_sha256"),
                "admission_receipt_sha256",
            ),
            accepted_intent_revision_sha256=_require_sha256(
                payload.get("accepted_intent_revision_sha256"),
                "accepted_intent_revision_sha256",
            ),
            policy_profile_sha256=_require_sha256(
                payload.get("policy_profile_sha256"),
                "policy_profile_sha256",
            ),
            intent_code=_require_text(
                payload.get("intent_code"),
                "intent_code",
                maximum=128,
            ),
            authorizer_id=_require_text(
                payload.get("authorizer_id"),
                "authorizer_id",
                maximum=512,
            ),
            decision=decision,
            decision_sequence=_require_sequence(
                payload.get("decision_sequence")
            ),
            previous_decision_sha256=_optional_sha256(
                payload.get("previous_decision_sha256"),
                "previous_decision_sha256",
            ),
            decided_at=_require_timestamp(
                payload.get("decided_at"),
                "decided_at",
            ),
            decision_note=_optional_note(payload.get("decision_note")),
            authorization_granted=_require_bool(
                payload.get("authorization_granted"),
                "authorization_granted",
            ),
            request_resolved=_require_bool(
                payload.get("request_resolved"),
                "request_resolved",
            ),
            capability_binding_created=_require_bool(
                payload.get("capability_binding_created"),
                "capability_binding_created",
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
        if item.authorization_decision_sha256 != claimed:
            raise GhostWalkAuthorizationDecisionError(
                "AuthorizationDecision hash mismatch"
            )
        return item


@dataclass(frozen=True, slots=True)
class GhostWalkAuthorizationReadiness:
    target_inference_receipt_sha256: str
    authority_request_sha256: str | None
    latest_decision_sha256: str | None
    latest_decision: str | None
    ready: bool
    reason: GhostWalkAuthorizationReadinessReason
    authorization_granted: bool
    capability_binding_created: bool = False
    action_lease_created: bool = False
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_AUTHORIZATION_READINESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_AUTHORIZATION_READINESS_SCHEMA_VERSION:
            raise GhostWalkAuthorizationDecisionError(
                "unsupported authorization readiness schema"
            )
        _require_sha256(
            self.target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        _optional_sha256(
            self.authority_request_sha256,
            "authority_request_sha256",
        )
        _optional_sha256(
            self.latest_decision_sha256,
            "latest_decision_sha256",
        )
        if self.latest_decision is not None and self.latest_decision not in {
            item.value for item in GhostWalkAuthorizationDecisionKind
        }:
            raise GhostWalkAuthorizationDecisionError(
                "latest_decision is unsupported"
            )
        if self.ready is not (
            self.reason is GhostWalkAuthorizationReadinessReason.READY
        ):
            raise GhostWalkAuthorizationDecisionError(
                "authorization readiness Boolean must match reason"
            )
        expected_granted = self.latest_decision == (
            GhostWalkAuthorizationDecisionKind.APPROVE.value
        )
        if self.authorization_granted is not expected_granted:
            raise GhostWalkAuthorizationDecisionError(
                "readiness authorization_granted does not match latest decision"
            )
        if (
            self.capability_binding_created
            or self.action_lease_created
            or self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkAuthorizationDecisionError(
                "authorization readiness cannot carry bindings, leases, effects, or authority"
            )

    def to_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "authority_request_sha256": self.authority_request_sha256,
            "latest_decision_sha256": self.latest_decision_sha256,
            "latest_decision": self.latest_decision,
            "ready": self.ready,
            "reason": self.reason.value,
            "authorization_granted": self.authorization_granted,
            "capability_binding_created": self.capability_binding_created,
            "action_lease_created": self.action_lease_created,
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }
        payload["readiness_sha256"] = _canonical_sha256(payload)
        return payload


class GhostWalkAuthorizationDecisionService:
    """Append explicit decisions for one exact current AuthorityRequest."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        authority_requests: GhostWalkAuthorityRequestService,
        authorizer_id: str,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkAuthorizationDecisionError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._authority_requests = authority_requests
        self.authorizer_id = _require_text(
            authorizer_id,
            "authorizer_id",
            maximum=512,
        )
        self._lock = threading.RLock()

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationReadiness:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        try:
            request = self._authority_requests.latest(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAuthorityRequestError as exc:
            raise GhostWalkAuthorizationDecisionError(str(exc)) from exc
        if request is None:
            return GhostWalkAuthorizationReadiness(
                target_inference_receipt_sha256=target,
                authority_request_sha256=None,
                latest_decision_sha256=None,
                latest_decision=None,
                ready=False,
                reason=(
                    GhostWalkAuthorizationReadinessReason
                    .AUTHORITY_REQUEST_REQUIRED
                ),
                authorization_granted=False,
            )

        try:
            request_readiness = self._authority_requests.readiness(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAuthorityRequestError as exc:
            raise GhostWalkAuthorizationDecisionError(str(exc)) from exc
        if (
            request_readiness.reason
            is not GhostWalkAuthorityRequestReadinessReason.REQUEST_ALREADY_EXISTS
            or (
                request_readiness.existing_authority_request_sha256
                != request.authority_request_sha256
            )
        ):
            return GhostWalkAuthorizationReadiness(
                target_inference_receipt_sha256=target,
                authority_request_sha256=request.authority_request_sha256,
                latest_decision_sha256=None,
                latest_decision=None,
                ready=False,
                reason=(
                    GhostWalkAuthorizationReadinessReason
                    .AUTHORITY_REQUEST_STALE
                ),
                authorization_granted=False,
            )

        chain = self._decision_chain(request)
        latest = chain[-1] if chain else None
        if latest is not None and latest.request_resolved:
            return GhostWalkAuthorizationReadiness(
                target_inference_receipt_sha256=target,
                authority_request_sha256=request.authority_request_sha256,
                latest_decision_sha256=(
                    latest.authorization_decision_sha256
                ),
                latest_decision=latest.decision.value,
                ready=False,
                reason=GhostWalkAuthorizationReadinessReason.DECISION_FINAL,
                authorization_granted=latest.authorization_granted,
            )
        return GhostWalkAuthorizationReadiness(
            target_inference_receipt_sha256=target,
            authority_request_sha256=request.authority_request_sha256,
            latest_decision_sha256=(
                None
                if latest is None
                else latest.authorization_decision_sha256
            ),
            latest_decision=(
                None if latest is None else latest.decision.value
            ),
            ready=True,
            reason=GhostWalkAuthorizationReadinessReason.READY,
            authorization_granted=False,
        )

    def record(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authority_request_sha256: str,
        expected_previous_decision_sha256: str | None,
        decision: GhostWalkAuthorizationDecisionKind,
        decision_note: str | None = None,
        decided_at: str | None = None,
    ) -> GhostWalkAuthorizationDecision:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        expected_request = _require_sha256(
            expected_authority_request_sha256,
            "expected_authority_request_sha256",
        )
        expected_previous = _optional_sha256(
            expected_previous_decision_sha256,
            "expected_previous_decision_sha256",
        )
        if not isinstance(decision, GhostWalkAuthorizationDecisionKind):
            try:
                decision = GhostWalkAuthorizationDecisionKind(decision)
            except (TypeError, ValueError) as exc:
                raise GhostWalkAuthorizationDecisionError(
                    "decision is unsupported"
                ) from exc
        note = _optional_note(decision_note)
        timestamp = _require_timestamp(
            _utc_now() if decided_at is None else decided_at,
            "decided_at",
        )

        with self._lock:
            readiness = self.readiness(
                target_inference_receipt_sha256=target
            )
            if not readiness.ready:
                raise GhostWalkAuthorizationDecisionError(
                    f"authorization decision not ready: {readiness.reason.value}"
                )
            if readiness.authority_request_sha256 != expected_request:
                raise GhostWalkAuthorizationDecisionError(
                    "AuthorityRequest changed before authorization decision"
                )
            if readiness.latest_decision_sha256 != expected_previous:
                raise GhostWalkAuthorizationDecisionError(
                    "authorization decision history changed before record"
                )
            try:
                request = self._authority_requests.latest(
                    target_inference_receipt_sha256=target
                )
            except GhostWalkAuthorityRequestError as exc:
                raise GhostWalkAuthorizationDecisionError(str(exc)) from exc
            if (
                request is None
                or request.authority_request_sha256 != expected_request
            ):
                raise GhostWalkAuthorizationDecisionError(
                    "AuthorityRequest disappeared before authorization decision"
                )
            chain = self._decision_chain(request)
            previous = chain[-1] if chain else None
            item = GhostWalkAuthorizationDecision(
                authority_request_sha256=request.authority_request_sha256,
                target_inference_receipt_sha256=(
                    request.target_inference_receipt_sha256
                ),
                admission_receipt_sha256=request.admission_receipt_sha256,
                accepted_intent_revision_sha256=(
                    request.accepted_intent_revision_sha256
                ),
                policy_profile_sha256=request.policy_profile_sha256,
                intent_code=request.intent_code,
                authorizer_id=self.authorizer_id,
                decision=decision,
                decision_sequence=len(chain),
                previous_decision_sha256=(
                    None
                    if previous is None
                    else previous.authorization_decision_sha256
                ),
                decided_at=timestamp,
                decision_note=note,
                authorization_granted=(
                    decision is GhostWalkAuthorizationDecisionKind.APPROVE
                ),
                request_resolved=decision in {
                    GhostWalkAuthorizationDecisionKind.APPROVE,
                    GhostWalkAuthorizationDecisionKind.DENY,
                },
            )
            self._ledger.append_ghostwalk_authorization_decision(item)
            return item

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationDecision | None:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        try:
            request = self._authority_requests.latest(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAuthorityRequestError as exc:
            raise GhostWalkAuthorizationDecisionError(str(exc)) from exc
        if request is None:
            return None
        chain = self._decision_chain(request)
        return chain[-1] if chain else None

    def _decision_chain(
        self,
        request: GhostWalkAuthorityRequest,
    ) -> list[GhostWalkAuthorizationDecision]:
        rows = self._ledger.ghostwalk_authorization_decisions(
            authority_request_sha256=request.authority_request_sha256
        )
        chain: list[GhostWalkAuthorizationDecision] = []
        previous_sha: str | None = None
        for index, row in enumerate(rows):
            try:
                item = GhostWalkAuthorizationDecision.from_dict(row)
            except GhostWalkAuthorizationDecisionError as exc:
                raise GhostWalkAuthorizationDecisionError(
                    "persisted AuthorizationDecision is invalid"
                ) from exc
            self._validate_decision_provenance(item, request)
            if item.decision_sequence != index:
                raise GhostWalkAuthorizationDecisionError(
                    "AuthorizationDecision sequence is not contiguous"
                )
            if item.previous_decision_sha256 != previous_sha:
                raise GhostWalkAuthorizationDecisionError(
                    "AuthorizationDecision hash chain mismatch"
                )
            if chain and chain[-1].request_resolved:
                raise GhostWalkAuthorizationDecisionError(
                    "AuthorizationDecision exists after terminal decision"
                )
            chain.append(item)
            previous_sha = item.authorization_decision_sha256
        return chain

    @staticmethod
    def _validate_decision_provenance(
        item: GhostWalkAuthorizationDecision,
        request: GhostWalkAuthorityRequest,
    ) -> None:
        expected = (
            ("authority_request_sha256", item.authority_request_sha256, request.authority_request_sha256),
            (
                "target_inference_receipt_sha256",
                item.target_inference_receipt_sha256,
                request.target_inference_receipt_sha256,
            ),
            (
                "admission_receipt_sha256",
                item.admission_receipt_sha256,
                request.admission_receipt_sha256,
            ),
            (
                "accepted_intent_revision_sha256",
                item.accepted_intent_revision_sha256,
                request.accepted_intent_revision_sha256,
            ),
            (
                "policy_profile_sha256",
                item.policy_profile_sha256,
                request.policy_profile_sha256,
            ),
            ("intent_code", item.intent_code, request.intent_code),
        )
        for field, actual, wanted in expected:
            if actual != wanted:
                raise GhostWalkAuthorizationDecisionError(
                    f"AuthorizationDecision {field} does not match AuthorityRequest"
                )
