"""Canonical enforcement/trust map contract for PhiOS.

An EnforcementProfile records which layer claims to enforce a specific rule for
an EffectIntent. It is descriptive evidence, not permission, execution
authority, or proof that the overall system is secure.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from phios.effect_intent import EffectIntent
from phios.spine.effects import (
    EffectBoundaryContractError,
    normalize_effects,
)

ENFORCEMENT_PROFILE_SCHEMA_VERSION = "phios.enforcement_profile.v0.1"
ENFORCEMENT_RULE_SCHEMA_VERSION = "phios.enforcement_rule.v0.1"

ENFORCEMENT_LAYERS = (
    "python_policy",
    "application_contract",
    "broker",
    "linux_permissions",
    "linux_namespaces",
    "resource_limits",
    "transport_boundary",
    "external_system",
    "none",
    "unknown",
)

TRUST_BOUNDARIES = (
    "same_process",
    "process_boundary",
    "kernel_boundary",
    "transport_boundary",
    "external_boundary",
    "none",
    "unknown",
)

ENFORCEMENT_STATUSES = (
    "enforced",
    "advisory",
    "not_enforced",
    "unknown",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RULE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class EnforcementProfileContractError(ValueError):
    """Raised when an enforcement profile violates its canonical contract."""


def _require_text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise EnforcementProfileContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise EnforcementProfileContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise EnforcementProfileContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise EnforcementProfileContractError(
            f"{field} must be a lowercase SHA-256 digest"
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
        raise EnforcementProfileContractError(
            "enforcement profile must be canonical JSON"
        ) from exc


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _normalize_effect_scope(
    effects: tuple[str, ...],
    *,
    label: str,
) -> tuple[str, ...]:
    try:
        normalized = normalize_effects(
            effects,
            label=label,
            allow_empty=True,
        )
    except EffectBoundaryContractError as exc:
        raise EnforcementProfileContractError(str(exc)) from exc
    if "none" in normalized:
        raise EnforcementProfileContractError(
            f"{label} cannot map the none effect"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class EnforcementRule:
    """One explicit claim about who enforces one bounded rule."""

    rule_id: str
    effect_scope: tuple[str, ...]
    constraint: str
    layer: str
    boundary: str
    status: str
    mechanism: str
    evidence_ref_sha256s: tuple[str, ...] = ()
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = ENFORCEMENT_RULE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENFORCEMENT_RULE_SCHEMA_VERSION:
            raise EnforcementProfileContractError(
                f"unsupported enforcement rule schema: {self.schema_version}"
            )
        if not isinstance(self.rule_id, str) or not _RULE_ID_RE.fullmatch(
            self.rule_id
        ):
            raise EnforcementProfileContractError(
                "rule_id must be a canonical lowercase identifier"
            )
        normalized_scope = _normalize_effect_scope(
            self.effect_scope,
            label="enforcement rule effect_scope",
        )
        if not normalized_scope:
            raise EnforcementProfileContractError(
                "enforcement rule effect_scope must not be empty"
            )
        if normalized_scope != self.effect_scope:
            raise EnforcementProfileContractError(
                "effect_scope must be sorted, unique, and canonical"
            )

        _require_text(self.constraint, "constraint")
        _require_text(self.mechanism, "mechanism")
        if self.layer not in ENFORCEMENT_LAYERS:
            raise EnforcementProfileContractError(
                f"unsupported enforcement layer: {self.layer}"
            )
        if self.boundary not in TRUST_BOUNDARIES:
            raise EnforcementProfileContractError(
                f"unsupported trust boundary: {self.boundary}"
            )
        if self.status not in ENFORCEMENT_STATUSES:
            raise EnforcementProfileContractError(
                f"unsupported enforcement status: {self.status}"
            )

        if len(self.evidence_ref_sha256s) > 64:
            raise EnforcementProfileContractError(
                "evidence_ref_sha256s exceeds 64 items"
            )
        if tuple(sorted(self.evidence_ref_sha256s)) != (
            self.evidence_ref_sha256s
        ):
            raise EnforcementProfileContractError(
                "evidence_ref_sha256s must be sorted"
            )
        if len(set(self.evidence_ref_sha256s)) != len(
            self.evidence_ref_sha256s
        ):
            raise EnforcementProfileContractError(
                "evidence_ref_sha256s must not contain duplicates"
            )
        for digest in self.evidence_ref_sha256s:
            _require_sha256(digest, "evidence_ref_sha256")

        if self.status in {"enforced", "advisory"}:
            if self.layer in {"none", "unknown"}:
                raise EnforcementProfileContractError(
                    f"{self.status} rules require a concrete enforcement layer"
                )
            if self.boundary in {"none", "unknown"}:
                raise EnforcementProfileContractError(
                    f"{self.status} rules require a concrete trust boundary"
                )
            if not self.evidence_ref_sha256s:
                raise EnforcementProfileContractError(
                    f"{self.status} rules require evidence references"
                )
        elif self.status == "not_enforced":
            if self.layer != "none" or self.boundary != "none":
                raise EnforcementProfileContractError(
                    "not_enforced rules must use none layer and none boundary"
                )
            if self.evidence_ref_sha256s:
                raise EnforcementProfileContractError(
                    "not_enforced rules cannot cite enforcement evidence"
                )
        elif self.status == "unknown":
            if self.layer != "unknown" or self.boundary != "unknown":
                raise EnforcementProfileContractError(
                    "unknown rules must use unknown layer and unknown boundary"
                )

        if self.effect_performed is not False:
            raise EnforcementProfileContractError(
                "enforcement rules cannot claim an effect was performed"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise EnforcementProfileContractError(
                "enforcement rules cannot carry authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rule_id": self.rule_id,
            "effect_scope": list(self.effect_scope),
            "constraint": self.constraint,
            "layer": self.layer,
            "boundary": self.boundary,
            "status": self.status,
            "mechanism": self.mechanism,
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def rule_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["rule_sha256"] = self.rule_sha256
        return payload

    @classmethod
    def build(
        cls,
        *,
        rule_id: str,
        effect_scope: tuple[str, ...],
        constraint: str,
        layer: str,
        boundary: str,
        status: str,
        mechanism: str,
        evidence_ref_sha256s: tuple[str, ...] = (),
    ) -> "EnforcementRule":
        effects = _normalize_effect_scope(
            effect_scope,
            label="enforcement rule effect_scope",
        )
        evidence = tuple(sorted(set(evidence_ref_sha256s)))
        return cls(
            rule_id=rule_id,
            effect_scope=effects,
            constraint=constraint,
            layer=layer,
            boundary=boundary,
            status=status,
            mechanism=mechanism,
            evidence_ref_sha256s=evidence,
        )

    @classmethod
    def from_dict(cls, value: object) -> "EnforcementRule":
        if not isinstance(value, dict):
            raise EnforcementProfileContractError(
                "enforcement rule must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "rule_id",
            "effect_scope",
            "constraint",
            "layer",
            "boundary",
            "status",
            "mechanism",
            "evidence_ref_sha256s",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "rule_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise EnforcementProfileContractError(
                f"enforcement rule fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        scope_raw = data["effect_scope"]
        if not isinstance(scope_raw, list):
            raise EnforcementProfileContractError(
                "effect_scope must be an array"
            )
        effect_scope = tuple(
            _require_text(item, "effect_scope item", maximum=64)
            for item in scope_raw
        )

        evidence_raw = data["evidence_ref_sha256s"]
        if not isinstance(evidence_raw, list):
            raise EnforcementProfileContractError(
                "evidence_ref_sha256s must be an array"
            )
        evidence = tuple(
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
                raise EnforcementProfileContractError(
                    f"{field} must be Boolean"
                )

        rule = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            rule_id=_require_text(
                data["rule_id"],
                "rule_id",
                maximum=128,
            ),
            effect_scope=effect_scope,
            constraint=_require_text(
                data["constraint"],
                "constraint",
            ),
            layer=_require_text(
                data["layer"],
                "layer",
                maximum=64,
            ),
            boundary=_require_text(
                data["boundary"],
                "boundary",
                maximum=64,
            ),
            status=_require_text(
                data["status"],
                "status",
                maximum=64,
            ),
            mechanism=_require_text(
                data["mechanism"],
                "mechanism",
            ),
            evidence_ref_sha256s=evidence,
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )
        if data["rule_sha256"] != rule.rule_sha256:
            raise EnforcementProfileContractError(
                "rule_sha256 does not match canonical enforcement rule"
            )
        return rule


@dataclass(frozen=True, slots=True)
class EnforcementProfile:
    """Descriptive trust map for one exact EffectIntent."""

    effect_intent_sha256: str
    effects_declared: tuple[str, ...]
    rules: tuple[EnforcementRule, ...] = ()
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = ENFORCEMENT_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENFORCEMENT_PROFILE_SCHEMA_VERSION:
            raise EnforcementProfileContractError(
                f"unsupported enforcement profile schema: {self.schema_version}"
            )
        _require_sha256(
            self.effect_intent_sha256,
            "effect_intent_sha256",
        )
        try:
            normalized = normalize_effects(
                self.effects_declared,
                label="profile effects_declared",
            )
        except EffectBoundaryContractError as exc:
            raise EnforcementProfileContractError(str(exc)) from exc
        if normalized != self.effects_declared:
            raise EnforcementProfileContractError(
                "effects_declared must be sorted, unique, and canonical"
            )

        if tuple(sorted(self.rules, key=lambda item: item.rule_id)) != self.rules:
            raise EnforcementProfileContractError(
                "enforcement rules must be sorted by rule_id"
            )
        rule_ids = tuple(rule.rule_id for rule in self.rules)
        if len(set(rule_ids)) != len(rule_ids):
            raise EnforcementProfileContractError(
                "enforcement rule IDs must be unique"
            )

        declared = set(self.effects_declared)
        if "none" in declared and self.rules:
            raise EnforcementProfileContractError(
                "none EffectIntent cannot carry enforcement rules"
            )
        for rule in self.rules:
            extra = set(rule.effect_scope) - declared
            if extra:
                raise EnforcementProfileContractError(
                    "enforcement rule references effects outside EffectIntent"
                )

        if self.effect_performed is not False:
            raise EnforcementProfileContractError(
                "enforcement profile cannot claim an effect was performed"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise EnforcementProfileContractError(
                "enforcement profile cannot carry authority"
            )

    @property
    def mapped_effects(self) -> tuple[str, ...]:
        values = {
            effect
            for rule in self.rules
            for effect in rule.effect_scope
        }
        return tuple(sorted(values))

    @property
    def unmapped_effects(self) -> tuple[str, ...]:
        if self.effects_declared == ("none",):
            return ()
        return tuple(
            effect
            for effect in self.effects_declared
            if effect not in set(self.mapped_effects)
        )

    @property
    def effects_with_enforced_rule(self) -> tuple[str, ...]:
        values = {
            effect
            for rule in self.rules
            if rule.status == "enforced"
            for effect in rule.effect_scope
        }
        return tuple(sorted(values))

    @property
    def effects_without_enforced_rule(self) -> tuple[str, ...]:
        if self.effects_declared == ("none",):
            return ()
        enforced = set(self.effects_with_enforced_rule)
        return tuple(
            effect
            for effect in self.effects_declared
            if effect not in enforced
        )

    @property
    def mapping_complete(self) -> bool:
        return not self.unmapped_effects

    @property
    def profile_status(self) -> str:
        if self.effects_declared == ("none",):
            return "no_effects"
        if self.unmapped_effects:
            return "mapping_gaps"
        return "mapped"

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "effect_intent_sha256": self.effect_intent_sha256,
            "effects_declared": list(self.effects_declared),
            "rules": [rule.to_dict() for rule in self.rules],
            "mapped_effects": list(self.mapped_effects),
            "unmapped_effects": list(self.unmapped_effects),
            "effects_with_enforced_rule": list(
                self.effects_with_enforced_rule
            ),
            "effects_without_enforced_rule": list(
                self.effects_without_enforced_rule
            ),
            "mapping_complete": self.mapping_complete,
            "profile_status": self.profile_status,
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def profile_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["profile_sha256"] = self.profile_sha256
        return payload

    @classmethod
    def build(
        cls,
        *,
        intent: EffectIntent,
        rules: tuple[EnforcementRule, ...] = (),
    ) -> "EnforcementProfile":
        ordered = tuple(sorted(rules, key=lambda item: item.rule_id))
        return cls(
            effect_intent_sha256=intent.effect_intent_sha256,
            effects_declared=intent.effects_declared,
            rules=ordered,
        )

    @classmethod
    def from_dict(cls, value: object) -> "EnforcementProfile":
        if not isinstance(value, dict):
            raise EnforcementProfileContractError(
                "enforcement profile must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "effect_intent_sha256",
            "effects_declared",
            "rules",
            "mapped_effects",
            "unmapped_effects",
            "effects_with_enforced_rule",
            "effects_without_enforced_rule",
            "mapping_complete",
            "profile_status",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "profile_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise EnforcementProfileContractError(
                f"enforcement profile fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        effects_raw = data["effects_declared"]
        if not isinstance(effects_raw, list):
            raise EnforcementProfileContractError(
                "effects_declared must be an array"
            )
        effects = tuple(
            _require_text(item, "effects_declared item", maximum=64)
            for item in effects_raw
        )

        rules_raw = data["rules"]
        if not isinstance(rules_raw, list):
            raise EnforcementProfileContractError(
                "rules must be an array"
            )
        rules = tuple(EnforcementRule.from_dict(item) for item in rules_raw)

        for field in (
            "mapping_complete",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise EnforcementProfileContractError(
                    f"{field} must be Boolean"
                )

        profile = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            effect_intent_sha256=_require_sha256(
                data["effect_intent_sha256"],
                "effect_intent_sha256",
            ),
            effects_declared=effects,
            rules=rules,
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )

        derived = {
            "mapped_effects": list(profile.mapped_effects),
            "unmapped_effects": list(profile.unmapped_effects),
            "effects_with_enforced_rule": list(
                profile.effects_with_enforced_rule
            ),
            "effects_without_enforced_rule": list(
                profile.effects_without_enforced_rule
            ),
            "mapping_complete": profile.mapping_complete,
            "profile_status": profile.profile_status,
        }
        for field, expected_value in derived.items():
            if data[field] != expected_value:
                raise EnforcementProfileContractError(
                    f"{field} does not match canonical enforcement profile"
                )

        if data["profile_sha256"] != profile.profile_sha256:
            raise EnforcementProfileContractError(
                "profile_sha256 does not match canonical enforcement profile"
            )
        return profile
