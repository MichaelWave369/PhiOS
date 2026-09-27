"""Deterministic Ghost-Walk capability/effect binding for Macro Runtime v0.33.

This module bridges one exact current APPROVE AuthorizationDecision to one exact
executable representation. It does not issue ActionLeases and does not execute
effects.

The binding is derived from:
- the approved semantic intent,
- a server-owned mapping registry,
- the exact demonstrated Ghost-Walk observation bound through transition
  inference.

No browser-supplied capability, payload, permission, or effect data is accepted.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from phios.effect_intent import EffectIntent, EffectIntentContractError
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecision,
    GhostWalkAuthorizationDecisionError,
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationDecisionService,
    GhostWalkAuthorizationReadinessReason,
)
from phios.macro_desktop_interaction import (
    DESKTOP_CLICK_CAPABILITY_ID,
    DESKTOP_CLICK_CAPABILITY_VERSION,
    DesktopClickRequest,
    DesktopInteractionContractError,
)
from phios.macro_ghostwalk import (
    GhostWalkActionKind,
    GhostWalkContractError,
    GhostWalkObservation,
    TargetStrategy,
)
from phios.spine.effects import (
    EffectBoundaryContractError,
    normalize_effects,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_CAPABILITY_MAPPING_SCHEMA_VERSION = (
    "phios.ghostwalk_capability_mapping.v0.33"
)
GHOSTWALK_EXECUTABLE_BINDING_SCHEMA_VERSION = (
    "phios.ghostwalk_executable_binding.v0.33"
)
GHOSTWALK_BINDING_READINESS_SCHEMA_VERSION = (
    "phios.ghostwalk_binding_readiness.v0.33"
)

DESKTOP_CLICK_PERMISSIONS = ("ui.interact",)
DESKTOP_CLICK_EFFECTS = ("display.control", "filesystem.change")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INTENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_MAPPING_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class GhostWalkCapabilityBindingError(ValueError):
    """Raised when an executable Ghost-Walk binding cannot be trusted."""


class GhostWalkBindingReadinessReason(StrEnum):
    READY = "READY"
    AUTHORIZATION_DECISION_REQUIRED = "AUTHORIZATION_DECISION_REQUIRED"
    AUTHORIZATION_NOT_APPROVED = "AUTHORIZATION_NOT_APPROVED"
    AUTHORIZATION_STALE = "AUTHORIZATION_STALE"
    NO_MAPPING = "NO_MAPPING"
    AMBIGUOUS_MAPPING = "AMBIGUOUS_MAPPING"
    ACTION_EVIDENCE_MISSING = "ACTION_EVIDENCE_MISSING"
    MAPPING_CONSTRAINT_MISMATCH = "MAPPING_CONSTRAINT_MISMATCH"
    BINDING_ALREADY_EXISTS = "BINDING_ALREADY_EXISTS"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkCapabilityBindingError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkCapabilityBindingError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkCapabilityBindingError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkCapabilityBindingError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkCapabilityBindingError(
            f"{field} must be Boolean"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkCapabilityBindingError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GhostWalkCapabilityBindingError(
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
        raise GhostWalkCapabilityBindingError(
            "capability binding payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_text_tuple(
    values: tuple[str, ...],
    field: str,
) -> tuple[str, ...]:
    normalized = tuple(
        _require_text(item, f"{field} item", maximum=256)
        for item in values
    )
    if tuple(sorted(set(normalized))) != normalized:
        raise GhostWalkCapabilityBindingError(
            f"{field} must be sorted and unique"
        )
    return normalized


def _canonical_effects(values: tuple[str, ...]) -> tuple[str, ...]:
    try:
        effects = normalize_effects(
            values,
            label="Ghost-Walk mapping effects",
        )
    except EffectBoundaryContractError as exc:
        raise GhostWalkCapabilityBindingError(str(exc)) from exc
    if effects != values:
        raise GhostWalkCapabilityBindingError(
            "effects_declared must be sorted, unique, and canonical"
        )
    if "unknown" in effects or effects == ("none",):
        raise GhostWalkCapabilityBindingError(
            "executable binding cannot use unknown or none effects"
        )
    return effects


def _pixel_anchor_dict(
    observation: GhostWalkObservation,
) -> dict[str, object]:
    payload = observation.pixel_anchor.body_dict()
    payload["anchor_sha256"] = observation.pixel_anchor.anchor_sha256
    return payload


def _desktop_click_payload(
    observation: GhostWalkObservation,
) -> dict[str, object]:
    target = observation.semantic_target
    payload: dict[str, object] = {
        "observation_sha256": observation.observation_sha256,
        "preferred_strategy": observation.preferred_strategy.value,
        "process_id": observation.pixel_anchor.process_id,
        "window_title_sha256": (
            observation.pixel_anchor.window_title_sha256
        ),
        "pixel_anchor": _pixel_anchor_dict(observation),
        "semantic_target": (
            None if target is None else target.to_dict()
        ),
        "absolute_pixel_is_evidence_only": True,
        "guard_required": True,
    }
    try:
        DesktopClickRequest.from_payload(payload)
    except DesktopInteractionContractError as exc:
        raise GhostWalkCapabilityBindingError(
            "demonstrated click cannot form a valid desktop click payload"
        ) from exc
    return payload


@dataclass(frozen=True, slots=True)
class GhostWalkCapabilityMapping:
    """One server-owned semantic-intent to capability mapping."""

    mapping_id: str
    intent_code: str
    action_kind: GhostWalkActionKind
    required_target_strategy: TargetStrategy
    capability_id: str
    capability_version: str
    permissions_required: tuple[str, ...]
    effects_declared: tuple[str, ...]
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_CAPABILITY_MAPPING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_CAPABILITY_MAPPING_SCHEMA_VERSION:
            raise GhostWalkCapabilityBindingError(
                "unsupported capability mapping schema"
            )
        if not _MAPPING_ID_RE.fullmatch(self.mapping_id):
            raise GhostWalkCapabilityBindingError(
                "mapping_id must be a canonical lowercase identifier"
            )
        if not _INTENT_CODE_RE.fullmatch(self.intent_code):
            raise GhostWalkCapabilityBindingError(
                "intent_code must be an uppercase symbolic identifier"
            )
        _require_text(self.capability_id, "capability_id", maximum=256)
        _require_text(
            self.capability_version,
            "capability_version",
            maximum=128,
        )
        _canonical_text_tuple(
            self.permissions_required,
            "permissions_required",
        )
        if not self.permissions_required:
            raise GhostWalkCapabilityBindingError(
                "permissions_required must not be empty"
            )
        _canonical_effects(self.effects_declared)

        if self.capability_id != DESKTOP_CLICK_CAPABILITY_ID:
            raise GhostWalkCapabilityBindingError(
                "v0.33 supports only the governed desktop click capability"
            )
        if self.capability_version != DESKTOP_CLICK_CAPABILITY_VERSION:
            raise GhostWalkCapabilityBindingError(
                "desktop click mapping version does not match runtime"
            )
        if self.action_kind is not GhostWalkActionKind.CLICK:
            raise GhostWalkCapabilityBindingError(
                "desktop click mapping requires CLICK action evidence"
            )
        if self.permissions_required != DESKTOP_CLICK_PERMISSIONS:
            raise GhostWalkCapabilityBindingError(
                "desktop click mapping permissions do not match runtime"
            )
        if self.effects_declared != DESKTOP_CLICK_EFFECTS:
            raise GhostWalkCapabilityBindingError(
                "desktop click mapping effects do not match runtime"
            )
        if (
            self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkCapabilityBindingError(
                "capability mapping cannot carry effects or authority"
            )

    @classmethod
    def desktop_click(
        cls,
        *,
        mapping_id: str,
        intent_code: str,
        required_target_strategy: TargetStrategy,
    ) -> "GhostWalkCapabilityMapping":
        return cls(
            mapping_id=mapping_id,
            intent_code=intent_code,
            action_kind=GhostWalkActionKind.CLICK,
            required_target_strategy=required_target_strategy,
            capability_id=DESKTOP_CLICK_CAPABILITY_ID,
            capability_version=DESKTOP_CLICK_CAPABILITY_VERSION,
            permissions_required=DESKTOP_CLICK_PERMISSIONS,
            effects_declared=DESKTOP_CLICK_EFFECTS,
        )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mapping_id": self.mapping_id,
            "intent_code": self.intent_code,
            "action_kind": self.action_kind.value,
            "required_target_strategy": (
                self.required_target_strategy.value
            ),
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "permissions_required": list(self.permissions_required),
            "effects_declared": list(self.effects_declared),
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def mapping_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["mapping_sha256"] = self.mapping_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkCapabilityMapping":
        expected = {
            "schema_version",
            "mapping_id",
            "intent_code",
            "action_kind",
            "required_target_strategy",
            "capability_id",
            "capability_version",
            "permissions_required",
            "effects_declared",
            "effect_performed",
            "policy_authority",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "mapping_sha256",
        }
        if set(payload) != expected:
            raise GhostWalkCapabilityBindingError(
                "capability mapping fields do not match contract"
            )
        claimed = _require_sha256(
            payload.get("mapping_sha256"),
            "mapping_sha256",
        )
        permissions_raw = payload.get("permissions_required")
        effects_raw = payload.get("effects_declared")
        if not isinstance(permissions_raw, list):
            raise GhostWalkCapabilityBindingError(
                "permissions_required must be an array"
            )
        if not isinstance(effects_raw, list):
            raise GhostWalkCapabilityBindingError(
                "effects_declared must be an array"
            )
        try:
            action_kind = GhostWalkActionKind(
                _require_text(
                    payload.get("action_kind"),
                    "action_kind",
                    maximum=64,
                )
            )
            strategy = TargetStrategy(
                _require_text(
                    payload.get("required_target_strategy"),
                    "required_target_strategy",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise GhostWalkCapabilityBindingError(
                "capability mapping enum value is unsupported"
            ) from exc
        item = cls(
            mapping_id=_require_text(
                payload.get("mapping_id"),
                "mapping_id",
                maximum=128,
            ),
            intent_code=_require_text(
                payload.get("intent_code"),
                "intent_code",
                maximum=128,
            ),
            action_kind=action_kind,
            required_target_strategy=strategy,
            capability_id=_require_text(
                payload.get("capability_id"),
                "capability_id",
                maximum=256,
            ),
            capability_version=_require_text(
                payload.get("capability_version"),
                "capability_version",
                maximum=128,
            ),
            permissions_required=tuple(
                _require_text(
                    value,
                    "permissions_required item",
                    maximum=256,
                )
                for value in permissions_raw
            ),
            effects_declared=tuple(
                _require_text(
                    value,
                    "effects_declared item",
                    maximum=64,
                )
                for value in effects_raw
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
        if item.mapping_sha256 != claimed:
            raise GhostWalkCapabilityBindingError(
                "capability mapping hash mismatch"
            )
        return item


class GhostWalkCapabilityMappingRegistry:
    """Immutable server-owned mapping set."""

    def __init__(
        self,
        mappings: tuple[GhostWalkCapabilityMapping, ...] = (),
    ) -> None:
        ordered = tuple(sorted(mappings, key=lambda item: item.mapping_id))
        ids = tuple(item.mapping_id for item in ordered)
        if len(set(ids)) != len(ids):
            raise GhostWalkCapabilityBindingError(
                "capability mapping IDs must be unique"
            )
        self._mappings = ordered
        self.mapping_set_sha256 = _canonical_sha256(
            [item.to_dict() for item in self._mappings]
        )

    @property
    def mappings(self) -> tuple[GhostWalkCapabilityMapping, ...]:
        return self._mappings

    def for_intent(
        self,
        intent_code: str,
    ) -> tuple[GhostWalkCapabilityMapping, ...]:
        code = _require_text(
            intent_code,
            "intent_code",
            maximum=128,
        )
        return tuple(
            item
            for item in self._mappings
            if item.intent_code == code
        )


@dataclass(frozen=True, slots=True)
class GhostWalkExecutableBinding:
    """Immutable zero-authority executable representation of approved intent."""

    authorization_decision_sha256: str
    authority_request_sha256: str
    target_inference_receipt_sha256: str
    action_observation_sha256: str
    intent_code: str
    mapping_id: str
    mapping_sha256: str
    mapping_set_sha256: str
    capability_id: str
    capability_version: str
    payload: Mapping[str, object]
    payload_sha256: str
    permissions_required: tuple[str, ...]
    effects_declared: tuple[str, ...]
    effect_intent: EffectIntent
    bound_at: str
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_EXECUTABLE_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_EXECUTABLE_BINDING_SCHEMA_VERSION:
            raise GhostWalkCapabilityBindingError(
                "unsupported executable binding schema"
            )
        for field, digest in (
            (
                "authorization_decision_sha256",
                self.authorization_decision_sha256,
            ),
            ("authority_request_sha256", self.authority_request_sha256),
            (
                "target_inference_receipt_sha256",
                self.target_inference_receipt_sha256,
            ),
            ("action_observation_sha256", self.action_observation_sha256),
            ("mapping_sha256", self.mapping_sha256),
            ("mapping_set_sha256", self.mapping_set_sha256),
            ("payload_sha256", self.payload_sha256),
        ):
            _require_sha256(digest, field)
        if not _INTENT_CODE_RE.fullmatch(self.intent_code):
            raise GhostWalkCapabilityBindingError(
                "intent_code must be an uppercase symbolic identifier"
            )
        if not _MAPPING_ID_RE.fullmatch(self.mapping_id):
            raise GhostWalkCapabilityBindingError(
                "mapping_id must be a canonical lowercase identifier"
            )
        _require_text(self.capability_id, "capability_id", maximum=256)
        _require_text(
            self.capability_version,
            "capability_version",
            maximum=128,
        )
        if not isinstance(self.payload, Mapping):
            raise GhostWalkCapabilityBindingError(
                "binding payload must be an object"
            )
        if _canonical_sha256(dict(self.payload)) != self.payload_sha256:
            raise GhostWalkCapabilityBindingError(
                "payload_sha256 does not match payload"
            )
        _canonical_text_tuple(
            self.permissions_required,
            "permissions_required",
        )
        _canonical_effects(self.effects_declared)
        _require_timestamp(self.bound_at, "bound_at")
        if self.effect_intent.capability_id != self.capability_id:
            raise GhostWalkCapabilityBindingError(
                "EffectIntent capability differs from binding"
            )
        if self.effect_intent.capability_version != self.capability_version:
            raise GhostWalkCapabilityBindingError(
                "EffectIntent version differs from binding"
            )
        if self.effect_intent.payload_sha256 != self.payload_sha256:
            raise GhostWalkCapabilityBindingError(
                "EffectIntent payload differs from binding"
            )
        if self.effect_intent.effects_declared != self.effects_declared:
            raise GhostWalkCapabilityBindingError(
                "EffectIntent effects differ from binding"
            )
        if self.effect_intent.declared_at != self.bound_at:
            raise GhostWalkCapabilityBindingError(
                "EffectIntent declaration time differs from binding"
            )
        if (
            self.effect_intent.effect_performed
            or self.effect_intent.operational_authority
            or self.effect_intent.action_authority
            or self.effect_intent.execution_authority
        ):
            raise GhostWalkCapabilityBindingError(
                "bound EffectIntent cannot carry authority or performed effects"
            )
        if (
            self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkCapabilityBindingError(
                "executable binding cannot carry effects or authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authorization_decision_sha256": (
                self.authorization_decision_sha256
            ),
            "authority_request_sha256": self.authority_request_sha256,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "action_observation_sha256": self.action_observation_sha256,
            "intent_code": self.intent_code,
            "mapping_id": self.mapping_id,
            "mapping_sha256": self.mapping_sha256,
            "mapping_set_sha256": self.mapping_set_sha256,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "payload": dict(self.payload),
            "payload_sha256": self.payload_sha256,
            "permissions_required": list(self.permissions_required),
            "effects_declared": list(self.effects_declared),
            "effect_intent": self.effect_intent.to_dict(),
            "bound_at": self.bound_at,
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def executable_binding_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["executable_binding_sha256"] = (
            self.executable_binding_sha256
        )
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkExecutableBinding":
        expected = {
            "schema_version",
            "authorization_decision_sha256",
            "authority_request_sha256",
            "target_inference_receipt_sha256",
            "action_observation_sha256",
            "intent_code",
            "mapping_id",
            "mapping_sha256",
            "mapping_set_sha256",
            "capability_id",
            "capability_version",
            "payload",
            "payload_sha256",
            "permissions_required",
            "effects_declared",
            "effect_intent",
            "bound_at",
            "effect_performed",
            "policy_authority",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "executable_binding_sha256",
        }
        if set(payload) != expected:
            raise GhostWalkCapabilityBindingError(
                "executable binding fields do not match contract"
            )
        claimed = _require_sha256(
            payload.get("executable_binding_sha256"),
            "executable_binding_sha256",
        )
        raw_payload = payload.get("payload")
        permissions_raw = payload.get("permissions_required")
        effects_raw = payload.get("effects_declared")
        effect_intent_raw = payload.get("effect_intent")
        if not isinstance(raw_payload, Mapping):
            raise GhostWalkCapabilityBindingError(
                "binding payload must be an object"
            )
        if not isinstance(permissions_raw, list):
            raise GhostWalkCapabilityBindingError(
                "permissions_required must be an array"
            )
        if not isinstance(effects_raw, list):
            raise GhostWalkCapabilityBindingError(
                "effects_declared must be an array"
            )
        try:
            effect_intent = EffectIntent.from_dict(effect_intent_raw)
        except EffectIntentContractError as exc:
            raise GhostWalkCapabilityBindingError(
                "bound EffectIntent is invalid"
            ) from exc
        item = cls(
            authorization_decision_sha256=_require_sha256(
                payload.get("authorization_decision_sha256"),
                "authorization_decision_sha256",
            ),
            authority_request_sha256=_require_sha256(
                payload.get("authority_request_sha256"),
                "authority_request_sha256",
            ),
            target_inference_receipt_sha256=_require_sha256(
                payload.get("target_inference_receipt_sha256"),
                "target_inference_receipt_sha256",
            ),
            action_observation_sha256=_require_sha256(
                payload.get("action_observation_sha256"),
                "action_observation_sha256",
            ),
            intent_code=_require_text(
                payload.get("intent_code"),
                "intent_code",
                maximum=128,
            ),
            mapping_id=_require_text(
                payload.get("mapping_id"),
                "mapping_id",
                maximum=128,
            ),
            mapping_sha256=_require_sha256(
                payload.get("mapping_sha256"),
                "mapping_sha256",
            ),
            mapping_set_sha256=_require_sha256(
                payload.get("mapping_set_sha256"),
                "mapping_set_sha256",
            ),
            capability_id=_require_text(
                payload.get("capability_id"),
                "capability_id",
                maximum=256,
            ),
            capability_version=_require_text(
                payload.get("capability_version"),
                "capability_version",
                maximum=128,
            ),
            payload=dict(raw_payload),
            payload_sha256=_require_sha256(
                payload.get("payload_sha256"),
                "payload_sha256",
            ),
            permissions_required=tuple(
                _require_text(
                    value,
                    "permissions_required item",
                    maximum=256,
                )
                for value in permissions_raw
            ),
            effects_declared=tuple(
                _require_text(
                    value,
                    "effects_declared item",
                    maximum=64,
                )
                for value in effects_raw
            ),
            effect_intent=effect_intent,
            bound_at=_require_timestamp(
                payload.get("bound_at"),
                "bound_at",
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
        if item.executable_binding_sha256 != claimed:
            raise GhostWalkCapabilityBindingError(
                "executable binding hash mismatch"
            )
        return item


@dataclass(frozen=True, slots=True)
class GhostWalkBindingReadiness:
    target_inference_receipt_sha256: str
    authorization_decision_sha256: str | None
    mapping_set_sha256: str
    selected_mapping_sha256: str | None
    action_observation_sha256: str | None
    existing_binding_sha256: str | None
    ready: bool
    reason: GhostWalkBindingReadinessReason
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_BINDING_READINESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_BINDING_READINESS_SCHEMA_VERSION:
            raise GhostWalkCapabilityBindingError(
                "unsupported binding readiness schema"
            )
        _require_sha256(
            self.target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        _optional_sha256(
            self.authorization_decision_sha256,
            "authorization_decision_sha256",
        )
        _require_sha256(
            self.mapping_set_sha256,
            "mapping_set_sha256",
        )
        _optional_sha256(
            self.selected_mapping_sha256,
            "selected_mapping_sha256",
        )
        _optional_sha256(
            self.action_observation_sha256,
            "action_observation_sha256",
        )
        _optional_sha256(
            self.existing_binding_sha256,
            "existing_binding_sha256",
        )
        if self.ready is not (
            self.reason is GhostWalkBindingReadinessReason.READY
        ):
            raise GhostWalkCapabilityBindingError(
                "binding readiness Boolean must match reason"
            )
        if (
            self.effect_performed
            or self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkCapabilityBindingError(
                "binding readiness cannot carry effects or authority"
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "authorization_decision_sha256": (
                self.authorization_decision_sha256
            ),
            "mapping_set_sha256": self.mapping_set_sha256,
            "selected_mapping_sha256": self.selected_mapping_sha256,
            "action_observation_sha256": self.action_observation_sha256,
            "existing_binding_sha256": self.existing_binding_sha256,
            "ready": self.ready,
            "reason": self.reason.value,
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }
        payload["readiness_sha256"] = _canonical_sha256(payload)
        return payload


class GhostWalkCapabilityBindingService:
    """Create one exact zero-authority executable binding per approval."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        authorization_decisions: GhostWalkAuthorizationDecisionService,
        registry: GhostWalkCapabilityMappingRegistry,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkCapabilityBindingError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._authorization_decisions = authorization_decisions
        self.registry = registry
        self._lock = threading.RLock()

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkBindingReadiness:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        decision = self._current_approved_decision(target)
        if decision is None:
            latest = self._latest_decision(target)
            if latest is None:
                return self._readiness(
                    target=target,
                    reason=(
                        GhostWalkBindingReadinessReason
                        .AUTHORIZATION_DECISION_REQUIRED
                    ),
                )
            try:
                auth = self._authorization_decisions.readiness(
                    target_inference_receipt_sha256=target
                )
            except GhostWalkAuthorizationDecisionError as exc:
                raise GhostWalkCapabilityBindingError(str(exc)) from exc
            if (
                auth.reason
                is GhostWalkAuthorizationReadinessReason
                .AUTHORITY_REQUEST_STALE
            ):
                return self._readiness(
                    target=target,
                    reason=GhostWalkBindingReadinessReason.AUTHORIZATION_STALE,
                    authorization_decision_sha256=(
                        latest.authorization_decision_sha256
                    ),
                )
            return self._readiness(
                target=target,
                reason=(
                    GhostWalkBindingReadinessReason
                    .AUTHORIZATION_NOT_APPROVED
                ),
                authorization_decision_sha256=(
                    latest.authorization_decision_sha256
                ),
            )

        matches = self.registry.for_intent(decision.intent_code)
        if not matches:
            return self._readiness(
                target=target,
                reason=GhostWalkBindingReadinessReason.NO_MAPPING,
                authorization_decision_sha256=(
                    decision.authorization_decision_sha256
                ),
            )
        if len(matches) != 1:
            return self._readiness(
                target=target,
                reason=GhostWalkBindingReadinessReason.AMBIGUOUS_MAPPING,
                authorization_decision_sha256=(
                    decision.authorization_decision_sha256
                ),
            )
        mapping = matches[0]

        observation = self._source_observation(decision)
        if observation is None:
            return self._readiness(
                target=target,
                reason=(
                    GhostWalkBindingReadinessReason
                    .ACTION_EVIDENCE_MISSING
                ),
                authorization_decision_sha256=(
                    decision.authorization_decision_sha256
                ),
                selected_mapping_sha256=mapping.mapping_sha256,
            )
        if (
            observation.action_kind is not mapping.action_kind
            or observation.preferred_strategy
            is not mapping.required_target_strategy
        ):
            return self._readiness(
                target=target,
                reason=(
                    GhostWalkBindingReadinessReason
                    .MAPPING_CONSTRAINT_MISMATCH
                ),
                authorization_decision_sha256=(
                    decision.authorization_decision_sha256
                ),
                selected_mapping_sha256=mapping.mapping_sha256,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )
        if mapping.capability_id == DESKTOP_CLICK_CAPABILITY_ID:
            _desktop_click_payload(observation)

        existing = self._binding_for_decision(
            decision.authorization_decision_sha256
        )
        if existing is not None:
            return self._readiness(
                target=target,
                reason=GhostWalkBindingReadinessReason.BINDING_ALREADY_EXISTS,
                authorization_decision_sha256=(
                    decision.authorization_decision_sha256
                ),
                selected_mapping_sha256=mapping.mapping_sha256,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
                existing_binding_sha256=(
                    existing.executable_binding_sha256
                ),
            )

        return self._readiness(
            target=target,
            reason=GhostWalkBindingReadinessReason.READY,
            authorization_decision_sha256=(
                decision.authorization_decision_sha256
            ),
            selected_mapping_sha256=mapping.mapping_sha256,
            action_observation_sha256=observation.observation_sha256,
        )

    def create(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authorization_decision_sha256: str,
        expected_mapping_sha256: str,
        expected_mapping_set_sha256: str,
        bound_at: str,
    ) -> GhostWalkExecutableBinding:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        expected_decision = _require_sha256(
            expected_authorization_decision_sha256,
            "expected_authorization_decision_sha256",
        )
        expected_mapping = _require_sha256(
            expected_mapping_sha256,
            "expected_mapping_sha256",
        )
        expected_mapping_set = _require_sha256(
            expected_mapping_set_sha256,
            "expected_mapping_set_sha256",
        )
        timestamp = _require_timestamp(bound_at, "bound_at")

        with self._lock:
            readiness = self.readiness(
                target_inference_receipt_sha256=target
            )
            if not readiness.ready:
                raise GhostWalkCapabilityBindingError(
                    f"capability binding not ready: {readiness.reason.value}"
                )
            if (
                readiness.authorization_decision_sha256
                != expected_decision
            ):
                raise GhostWalkCapabilityBindingError(
                    "authorization decision changed before binding"
                )
            if readiness.selected_mapping_sha256 != expected_mapping:
                raise GhostWalkCapabilityBindingError(
                    "capability mapping changed before binding"
                )
            if self.registry.mapping_set_sha256 != expected_mapping_set:
                raise GhostWalkCapabilityBindingError(
                    "capability mapping registry changed before binding"
                )

            decision = self._current_approved_decision(target)
            if decision is None:
                raise GhostWalkCapabilityBindingError(
                    "approved authorization disappeared before binding"
                )
            matches = self.registry.for_intent(decision.intent_code)
            if len(matches) != 1:
                raise GhostWalkCapabilityBindingError(
                    "capability mapping is no longer unique"
                )
            mapping = matches[0]
            observation = self._source_observation(decision)
            if observation is None:
                raise GhostWalkCapabilityBindingError(
                    "demonstrated action evidence disappeared before binding"
                )
            if (
                observation.action_kind is not mapping.action_kind
                or observation.preferred_strategy
                is not mapping.required_target_strategy
            ):
                raise GhostWalkCapabilityBindingError(
                    "demonstrated action no longer satisfies mapping"
                )

            if mapping.capability_id != DESKTOP_CLICK_CAPABILITY_ID:
                raise GhostWalkCapabilityBindingError(
                    "unsupported capability mapping"
                )
            executable_payload = _desktop_click_payload(observation)
            payload_sha256 = _canonical_sha256(executable_payload)
            try:
                effect_intent = EffectIntent.build(
                    capability_id=mapping.capability_id,
                    capability_version=mapping.capability_version,
                    payload_sha256=payload_sha256,
                    declared_at=timestamp,
                    effects_declared=mapping.effects_declared,
                )
            except EffectIntentContractError as exc:
                raise GhostWalkCapabilityBindingError(
                    "EffectIntent construction failed"
                ) from exc

            binding = GhostWalkExecutableBinding(
                authorization_decision_sha256=(
                    decision.authorization_decision_sha256
                ),
                authority_request_sha256=decision.authority_request_sha256,
                target_inference_receipt_sha256=(
                    decision.target_inference_receipt_sha256
                ),
                action_observation_sha256=observation.observation_sha256,
                intent_code=decision.intent_code,
                mapping_id=mapping.mapping_id,
                mapping_sha256=mapping.mapping_sha256,
                mapping_set_sha256=self.registry.mapping_set_sha256,
                capability_id=mapping.capability_id,
                capability_version=mapping.capability_version,
                payload=executable_payload,
                payload_sha256=payload_sha256,
                permissions_required=mapping.permissions_required,
                effects_declared=mapping.effects_declared,
                effect_intent=effect_intent,
                bound_at=timestamp,
            )
            self._ledger.append_ghostwalk_executable_binding(binding)
            return binding

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkExecutableBinding | None:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        rows = self._ledger.ghostwalk_executable_bindings(
            target_inference_receipt_sha256=target
        )
        bindings = [self._parse_binding(row) for row in rows]
        return bindings[-1] if bindings else None

    def _latest_decision(
        self,
        target: str,
    ) -> GhostWalkAuthorizationDecision | None:
        try:
            return self._authorization_decisions.latest(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAuthorizationDecisionError as exc:
            raise GhostWalkCapabilityBindingError(str(exc)) from exc

    def _current_approved_decision(
        self,
        target: str,
    ) -> GhostWalkAuthorizationDecision | None:
        latest = self._latest_decision(target)
        if latest is None:
            return None
        try:
            readiness = self._authorization_decisions.readiness(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAuthorizationDecisionError as exc:
            raise GhostWalkCapabilityBindingError(str(exc)) from exc
        if (
            readiness.reason
            is GhostWalkAuthorizationReadinessReason.DECISION_FINAL
            and readiness.authorization_granted
            and latest.decision is GhostWalkAuthorizationDecisionKind.APPROVE
            and latest.authorization_granted
        ):
            return latest
        return None

    def _source_observation(
        self,
        decision: GhostWalkAuthorizationDecision,
    ) -> GhostWalkObservation | None:
        row = self._ledger.transition_inference_receipt(
            receipt_sha256=decision.target_inference_receipt_sha256
        )
        if row is None:
            return None
        claimed = row.get("receipt_sha256")
        if claimed != decision.target_inference_receipt_sha256:
            raise GhostWalkCapabilityBindingError(
                "transition inference receipt identity changed"
            )
        body = dict(row)
        body.pop("receipt_sha256", None)
        if _canonical_sha256(body) != claimed:
            raise GhostWalkCapabilityBindingError(
                "persisted transition inference receipt is invalid"
            )
        session_id = row.get("session_id")
        action_sha256 = row.get("action_observation_sha256")
        if not isinstance(session_id, str) or not isinstance(
            action_sha256,
            str,
        ):
            raise GhostWalkCapabilityBindingError(
                "transition inference action link is invalid"
            )
        _require_sha256(
            action_sha256,
            "action_observation_sha256",
        )

        matches: list[GhostWalkObservation] = []
        for candidate in self._ledger.ghostwalk_observations():
            if candidate.get("observation_sha256") != action_sha256:
                continue
            try:
                observation = GhostWalkObservation.from_dict(candidate)
            except GhostWalkContractError as exc:
                raise GhostWalkCapabilityBindingError(
                    "persisted Ghost-Walk action observation is invalid"
                ) from exc
            matches.append(observation)
        if not matches:
            return None
        if len(matches) != 1:
            raise GhostWalkCapabilityBindingError(
                "Ghost-Walk action observation identity is not unique"
            )
        observation = matches[0]
        if observation.session_id != session_id:
            raise GhostWalkCapabilityBindingError(
                "transition inference session differs from action observation"
            )
        return observation

    def _binding_for_decision(
        self,
        authorization_decision_sha256: str,
    ) -> GhostWalkExecutableBinding | None:
        rows = self._ledger.ghostwalk_executable_bindings(
            authorization_decision_sha256=authorization_decision_sha256
        )
        bindings = [self._parse_binding(row) for row in rows]
        if len(bindings) > 1:
            raise GhostWalkCapabilityBindingError(
                "multiple executable bindings exist for one authorization"
            )
        return bindings[0] if bindings else None

    def _parse_binding(
        self,
        row: Mapping[str, object],
    ) -> GhostWalkExecutableBinding:
        try:
            binding = GhostWalkExecutableBinding.from_dict(row)
        except GhostWalkCapabilityBindingError as exc:
            raise GhostWalkCapabilityBindingError(
                "persisted executable binding is invalid"
            ) from exc
        mapping_matches = tuple(
            item
            for item in self.registry.mappings
            if item.mapping_sha256 == binding.mapping_sha256
        )
        if len(mapping_matches) != 1:
            raise GhostWalkCapabilityBindingError(
                "binding mapping is absent or ambiguous in current registry"
            )
        mapping = mapping_matches[0]
        if binding.mapping_set_sha256 != self.registry.mapping_set_sha256:
            raise GhostWalkCapabilityBindingError(
                "binding mapping-set identity differs from current registry"
            )
        if (
            binding.mapping_id != mapping.mapping_id
            or binding.intent_code != mapping.intent_code
            or binding.capability_id != mapping.capability_id
            or binding.capability_version != mapping.capability_version
            or binding.permissions_required != mapping.permissions_required
            or binding.effects_declared != mapping.effects_declared
        ):
            raise GhostWalkCapabilityBindingError(
                "binding does not match its capability mapping"
            )
        return binding

    def _readiness(
        self,
        *,
        target: str,
        reason: GhostWalkBindingReadinessReason,
        authorization_decision_sha256: str | None = None,
        selected_mapping_sha256: str | None = None,
        action_observation_sha256: str | None = None,
        existing_binding_sha256: str | None = None,
    ) -> GhostWalkBindingReadiness:
        return GhostWalkBindingReadiness(
            target_inference_receipt_sha256=target,
            authorization_decision_sha256=(
                authorization_decision_sha256
            ),
            mapping_set_sha256=self.registry.mapping_set_sha256,
            selected_mapping_sha256=selected_mapping_sha256,
            action_observation_sha256=action_observation_sha256,
            existing_binding_sha256=existing_binding_sha256,
            ready=reason is GhostWalkBindingReadinessReason.READY,
            reason=reason,
        )
