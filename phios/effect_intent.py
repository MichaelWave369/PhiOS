"""Canonical zero-authority effect intent contract for PhiOS.

EffectIntent states what effects a proposed capability invocation is intended to
cause. It does not authorize those effects and it does not assert execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from phios.spine.effects import (
    ACTIVE_EFFECTS,
    EffectBoundaryContractError,
    normalize_effects,
)

EFFECT_INTENT_SCHEMA_VERSION = "phios.effect_intent.v0.1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EffectIntentContractError(ValueError):
    """Raised when an EffectIntent violates the canonical contract."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise EffectIntentContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise EffectIntentContractError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise EffectIntentContractError(f"{field} contains control characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise EffectIntentContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EffectIntentContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EffectIntentContractError(
            f"{field} must include a timezone offset"
        )
    return text


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EffectIntentContractError(
            "EffectIntent payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_declared_effects(effects: tuple[str, ...]) -> tuple[str, ...]:
    try:
        normalized = normalize_effects(
            effects,
            label="effect intent effects",
        )
    except EffectBoundaryContractError as exc:
        raise EffectIntentContractError(str(exc)) from exc
    if "unknown" in normalized:
        raise EffectIntentContractError(
            "EffectIntent cannot declare unknown effects"
        )
    return normalized


def _active_effects(effects: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(effect for effect in effects if effect in ACTIVE_EFFECTS)


@dataclass(frozen=True, slots=True)
class EffectIntent:
    """Immutable declaration of intended effects with zero authority."""

    capability_id: str
    capability_version: str
    payload_sha256: str
    declared_at: str
    effects_declared: tuple[str, ...]
    evidence_ref_sha256s: tuple[str, ...] = ()
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = EFFECT_INTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EFFECT_INTENT_SCHEMA_VERSION:
            raise EffectIntentContractError(
                f"unsupported EffectIntent schema: {self.schema_version}"
            )
        _require_text(self.capability_id, "capability_id")
        _require_text(
            self.capability_version,
            "capability_version",
            maximum=128,
        )
        _require_sha256(self.payload_sha256, "payload_sha256")
        _require_timestamp(self.declared_at, "declared_at")

        normalized_effects = _normalize_declared_effects(
            self.effects_declared
        )
        if normalized_effects != self.effects_declared:
            raise EffectIntentContractError(
                "effects_declared must be sorted, unique, and canonical"
            )

        if len(self.evidence_ref_sha256s) > 64:
            raise EffectIntentContractError(
                "evidence_ref_sha256s exceeds 64 items"
            )
        if tuple(sorted(self.evidence_ref_sha256s)) != (
            self.evidence_ref_sha256s
        ):
            raise EffectIntentContractError(
                "evidence_ref_sha256s must be sorted"
            )
        if len(set(self.evidence_ref_sha256s)) != len(
            self.evidence_ref_sha256s
        ):
            raise EffectIntentContractError(
                "evidence_ref_sha256s must not contain duplicates"
            )
        for digest in self.evidence_ref_sha256s:
            _require_sha256(digest, "evidence_ref_sha256")

        if self.effect_performed is not False:
            raise EffectIntentContractError(
                "EffectIntent cannot claim that an effect was performed"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise EffectIntentContractError(
                "EffectIntent cannot carry operational, action, or execution authority"
            )

    @property
    def active_effects(self) -> tuple[str, ...]:
        return _active_effects(self.effects_declared)

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "payload_sha256": self.payload_sha256,
            "declared_at": self.declared_at,
            "effects_declared": list(self.effects_declared),
            "active_effects": list(self.active_effects),
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def effect_intent_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["effect_intent_sha256"] = self.effect_intent_sha256
        return payload

    @classmethod
    def build(
        cls,
        *,
        capability_id: str,
        capability_version: str,
        payload_sha256: str,
        declared_at: str,
        effects_declared: tuple[str, ...],
        evidence_ref_sha256s: tuple[str, ...] = (),
    ) -> "EffectIntent":
        try:
            effects = _normalize_declared_effects(effects_declared)
        except EffectIntentContractError:
            raise
        evidence_refs = tuple(sorted(set(evidence_ref_sha256s)))
        return cls(
            capability_id=capability_id,
            capability_version=capability_version,
            payload_sha256=payload_sha256,
            declared_at=declared_at,
            effects_declared=effects,
            evidence_ref_sha256s=evidence_refs,
        )

    @classmethod
    def from_dict(cls, value: object) -> "EffectIntent":
        if not isinstance(value, dict):
            raise EffectIntentContractError("EffectIntent must be an object")
        data = dict(value)
        expected = {
            "schema_version",
            "capability_id",
            "capability_version",
            "payload_sha256",
            "declared_at",
            "effects_declared",
            "active_effects",
            "evidence_ref_sha256s",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "effect_intent_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise EffectIntentContractError(
                f"EffectIntent fields mismatch: missing={missing}; unknown={unknown}"
            )

        effects_raw = data["effects_declared"]
        if not isinstance(effects_raw, list):
            raise EffectIntentContractError(
                "effects_declared must be an array"
            )
        effects = tuple(
            _require_text(
                item,
                "effects_declared item",
                maximum=64,
            )
            for item in effects_raw
        )

        evidence_raw = data["evidence_ref_sha256s"]
        if not isinstance(evidence_raw, list):
            raise EffectIntentContractError(
                "evidence_ref_sha256s must be an array"
            )
        evidence_refs = tuple(
            _require_sha256(item, "evidence_ref_sha256")
            for item in evidence_raw
        )

        for field in (
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise EffectIntentContractError(
                    f"{field} must be Boolean"
                )

        intent = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            capability_id=_require_text(
                data["capability_id"],
                "capability_id",
            ),
            capability_version=_require_text(
                data["capability_version"],
                "capability_version",
                maximum=128,
            ),
            payload_sha256=_require_sha256(
                data["payload_sha256"],
                "payload_sha256",
            ),
            declared_at=_require_timestamp(
                data["declared_at"],
                "declared_at",
            ),
            effects_declared=effects,
            evidence_ref_sha256s=evidence_refs,
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )

        active_raw = data["active_effects"]
        if not isinstance(active_raw, list):
            raise EffectIntentContractError("active_effects must be an array")
        active = tuple(
            _require_text(item, "active_effects item", maximum=64)
            for item in active_raw
        )
        if active != intent.active_effects:
            raise EffectIntentContractError(
                "active_effects does not match declared effects"
            )

        if data["effect_intent_sha256"] != intent.effect_intent_sha256:
            raise EffectIntentContractError(
                "effect_intent_sha256 does not match canonical EffectIntent"
            )
        return intent
