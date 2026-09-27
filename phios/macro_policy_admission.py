"""Fail-closed Ghost-Walk policy admission for Macro Runtime v0.30.

Policy admission answers one narrow question: whether the current accepted intent
is eligible to proceed to a *later* authority-request step.

Admission never creates an EffectIntent, AuthorityEpoch, ActionLease, execution
handoff, or desktop effect.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentError,
    GhostWalkAcceptedIntentRegistry,
    GhostWalkAcceptedIntentRevision,
    GhostWalkAcceptedIntentStatus,
)
from phios.macro_ghostwalk_operator_editor import (
    GhostWalkOperatorEditor,
    GhostWalkOperatorEditorError,
)
from phios.macro_operator_log import OperatorNoteStatus
from phios.spine.ledger import RealityLedger

GHOSTWALK_POLICY_PROFILE_SCHEMA_VERSION = (
    "phios.ghostwalk_policy_profile.v0.30"
)
GHOSTWALK_POLICY_ADMISSION_PROJECTION_SCHEMA_VERSION = (
    "phios.ghostwalk_policy_admission_projection.v0.30"
)
GHOSTWALK_POLICY_ADMISSION_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_policy_admission_receipt.v0.30"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INTENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


class GhostWalkPolicyAdmissionError(ValueError):
    """Raised when policy admission evidence or configuration is invalid."""


class GhostWalkPolicyDecision(StrEnum):
    ALLOW_REQUEST = "ALLOW_REQUEST"
    HOLD = "HOLD"
    DENY = "DENY"


class GhostWalkPolicyReason(StrEnum):
    INTENT_EXPLICITLY_ALLOWED = "INTENT_EXPLICITLY_ALLOWED"
    INTENT_EXPLICITLY_DENIED = "INTENT_EXPLICITLY_DENIED"
    INTENT_UNMAPPED = "INTENT_UNMAPPED"
    ACCEPTED_INTENT_REVOKED = "ACCEPTED_INTENT_REVOKED"
    OPERATOR_NOTE_RETRACTED = "OPERATOR_NOTE_RETRACTED"
    STALE_OPERATOR_BINDING = "STALE_OPERATOR_BINDING"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkPolicyAdmissionError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkPolicyAdmissionError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkPolicyAdmissionError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkPolicyAdmissionError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkPolicyAdmissionError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkPolicyAdmissionError(
            f"{field} must include a timezone"
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
        raise GhostWalkPolicyAdmissionError(
            "policy-admission payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_codes(
    values: tuple[str, ...],
    field: str,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        code = _require_text(value, f"{field} item", maximum=128)
        if not _INTENT_CODE_RE.fullmatch(code):
            raise GhostWalkPolicyAdmissionError(
                f"{field} items must be uppercase symbolic intent codes"
            )
        normalized.append(code)
    canonical = tuple(sorted(set(normalized)))
    if canonical != values:
        raise GhostWalkPolicyAdmissionError(
            f"{field} must be sorted and unique"
        )
    return canonical


def _parse_csv_codes(raw: str | None) -> tuple[str, ...]:
    if raw is None or raw.strip() == "":
        return ()
    values = tuple(
        sorted(
            {
                item.strip().upper()
                for item in raw.split(",")
                if item.strip()
            }
        )
    )
    return _canonical_codes(values, "policy codes")


@dataclass(frozen=True, slots=True)
class GhostWalkPolicyProfile:
    profile_id: str
    allow_request_intent_codes: tuple[str, ...]
    deny_intent_codes: tuple[str, ...]
    default_decision: GhostWalkPolicyDecision = GhostWalkPolicyDecision.HOLD
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_POLICY_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_POLICY_PROFILE_SCHEMA_VERSION:
            raise GhostWalkPolicyAdmissionError(
                "unsupported Ghost-Walk policy profile schema"
            )
        _require_text(self.profile_id, "profile_id", maximum=512)
        _canonical_codes(
            self.allow_request_intent_codes,
            "allow_request_intent_codes",
        )
        _canonical_codes(self.deny_intent_codes, "deny_intent_codes")
        if set(self.allow_request_intent_codes).intersection(
            self.deny_intent_codes
        ):
            raise GhostWalkPolicyAdmissionError(
                "policy allow and deny intent sets must not overlap"
            )
        if self.default_decision is not GhostWalkPolicyDecision.HOLD:
            raise GhostWalkPolicyAdmissionError(
                "v0.30 policy default must fail closed as HOLD"
            )
        if (
            self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkPolicyAdmissionError(
                "policy profile cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "allow_request_intent_codes": list(
                self.allow_request_intent_codes
            ),
            "deny_intent_codes": list(self.deny_intent_codes),
            "default_decision": self.default_decision.value,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def profile_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["profile_sha256"] = self.profile_sha256
        return payload

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str],
        *,
        profile_id: str = "ghostwalk-policy:local",
    ) -> "GhostWalkPolicyProfile":
        return cls(
            profile_id=profile_id,
            allow_request_intent_codes=_parse_csv_codes(
                env.get("PHIOS_GHOSTWALK_POLICY_ALLOW_REQUEST")
            ),
            deny_intent_codes=_parse_csv_codes(
                env.get("PHIOS_GHOSTWALK_POLICY_DENY")
            ),
        )


@dataclass(frozen=True, slots=True)
class GhostWalkPolicyAdmissionProjection:
    target_inference_receipt_sha256: str
    accepted_intent_revision_sha256: str
    source_operator_note_revision_sha256: str
    current_operator_note_revision_sha256: str
    policy_profile_sha256: str
    intent_family: str
    intent_code: str
    accepted_intent_status: str
    operator_binding_current: bool
    decision: GhostWalkPolicyDecision
    reason: GhostWalkPolicyReason
    request_authority_eligible: bool
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = (
        GHOSTWALK_POLICY_ADMISSION_PROJECTION_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GHOSTWALK_POLICY_ADMISSION_PROJECTION_SCHEMA_VERSION
        ):
            raise GhostWalkPolicyAdmissionError(
                "unsupported policy admission projection schema"
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
            (
                "source_operator_note_revision_sha256",
                self.source_operator_note_revision_sha256,
            ),
            (
                "current_operator_note_revision_sha256",
                self.current_operator_note_revision_sha256,
            ),
            ("policy_profile_sha256", self.policy_profile_sha256),
        ):
            _require_sha256(digest, field)
        _require_text(self.intent_family, "intent_family", maximum=64)
        code = _require_text(self.intent_code, "intent_code", maximum=128)
        if not _INTENT_CODE_RE.fullmatch(code):
            raise GhostWalkPolicyAdmissionError(
                "intent_code must be an uppercase symbolic identifier"
            )
        _require_text(
            self.accepted_intent_status,
            "accepted_intent_status",
            maximum=64,
        )
        if self.request_authority_eligible is not (
            self.decision is GhostWalkPolicyDecision.ALLOW_REQUEST
        ):
            raise GhostWalkPolicyAdmissionError(
                "request_authority_eligible must match ALLOW_REQUEST decision"
            )
        if (
            self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkPolicyAdmissionError(
                "policy admission projection cannot carry authority or effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "accepted_intent_revision_sha256": (
                self.accepted_intent_revision_sha256
            ),
            "source_operator_note_revision_sha256": (
                self.source_operator_note_revision_sha256
            ),
            "current_operator_note_revision_sha256": (
                self.current_operator_note_revision_sha256
            ),
            "policy_profile_sha256": self.policy_profile_sha256,
            "intent_family": self.intent_family,
            "intent_code": self.intent_code,
            "accepted_intent_status": self.accepted_intent_status,
            "operator_binding_current": self.operator_binding_current,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "request_authority_eligible": (
                self.request_authority_eligible
            ),
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def projection_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["projection_sha256"] = self.projection_sha256
        return payload


@dataclass(frozen=True, slots=True)
class GhostWalkPolicyAdmissionReceipt:
    projection_sha256: str
    target_inference_receipt_sha256: str
    accepted_intent_revision_sha256: str
    policy_profile_sha256: str
    decision: GhostWalkPolicyDecision
    reason: GhostWalkPolicyReason
    request_authority_eligible: bool
    evaluated_at: str
    effect_performed: bool = True
    desktop_effect_performed: bool = False
    authority_request_created: bool = False
    action_lease_created: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = (
        GHOSTWALK_POLICY_ADMISSION_RECEIPT_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GHOSTWALK_POLICY_ADMISSION_RECEIPT_SCHEMA_VERSION
        ):
            raise GhostWalkPolicyAdmissionError(
                "unsupported policy admission receipt schema"
            )
        for field, digest in (
            ("projection_sha256", self.projection_sha256),
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
        _require_timestamp(self.evaluated_at, "evaluated_at")
        if self.request_authority_eligible is not (
            self.decision is GhostWalkPolicyDecision.ALLOW_REQUEST
        ):
            raise GhostWalkPolicyAdmissionError(
                "receipt request eligibility must match decision"
            )
        if self.effect_performed is not True:
            raise GhostWalkPolicyAdmissionError(
                "recorded admission receipt must acknowledge persistence effect"
            )
        if (
            self.desktop_effect_performed
            or self.authority_request_created
            or self.action_lease_created
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkPolicyAdmissionError(
                "policy admission receipt cannot create authority or desktop effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "projection_sha256": self.projection_sha256,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "accepted_intent_revision_sha256": (
                self.accepted_intent_revision_sha256
            ),
            "policy_profile_sha256": self.policy_profile_sha256,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "request_authority_eligible": (
                self.request_authority_eligible
            ),
            "evaluated_at": self.evaluated_at,
            "effect_performed": self.effect_performed,
            "desktop_effect_performed": self.desktop_effect_performed,
            "authority_request_created": self.authority_request_created,
            "action_lease_created": self.action_lease_created,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def admission_receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["admission_receipt_sha256"] = (
            self.admission_receipt_sha256
        )
        return payload


    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkPolicyAdmissionReceipt":
        expected = {
            "schema_version",
            "projection_sha256",
            "target_inference_receipt_sha256",
            "accepted_intent_revision_sha256",
            "policy_profile_sha256",
            "decision",
            "reason",
            "request_authority_eligible",
            "evaluated_at",
            "effect_performed",
            "desktop_effect_performed",
            "authority_request_created",
            "action_lease_created",
            "policy_authority",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "admission_receipt_sha256",
        }
        if set(payload) != expected:
            raise GhostWalkPolicyAdmissionError(
                "policy admission receipt fields do not match contract"
            )
        claimed = _require_sha256(
            payload.get("admission_receipt_sha256"),
            "admission_receipt_sha256",
        )
        for field in (
            "request_authority_eligible",
            "effect_performed",
            "desktop_effect_performed",
            "authority_request_created",
            "action_lease_created",
            "policy_authority",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(payload.get(field), bool):
                raise GhostWalkPolicyAdmissionError(
                    f"{field} must be Boolean"
                )
        try:
            decision = GhostWalkPolicyDecision(
                _require_text(
                    payload.get("decision"),
                    "decision",
                    maximum=64,
                )
            )
            reason = GhostWalkPolicyReason(
                _require_text(
                    payload.get("reason"),
                    "reason",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise GhostWalkPolicyAdmissionError(
                "policy admission receipt enum value is unsupported"
            ) from exc

        receipt = cls(
            projection_sha256=_require_sha256(
                payload.get("projection_sha256"),
                "projection_sha256",
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
            decision=decision,
            reason=reason,
            request_authority_eligible=payload[
                "request_authority_eligible"
            ],
            evaluated_at=_require_timestamp(
                payload.get("evaluated_at"),
                "evaluated_at",
            ),
            effect_performed=payload["effect_performed"],
            desktop_effect_performed=payload[
                "desktop_effect_performed"
            ],
            authority_request_created=payload[
                "authority_request_created"
            ],
            action_lease_created=payload["action_lease_created"],
            policy_authority=payload["policy_authority"],
            operational_authority=payload["operational_authority"],
            action_authority=payload["action_authority"],
            execution_authority=payload["execution_authority"],
            schema_version=_require_text(
                payload.get("schema_version"),
                "schema_version",
                maximum=128,
            ),
        )
        if receipt.admission_receipt_sha256 != claimed:
            raise GhostWalkPolicyAdmissionError(
                "policy admission receipt hash mismatch"
            )
        return receipt


class GhostWalkPolicyAdmissionService:
    """Evaluate accepted intent against server-owned, fail-closed policy."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        accepted_intents: GhostWalkAcceptedIntentRegistry,
        operator_editor: GhostWalkOperatorEditor,
        profile: GhostWalkPolicyProfile,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkPolicyAdmissionError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._accepted_intents = accepted_intents
        self._operator_editor = operator_editor
        self.profile = profile

    def project(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkPolicyAdmissionProjection:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        try:
            accepted = self._accepted_intents.current(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAcceptedIntentError as exc:
            raise GhostWalkPolicyAdmissionError(str(exc)) from exc
        if accepted is None:
            raise GhostWalkPolicyAdmissionError(
                "accepted intent does not exist"
            )

        try:
            note = self._operator_editor.view(
                target_inference_receipt_sha256=target
            )
        except GhostWalkOperatorEditorError as exc:
            raise GhostWalkPolicyAdmissionError(str(exc)) from exc

        binding_current = (
            note.revision_sha256
            == accepted.source_operator_note_revision_sha256
        )
        decision, reason = self._decide(
            accepted=accepted,
            operator_note_active=(
                note.status is OperatorNoteStatus.ACTIVE
            ),
            binding_current=binding_current,
        )
        return GhostWalkPolicyAdmissionProjection(
            target_inference_receipt_sha256=target,
            accepted_intent_revision_sha256=(
                accepted.revision_sha256
            ),
            source_operator_note_revision_sha256=(
                accepted.source_operator_note_revision_sha256
            ),
            current_operator_note_revision_sha256=(
                note.revision_sha256
            ),
            policy_profile_sha256=self.profile.profile_sha256,
            intent_family=accepted.intent_family.value,
            intent_code=accepted.intent_code,
            accepted_intent_status=accepted.status.value,
            operator_binding_current=binding_current,
            decision=decision,
            reason=reason,
            request_authority_eligible=(
                decision is GhostWalkPolicyDecision.ALLOW_REQUEST
            ),
        )

    def record(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_accepted_intent_revision_sha256: str,
        expected_policy_profile_sha256: str,
        evaluated_at: str | None = None,
    ) -> GhostWalkPolicyAdmissionReceipt:
        expected_intent = _require_sha256(
            expected_accepted_intent_revision_sha256,
            "expected_accepted_intent_revision_sha256",
        )
        expected_profile = _require_sha256(
            expected_policy_profile_sha256,
            "expected_policy_profile_sha256",
        )
        if expected_profile != self.profile.profile_sha256:
            raise GhostWalkPolicyAdmissionError(
                "policy profile changed before admission record"
            )

        projection = self.project(
            target_inference_receipt_sha256=(
                target_inference_receipt_sha256
            )
        )
        if projection.accepted_intent_revision_sha256 != expected_intent:
            raise GhostWalkPolicyAdmissionError(
                "accepted intent changed before admission record"
            )

        receipt = GhostWalkPolicyAdmissionReceipt(
            projection_sha256=projection.projection_sha256,
            target_inference_receipt_sha256=(
                projection.target_inference_receipt_sha256
            ),
            accepted_intent_revision_sha256=(
                projection.accepted_intent_revision_sha256
            ),
            policy_profile_sha256=projection.policy_profile_sha256,
            decision=projection.decision,
            reason=projection.reason,
            request_authority_eligible=(
                projection.request_authority_eligible
            ),
            evaluated_at=_require_timestamp(
                _utc_now() if evaluated_at is None else evaluated_at,
                "evaluated_at",
            ),
        )
        self._ledger.append_ghostwalk_policy_admission_receipt(receipt)
        return receipt

    def _decide(
        self,
        *,
        accepted: GhostWalkAcceptedIntentRevision,
        operator_note_active: bool,
        binding_current: bool,
    ) -> tuple[GhostWalkPolicyDecision, GhostWalkPolicyReason]:
        if accepted.status is GhostWalkAcceptedIntentStatus.REVOKED:
            return (
                GhostWalkPolicyDecision.HOLD,
                GhostWalkPolicyReason.ACCEPTED_INTENT_REVOKED,
            )
        if not operator_note_active:
            return (
                GhostWalkPolicyDecision.HOLD,
                GhostWalkPolicyReason.OPERATOR_NOTE_RETRACTED,
            )
        if not binding_current:
            return (
                GhostWalkPolicyDecision.HOLD,
                GhostWalkPolicyReason.STALE_OPERATOR_BINDING,
            )
        if accepted.intent_code in self.profile.deny_intent_codes:
            return (
                GhostWalkPolicyDecision.DENY,
                GhostWalkPolicyReason.INTENT_EXPLICITLY_DENIED,
            )
        if (
            accepted.intent_code
            in self.profile.allow_request_intent_codes
        ):
            return (
                GhostWalkPolicyDecision.ALLOW_REQUEST,
                GhostWalkPolicyReason.INTENT_EXPLICITLY_ALLOWED,
            )
        return (
            self.profile.default_decision,
            GhostWalkPolicyReason.INTENT_UNMAPPED,
        )
