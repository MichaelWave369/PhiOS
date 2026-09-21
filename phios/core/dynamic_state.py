"""Deterministic lifecycle for advisory DynamicField state.

Dynamic field values are useful precisely because they can change routing pressure.
That same property makes stale values dangerous: an old failure, contradiction, or
resource condition must not influence the runtime forever merely because nobody
published a compensating event.

This module adds an explicit, zero-authority temporal envelope. It attenuates selected
field variables toward their immutable-law initial values and terminates the entire
advisory snapshot at a declared maximum age.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping

from phios.core.dynamic_field import (
    DynamicField,
    DynamicFieldState,
)

DYNAMIC_STATE_POLICY_SCHEMA_VERSION = "phios.dynamic_state_policy.v0.1"
DYNAMIC_STATE_RECEIPT_SCHEMA_VERSION = "phios.dynamic_state_receipt.v0.1"


class DynamicStateContractError(ValueError):
    """Raised when dynamic-state lifecycle evidence is invalid."""


@dataclass(frozen=True, slots=True)
class DynamicStateDecayRule:
    """Attenuate one field variable toward its immutable-law initial value."""

    field_variable: str
    grace_seconds: float
    attenuation_rate_per_second: float

    def to_dict(self) -> dict[str, object]:
        return {
            "field_variable": self.field_variable,
            "grace_seconds": self.grace_seconds,
            "attenuation_rate_per_second": self.attenuation_rate_per_second,
        }


@dataclass(frozen=True, slots=True)
class DynamicStatePolicy:
    """Immutable temporal policy for one complete DynamicField law."""

    policy_id: str
    version: str
    max_state_age_seconds: float
    rules: tuple[DynamicStateDecayRule, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": DYNAMIC_STATE_POLICY_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "version": self.version,
            "max_state_age_seconds": self.max_state_age_seconds,
            "rules": [
                rule.to_dict()
                for rule in sorted(self.rules, key=lambda item: item.field_variable)
            ],
        }

    @property
    def policy_sha256(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class DynamicStateValueChange:
    field_variable: str
    before: float
    baseline: float
    grace_seconds: float
    attenuation_rate_per_second: float
    elapsed_attenuation_seconds: float
    after: float

    def to_dict(self) -> dict[str, object]:
        return {
            "field_variable": self.field_variable,
            "before": self.before,
            "baseline": self.baseline,
            "grace_seconds": self.grace_seconds,
            "attenuation_rate_per_second": self.attenuation_rate_per_second,
            "elapsed_attenuation_seconds": self.elapsed_attenuation_seconds,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class DynamicStateReceipt:
    schema: str
    status: str
    reason: str
    policy_id: str
    policy_sha256: str
    field_law_sha256: str
    source_field_state_sha256: str
    source_field_revision: int
    anchor_event_id: str
    activated_at_utc: str
    observed_at_utc: str
    age_seconds: float
    max_state_age_seconds: float
    effective_field_state_sha256: str | None
    effective_field_revision: int | None
    transition_id: str | None
    transition_sha256: str | None
    changes: tuple[DynamicStateValueChange, ...]
    state_consumable: bool
    terminated: bool
    governing_law_mutated: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "field_law_sha256": self.field_law_sha256,
            "source_field_state_sha256": self.source_field_state_sha256,
            "source_field_revision": self.source_field_revision,
            "anchor_event_id": self.anchor_event_id,
            "activated_at_utc": self.activated_at_utc,
            "observed_at_utc": self.observed_at_utc,
            "age_seconds": self.age_seconds,
            "max_state_age_seconds": self.max_state_age_seconds,
            "effective_field_state_sha256": self.effective_field_state_sha256,
            "effective_field_revision": self.effective_field_revision,
            "transition_id": self.transition_id,
            "transition_sha256": self.transition_sha256,
            "changes": [item.to_dict() for item in self.changes],
            "state_consumable": self.state_consumable,
            "terminated": self.terminated,
            "governing_law_mutated": self.governing_law_mutated,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class DynamicStateEvaluation:
    receipt: DynamicStateReceipt
    effective_state: DynamicFieldState | None

    def require_consumable_state(self) -> DynamicFieldState:
        if not self.receipt.state_consumable or self.effective_state is None:
            raise DynamicStateContractError(
                "dynamic state is terminated and cannot be consumed"
            )
        if (
            self.receipt.effective_field_state_sha256
            != self.effective_state.state_sha256
        ):
            raise DynamicStateContractError(
                "dynamic state receipt does not bind the effective state"
            )
        if (
            self.receipt.effective_field_revision
            != self.effective_state.revision
        ):
            raise DynamicStateContractError(
                "dynamic state receipt does not bind the effective revision"
            )
        if (
            self.receipt.action_authority is not False
            or self.receipt.execution_authority is not False
            or self.receipt.operational_authority is not False
        ):
            raise DynamicStateContractError(
                "dynamic state receipt cannot carry operational authority"
            )
        return self.effective_state


class DynamicStateController:
    """Evaluate age, attenuation, and termination for one DynamicField law."""

    def __init__(
        self,
        *,
        dynamic_field: DynamicField,
        policy: DynamicStatePolicy,
    ) -> None:
        self._field = dynamic_field
        self._policy, self._rules = self._validate_policy(policy)

    @property
    def policy(self) -> DynamicStatePolicy:
        return self._policy

    def evaluate(
        self,
        state: DynamicFieldState,
        *,
        activated_at_utc: str,
        observed_at_utc: str,
    ) -> DynamicStateEvaluation:
        self._field.validate_state(state)
        self._require_fresh_anchor(state)

        activated = _parse_time(activated_at_utc, "activated_at_utc")
        observed = _parse_time(observed_at_utc, "observed_at_utc")
        if observed < activated:
            raise DynamicStateContractError(
                "observed_at_utc cannot precede activated_at_utc"
            )

        age_seconds = _stable_float((observed - activated).total_seconds())
        activated_text = activated.isoformat()
        observed_text = observed.isoformat()
        anchor_event_id = (
            state.applied_event_ids[-1]
            if state.applied_event_ids
            else "dynamic-field-initial-state"
        )

        if age_seconds >= self._policy.max_state_age_seconds:
            receipt = self._receipt(
                status="TERMINATED",
                reason="max_state_age_reached",
                state=state,
                anchor_event_id=anchor_event_id,
                activated_at_utc=activated_text,
                observed_at_utc=observed_text,
                age_seconds=age_seconds,
                effective_state=None,
                transition_id=None,
                transition_sha256=None,
                changes=(),
                state_consumable=False,
                terminated=True,
            )
            return DynamicStateEvaluation(
                receipt=receipt,
                effective_state=None,
            )

        current = state.as_mapping()
        baselines = {
            rule.name: float(rule.initial)
            for rule in self._field.law.variables
        }
        effective = dict(current)
        changes: list[DynamicStateValueChange] = []

        for variable in sorted(self._rules):
            rule = self._rules[variable]
            before = float(current[variable])
            baseline = baselines[variable]
            elapsed = max(0.0, age_seconds - rule.grace_seconds)
            after = _move_toward(
                before,
                baseline,
                rule.attenuation_rate_per_second * elapsed,
            )
            after = _stable_float(after)
            effective[variable] = after
            if after != before:
                changes.append(
                    DynamicStateValueChange(
                        field_variable=variable,
                        before=before,
                        baseline=baseline,
                        grace_seconds=rule.grace_seconds,
                        attenuation_rate_per_second=(
                            rule.attenuation_rate_per_second
                        ),
                        elapsed_attenuation_seconds=_stable_float(elapsed),
                        after=after,
                    )
                )

        transition_id: str | None = None
        transition_sha256: str | None = None
        effective_state = state
        if changes:
            transition_payload = {
                "schema": "phios.dynamic_state_transition.v0.1",
                "policy_sha256": self._policy.policy_sha256,
                "source_field_state_sha256": state.state_sha256,
                "activated_at_utc": activated_text,
                "observed_at_utc": observed_text,
                "effective_values": {
                    key: effective[key]
                    for key in sorted(effective)
                },
            }
            transition_sha256 = _digest(transition_payload)
            transition_id = f"dynamic-state:{transition_sha256[:32]}"
            effective_state = self._field.materialize_temporal_transition(
                state,
                transition_id=transition_id,
                transition_sha256=transition_sha256,
                values=effective,
            )
            status = "ATTENUATED"
            reason = "temporal_attenuation_applied"
        else:
            status = "ACTIVE"
            reason = "within_temporal_policy_without_attenuation"

        receipt = self._receipt(
            status=status,
            reason=reason,
            state=state,
            anchor_event_id=anchor_event_id,
            activated_at_utc=activated_text,
            observed_at_utc=observed_text,
            age_seconds=age_seconds,
            effective_state=effective_state,
            transition_id=transition_id,
            transition_sha256=transition_sha256,
            changes=tuple(changes),
            state_consumable=True,
            terminated=False,
        )
        return DynamicStateEvaluation(
            receipt=receipt,
            effective_state=effective_state,
        )

    def validate_evaluation(
        self,
        evaluation: DynamicStateEvaluation,
    ) -> None:
        receipt = evaluation.receipt
        if receipt.schema != DYNAMIC_STATE_RECEIPT_SCHEMA_VERSION:
            raise DynamicStateContractError(
                "unsupported dynamic state receipt schema"
            )
        if receipt.policy_sha256 != self._policy.policy_sha256:
            raise DynamicStateContractError(
                "dynamic state receipt is bound to another policy"
            )
        if receipt.field_law_sha256 != self._field.law.law_sha256:
            raise DynamicStateContractError(
                "dynamic state receipt is bound to another field law"
            )
        payload = receipt.to_dict()
        supplied_sha = payload.pop("receipt_sha256")
        if _digest(payload) != supplied_sha:
            raise DynamicStateContractError(
                "dynamic state receipt hash does not match receipt contents"
            )

        if receipt.terminated:
            if receipt.state_consumable:
                raise DynamicStateContractError(
                    "terminated dynamic state cannot be consumable"
                )
            if evaluation.effective_state is not None:
                raise DynamicStateContractError(
                    "terminated dynamic state cannot carry effective state"
                )
            return

        state = evaluation.require_consumable_state()
        self._field.validate_state(state)

    def _validate_policy(
        self,
        policy: DynamicStatePolicy,
    ) -> tuple[DynamicStatePolicy, dict[str, DynamicStateDecayRule]]:
        policy_id = policy.policy_id.strip()
        version = policy.version.strip()
        if not policy_id:
            raise DynamicStateContractError("policy_id must be non-empty")
        if not version:
            raise DynamicStateContractError("policy version must be non-empty")
        max_age = _require_positive_finite(
            policy.max_state_age_seconds,
            "max_state_age_seconds",
        )

        expected = {rule.name for rule in self._field.law.variables}
        rules: dict[str, DynamicStateDecayRule] = {}
        for raw in policy.rules:
            variable = raw.field_variable.strip()
            if not variable:
                raise DynamicStateContractError(
                    "field_variable must be non-empty"
                )
            if variable in rules:
                raise DynamicStateContractError(
                    "dynamic state policy variables must be unique"
                )
            if variable not in expected:
                raise DynamicStateContractError(
                    f"dynamic state policy references unknown variable {variable!r}"
                )
            grace = _require_nonnegative_finite(
                raw.grace_seconds,
                f"{variable} grace_seconds",
            )
            rate = _require_nonnegative_finite(
                raw.attenuation_rate_per_second,
                f"{variable} attenuation_rate_per_second",
            )
            if grace > max_age:
                raise DynamicStateContractError(
                    f"{variable} grace_seconds cannot exceed max_state_age_seconds"
                )
            rules[variable] = DynamicStateDecayRule(
                field_variable=variable,
                grace_seconds=grace,
                attenuation_rate_per_second=rate,
            )

        if set(rules) != expected:
            missing = ",".join(sorted(expected - set(rules)))
            raise DynamicStateContractError(
                "dynamic state policy must cover every field variable"
                + (f": missing {missing}" if missing else "")
            )

        normalized = DynamicStatePolicy(
            policy_id=policy_id,
            version=version,
            max_state_age_seconds=max_age,
            rules=tuple(rules[name] for name in sorted(rules)),
        )
        return normalized, rules

    @staticmethod
    def _require_fresh_anchor(state: DynamicFieldState) -> None:
        if (
            state.applied_event_ids
            and state.applied_event_ids[-1].startswith("dynamic-state:")
        ):
            raise DynamicStateContractError(
                "lifecycle-derived state cannot reset its own temporal anchor; "
                "a fresh external field event is required"
            )

    def _receipt(
        self,
        *,
        status: str,
        reason: str,
        state: DynamicFieldState,
        anchor_event_id: str,
        activated_at_utc: str,
        observed_at_utc: str,
        age_seconds: float,
        effective_state: DynamicFieldState | None,
        transition_id: str | None,
        transition_sha256: str | None,
        changes: tuple[DynamicStateValueChange, ...],
        state_consumable: bool,
        terminated: bool,
    ) -> DynamicStateReceipt:
        payload: dict[str, object] = {
            "schema": DYNAMIC_STATE_RECEIPT_SCHEMA_VERSION,
            "status": status,
            "reason": reason,
            "policy_id": self._policy.policy_id,
            "policy_sha256": self._policy.policy_sha256,
            "field_law_sha256": self._field.law.law_sha256,
            "source_field_state_sha256": state.state_sha256,
            "source_field_revision": state.revision,
            "anchor_event_id": anchor_event_id,
            "activated_at_utc": activated_at_utc,
            "observed_at_utc": observed_at_utc,
            "age_seconds": age_seconds,
            "max_state_age_seconds": self._policy.max_state_age_seconds,
            "effective_field_state_sha256": (
                effective_state.state_sha256
                if effective_state is not None
                else None
            ),
            "effective_field_revision": (
                effective_state.revision
                if effective_state is not None
                else None
            ),
            "transition_id": transition_id,
            "transition_sha256": transition_sha256,
            "changes": [item.to_dict() for item in changes],
            "state_consumable": state_consumable,
            "terminated": terminated,
            "governing_law_mutated": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return DynamicStateReceipt(
            schema=DYNAMIC_STATE_RECEIPT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            policy_id=self._policy.policy_id,
            policy_sha256=self._policy.policy_sha256,
            field_law_sha256=self._field.law.law_sha256,
            source_field_state_sha256=state.state_sha256,
            source_field_revision=state.revision,
            anchor_event_id=anchor_event_id,
            activated_at_utc=activated_at_utc,
            observed_at_utc=observed_at_utc,
            age_seconds=age_seconds,
            max_state_age_seconds=self._policy.max_state_age_seconds,
            effective_field_state_sha256=(
                effective_state.state_sha256
                if effective_state is not None
                else None
            ),
            effective_field_revision=(
                effective_state.revision
                if effective_state is not None
                else None
            ),
            transition_id=transition_id,
            transition_sha256=transition_sha256,
            changes=changes,
            state_consumable=state_consumable,
            terminated=terminated,
            governing_law_mutated=False,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )


def _move_toward(current: float, target: float, amount: float) -> float:
    if amount <= 0.0 or current == target:
        return current
    if current > target:
        return max(target, current - amount)
    return min(target, current + amount)


def _parse_time(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DynamicStateContractError(f"{label} must be non-empty")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise DynamicStateContractError(
            f"{label} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DynamicStateContractError(
            f"{label} must include an explicit UTC offset"
        )
    return parsed.astimezone(UTC)


def _require_positive_finite(value: object, label: str) -> float:
    number = _require_nonnegative_finite(value, label)
    if number <= 0.0:
        raise DynamicStateContractError(f"{label} must be > 0")
    return number


def _require_nonnegative_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DynamicStateContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise DynamicStateContractError(
            f"{label} must be finite and non-negative"
        )
    return _stable_float(number)


def _stable_float(value: float) -> float:
    return round(float(value), 12)


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
        raise DynamicStateContractError(
            "dynamic state payload must be canonical JSON"
        ) from exc


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(value)).encode("utf-8")
    ).hexdigest()
