from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from .models import Capability

EFFECT_BOUNDARY_POLICY_SCHEMA_VERSION = "phios.effect_boundary_policy.v0.1"

KNOWN_EFFECTS = (
    "none",
    "local_state.read",
    "local_state.change",
    "filesystem.read",
    "filesystem.change",
    "process.spawn",
    "network.request",
    "external_state.read",
    "external_state.change",
    "ipc.request",
    "display.observe",
    "display.control",
    "credential.read",
    "control_plane.read",
    "control_plane.change",
    "unknown",
)

ACTIVE_EFFECTS = (
    "local_state.change",
    "filesystem.change",
    "process.spawn",
    "network.request",
    "external_state.change",
    "ipc.request",
    "display.control",
    "control_plane.change",
)


class EffectBoundaryContractError(ValueError):
    """Raised when a capability or executor effect declaration is malformed."""


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
        raise EffectBoundaryContractError(
            "effect-boundary payload must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_effects(
    effects: Iterable[str],
    *,
    label: str = "effects",
    allow_empty: bool = False,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in effects:
        if not isinstance(raw, str) or not raw.strip():
            raise EffectBoundaryContractError(
                f"{label} entries must be non-empty strings"
            )
        value = raw.strip()
        if value not in KNOWN_EFFECTS:
            raise EffectBoundaryContractError(
                f"{label} contains unsupported effect: {value}"
            )
        if value not in normalized:
            normalized.append(value)

    result = tuple(sorted(normalized))
    if not result and not allow_empty:
        raise EffectBoundaryContractError(f"{label} must not be empty")
    if "none" in result and len(result) != 1:
        raise EffectBoundaryContractError(
            f"{label} cannot combine none with another effect"
        )
    return result


@dataclass(frozen=True, slots=True)
class EffectBoundaryDecision:
    status: str
    reason: str
    capability_id: str
    capability_version: str
    capability_risk: str
    capability_effects: tuple[str, ...]
    executor_effects: tuple[str, ...]
    active_effects: tuple[str, ...]
    effect_contract_match: bool
    classification_complete: bool
    semantic_read_label_conflict: bool
    policy_sha256: str
    action_authority: bool = False
    execution_authority: bool = False

    @property
    def allowed(self) -> bool:
        return self.status == "CLASSIFIED"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": EFFECT_BOUNDARY_POLICY_SCHEMA_VERSION,
            "status": self.status,
            "reason": self.reason,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "capability_risk": self.capability_risk,
            "capability_effects": list(self.capability_effects),
            "executor_effects": list(self.executor_effects),
            "active_effects": list(self.active_effects),
            "effect_contract_match": self.effect_contract_match,
            "classification_complete": self.classification_complete,
            "semantic_read_label_conflict": self.semantic_read_label_conflict,
            "policy_sha256": self.policy_sha256,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


class EffectBoundaryPolicy:
    """Fail-closed effect classification independent of capability naming."""

    def __init__(self) -> None:
        self._policy_sha256 = _sha256(
            {
                "schema_version": EFFECT_BOUNDARY_POLICY_SCHEMA_VERSION,
                "known_effects": list(KNOWN_EFFECTS),
                "active_effects": list(ACTIVE_EFFECTS),
                "rules": [
                    "capability_and_executor_effects_required",
                    "unknown_is_incomplete",
                    "capability_executor_effects_must_match",
                    "risk_read_cannot_mask_active_effects",
                    "method_names_do_not_define_effects",
                ],
            }
        )

    @property
    def policy_sha256(self) -> str:
        return self._policy_sha256

    def evaluate(
        self,
        capability: Capability,
        *,
        executor_effects: Iterable[str],
    ) -> EffectBoundaryDecision:
        capability_effects = normalize_effects(
            capability.effects,
            label="capability effects",
            allow_empty=True,
        )
        normalized_executor_effects = normalize_effects(
            executor_effects,
            label="executor effects",
            allow_empty=True,
        )

        contract_match = (
            bool(capability_effects)
            and capability_effects == normalized_executor_effects
        )
        classification_complete = (
            bool(capability_effects)
            and bool(normalized_executor_effects)
            and "unknown" not in capability_effects
            and "unknown" not in normalized_executor_effects
        )
        active = tuple(
            effect
            for effect in capability_effects
            if effect in ACTIVE_EFFECTS
        )
        read_conflict = str(capability.risk) == "read" and bool(active)

        if not capability_effects:
            status = "BLOCKED"
            reason = "capability_effect_classification_missing"
        elif not normalized_executor_effects:
            status = "BLOCKED"
            reason = "executor_effect_classification_missing"
        elif not classification_complete:
            status = "BLOCKED"
            reason = "effect_classification_unknown"
        elif not contract_match:
            status = "BLOCKED"
            reason = "capability_executor_effect_contract_mismatch"
        elif read_conflict:
            status = "BLOCKED"
            reason = "read_risk_label_conflicts_with_active_effects"
        else:
            status = "CLASSIFIED"
            reason = "effect_contract_classified"

        return EffectBoundaryDecision(
            status=status,
            reason=reason,
            capability_id=capability.id,
            capability_version=capability.version,
            capability_risk=str(capability.risk),
            capability_effects=capability_effects,
            executor_effects=normalized_executor_effects,
            active_effects=active,
            effect_contract_match=contract_match,
            classification_complete=classification_complete,
            semantic_read_label_conflict=read_conflict,
            policy_sha256=self.policy_sha256,
        )
