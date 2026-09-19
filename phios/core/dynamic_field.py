"""Dynamic advisory field state for PhiOS core reasoning v0.3.

Evidence, contradiction, failures, and resource signals may update bounded field
variables under an immutable declared law. Field evolution never grants action
authority and never rewrites the governing law.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence


class DynamicFieldContractError(ValueError):
    """Raised when a dynamic-field contract cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class FieldVariableRule:
    """Immutable update law for one dynamic field variable."""

    name: str
    minimum: float
    maximum: float
    initial: float
    allowed_event_kinds: tuple[str, ...]
    max_abs_delta: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "initial": self.initial,
            "allowed_event_kinds": sorted(self.allowed_event_kinds),
            "max_abs_delta": self.max_abs_delta,
        }


@dataclass(frozen=True, slots=True)
class DynamicFieldLaw:
    """Immutable collection of bounded variable-update rules."""

    law_id: str
    version: str
    variables: tuple[FieldVariableRule, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.dynamic_field_law.v0.3",
            "law_id": self.law_id,
            "version": self.version,
            "variables": [
                rule.to_dict()
                for rule in sorted(self.variables, key=lambda item: item.name)
            ],
        }

    @property
    def law_sha256(self) -> str:
        return _payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class FieldEvent:
    """One requested field update anchored to an external observation when available."""

    event_id: str
    kind: str
    deltas: Mapping[str, float]
    source_label: str
    evidence_sha256: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.dynamic_field_event.v0.3",
            "event_id": self.event_id,
            "kind": self.kind,
            "deltas": {
                key: self.deltas[key]
                for key in sorted(self.deltas)
            },
            "source_label": self.source_label,
            "evidence_sha256": self.evidence_sha256,
        }

    @property
    def event_sha256(self) -> str:
        return _payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class DynamicFieldState:
    """Immutable snapshot of the current advisory field."""

    schema: str
    law_sha256: str
    revision: int
    values: tuple[tuple[str, float], ...]
    applied_event_ids: tuple[str, ...]
    event_chain_sha256: str
    action_authority: bool
    state_sha256: str

    def value(self, name: str) -> float:
        for key, value in self.values:
            if key == name:
                return value
        raise KeyError(name)

    def as_mapping(self) -> dict[str, float]:
        return dict(self.values)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "law_sha256": self.law_sha256,
            "revision": self.revision,
            "values": {key: value for key, value in self.values},
            "applied_event_ids": list(self.applied_event_ids),
            "event_chain_sha256": self.event_chain_sha256,
            "action_authority": self.action_authority,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class FieldValueChange:
    """One accepted bounded variable change."""

    name: str
    before: float
    requested_delta: float
    after: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "before": self.before,
            "requested_delta": self.requested_delta,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class FieldUpdateReceipt:
    """Deterministic receipt for one attempted field event."""

    schema: str
    status: str
    event_id: str
    event_sha256: str
    law_sha256: str
    prior_state_sha256: str
    next_state_sha256: str
    revision_before: int
    revision_after: int
    changes: tuple[FieldValueChange, ...]
    blocked_by: tuple[str, ...]
    governing_law_mutated: bool
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "event_id": self.event_id,
            "event_sha256": self.event_sha256,
            "law_sha256": self.law_sha256,
            "prior_state_sha256": self.prior_state_sha256,
            "next_state_sha256": self.next_state_sha256,
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "changes": [item.to_dict() for item in self.changes],
            "blocked_by": list(self.blocked_by),
            "governing_law_mutated": self.governing_law_mutated,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class DynamicField:
    """Apply bounded events to an immutable-law dynamic advisory field."""

    def __init__(self, law: DynamicFieldLaw) -> None:
        self._law = law
        self._rules = self._validate_law(law)

    @property
    def law(self) -> DynamicFieldLaw:
        return self._law

    def initialize(self) -> DynamicFieldState:
        values = tuple(
            sorted(
                (
                    name,
                    rule.initial,
                )
                for name, rule in self._rules.items()
            )
        )
        return self._build_state(
            revision=0,
            values=values,
            applied_event_ids=(),
            event_chain_sha256=_text_digest("phios.dynamic_field_chain.v0.3"),
        )

    def apply_event(
        self,
        state: DynamicFieldState,
        event: FieldEvent,
    ) -> tuple[DynamicFieldState, FieldUpdateReceipt]:
        self._validate_state(state)
        normalized_event = self._validate_event(event)
        event_sha256 = normalized_event.event_sha256

        blocked_by: list[str] = []
        pending: list[FieldValueChange] = []
        current = state.as_mapping()

        if normalized_event.event_id in state.applied_event_ids:
            blocked_by.append("event_replay")

        for name, delta in sorted(normalized_event.deltas.items()):
            rule = self._rules[name]
            if normalized_event.kind not in rule.allowed_event_kinds:
                blocked_by.append(f"{name}:event_kind_not_allowed")
                continue
            if abs(delta) > rule.max_abs_delta:
                blocked_by.append(f"{name}:delta_exceeds_rule")
                continue
            after = current[name] + delta
            if after < rule.minimum or after > rule.maximum:
                blocked_by.append(f"{name}:value_out_of_bounds")
                continue
            pending.append(
                FieldValueChange(
                    name=name,
                    before=current[name],
                    requested_delta=delta,
                    after=after,
                )
            )

        if blocked_by:
            receipt = self._build_receipt(
                status="blocked",
                event=normalized_event,
                event_sha256=event_sha256,
                prior=state,
                next_state=state,
                changes=(),
                blocked_by=tuple(sorted(set(blocked_by))),
            )
            return state, receipt

        updated = dict(current)
        for change in pending:
            updated[change.name] = change.after

        next_chain = _text_digest(
            f"{state.event_chain_sha256}:{event_sha256}"
        )
        next_state = self._build_state(
            revision=state.revision + 1,
            values=tuple(sorted(updated.items())),
            applied_event_ids=state.applied_event_ids + (normalized_event.event_id,),
            event_chain_sha256=next_chain,
        )
        receipt = self._build_receipt(
            status="applied",
            event=normalized_event,
            event_sha256=event_sha256,
            prior=state,
            next_state=next_state,
            changes=tuple(pending),
            blocked_by=(),
        )
        return next_state, receipt

    def _validate_law(
        self,
        law: DynamicFieldLaw,
    ) -> dict[str, FieldVariableRule]:
        law_id = law.law_id.strip()
        version = law.version.strip()
        if not law_id:
            raise DynamicFieldContractError("law_id must be non-empty")
        if not version:
            raise DynamicFieldContractError("law version must be non-empty")
        if not law.variables:
            raise DynamicFieldContractError("law must define at least one variable")

        rules: dict[str, FieldVariableRule] = {}
        for rule in law.variables:
            name = rule.name.strip()
            if not name:
                raise DynamicFieldContractError("variable names must be non-empty")
            if name in rules:
                raise DynamicFieldContractError("variable names must be unique")
            minimum = _require_finite(rule.minimum, f"{name} minimum")
            maximum = _require_finite(rule.maximum, f"{name} maximum")
            initial = _require_finite(rule.initial, f"{name} initial")
            max_abs_delta = _require_nonnegative_finite(
                rule.max_abs_delta,
                f"{name} max_abs_delta",
            )
            if minimum > maximum:
                raise DynamicFieldContractError(
                    f"{name} minimum must be <= maximum"
                )
            if initial < minimum or initial > maximum:
                raise DynamicFieldContractError(
                    f"{name} initial value must be inside bounds"
                )
            kinds = tuple(item.strip() for item in rule.allowed_event_kinds)
            if not kinds or any(not item for item in kinds):
                raise DynamicFieldContractError(
                    f"{name} must declare non-empty allowed event kinds"
                )
            if len(set(kinds)) != len(kinds):
                raise DynamicFieldContractError(
                    f"{name} allowed event kinds must be unique"
                )
            rules[name] = FieldVariableRule(
                name=name,
                minimum=minimum,
                maximum=maximum,
                initial=initial,
                allowed_event_kinds=kinds,
                max_abs_delta=max_abs_delta,
            )
        return rules

    def _validate_event(self, event: FieldEvent) -> FieldEvent:
        event_id = event.event_id.strip()
        kind = event.kind.strip()
        source_label = event.source_label.strip()
        if not event_id:
            raise DynamicFieldContractError("event_id must be non-empty")
        if not kind:
            raise DynamicFieldContractError("event kind must be non-empty")
        if not source_label:
            raise DynamicFieldContractError("event source_label must be non-empty")
        if not event.deltas:
            raise DynamicFieldContractError("event must update at least one field variable")

        normalized_deltas: dict[str, float] = {}
        for raw_name, raw_delta in event.deltas.items():
            name = str(raw_name).strip()
            if name not in self._rules:
                raise DynamicFieldContractError(
                    f"event references unknown field variable {name!r}"
                )
            normalized_deltas[name] = _require_finite(
                raw_delta,
                f"{name} requested delta",
            )

        evidence_sha256 = event.evidence_sha256
        if evidence_sha256 is not None:
            evidence_sha256 = evidence_sha256.strip().lower()
            if not _is_sha256(evidence_sha256):
                raise DynamicFieldContractError(
                    "evidence_sha256 must be a 64-character hexadecimal SHA-256"
                )

        return FieldEvent(
            event_id=event_id,
            kind=kind,
            deltas=normalized_deltas,
            source_label=source_label,
            evidence_sha256=evidence_sha256,
        )

    def _validate_state(self, state: DynamicFieldState) -> None:
        if state.schema != "phios.dynamic_field_state.v0.3":
            raise DynamicFieldContractError("unsupported dynamic field state schema")
        if state.law_sha256 != self._law.law_sha256:
            raise DynamicFieldContractError(
                "state is bound to a different governing law"
            )
        if state.action_authority is not False:
            raise DynamicFieldContractError(
                "dynamic field state cannot carry action authority"
            )
        if state.revision != len(state.applied_event_ids):
            raise DynamicFieldContractError(
                "state revision does not match applied event count"
            )
        names = [name for name, _ in state.values]
        if names != sorted(self._rules):
            raise DynamicFieldContractError(
                "state variables do not match governing law"
            )
        if len(set(state.applied_event_ids)) != len(state.applied_event_ids):
            raise DynamicFieldContractError(
                "applied event IDs must be unique"
            )

        for name, value in state.values:
            rule = self._rules[name]
            numeric = _require_finite(value, f"{name} state value")
            if numeric < rule.minimum or numeric > rule.maximum:
                raise DynamicFieldContractError(
                    f"{name} state value is outside governing bounds"
                )

        expected = self._state_digest(
            revision=state.revision,
            values=state.values,
            applied_event_ids=state.applied_event_ids,
            event_chain_sha256=state.event_chain_sha256,
        )
        if expected != state.state_sha256:
            raise DynamicFieldContractError(
                "dynamic field state hash does not match state contents"
            )

    def _build_state(
        self,
        *,
        revision: int,
        values: tuple[tuple[str, float], ...],
        applied_event_ids: tuple[str, ...],
        event_chain_sha256: str,
    ) -> DynamicFieldState:
        digest = self._state_digest(
            revision=revision,
            values=values,
            applied_event_ids=applied_event_ids,
            event_chain_sha256=event_chain_sha256,
        )
        return DynamicFieldState(
            schema="phios.dynamic_field_state.v0.3",
            law_sha256=self._law.law_sha256,
            revision=revision,
            values=values,
            applied_event_ids=applied_event_ids,
            event_chain_sha256=event_chain_sha256,
            action_authority=False,
            state_sha256=digest,
        )

    def _state_digest(
        self,
        *,
        revision: int,
        values: tuple[tuple[str, float], ...],
        applied_event_ids: tuple[str, ...],
        event_chain_sha256: str,
    ) -> str:
        payload: dict[str, object] = {
            "schema": "phios.dynamic_field_state.v0.3",
            "law_sha256": self._law.law_sha256,
            "revision": revision,
            "values": {key: value for key, value in values},
            "applied_event_ids": list(applied_event_ids),
            "event_chain_sha256": event_chain_sha256,
            "action_authority": False,
        }
        return _payload_digest(payload)

    def _build_receipt(
        self,
        *,
        status: str,
        event: FieldEvent,
        event_sha256: str,
        prior: DynamicFieldState,
        next_state: DynamicFieldState,
        changes: tuple[FieldValueChange, ...],
        blocked_by: tuple[str, ...],
    ) -> FieldUpdateReceipt:
        payload: dict[str, object] = {
            "schema": "phios.dynamic_field_update_receipt.v0.3",
            "status": status,
            "event_id": event.event_id,
            "event_sha256": event_sha256,
            "law_sha256": self._law.law_sha256,
            "prior_state_sha256": prior.state_sha256,
            "next_state_sha256": next_state.state_sha256,
            "revision_before": prior.revision,
            "revision_after": next_state.revision,
            "changes": [item.to_dict() for item in changes],
            "blocked_by": list(blocked_by),
            "governing_law_mutated": False,
            "action_authority": False,
        }
        return FieldUpdateReceipt(
            schema="phios.dynamic_field_update_receipt.v0.3",
            status=status,
            event_id=event.event_id,
            event_sha256=event_sha256,
            law_sha256=self._law.law_sha256,
            prior_state_sha256=prior.state_sha256,
            next_state_sha256=next_state.state_sha256,
            revision_before=prior.revision,
            revision_after=next_state.revision,
            changes=changes,
            blocked_by=blocked_by,
            governing_law_mutated=False,
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )


def _require_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DynamicFieldContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise DynamicFieldContractError(f"{label} must be finite")
    return number


def _require_nonnegative_finite(value: object, label: str) -> float:
    number = _require_finite(value, label)
    if number < 0:
        raise DynamicFieldContractError(f"{label} must be non-negative")
    return number


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
        raise DynamicFieldContractError(
            "dynamic field payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return _text_digest(_canonical_json(dict(payload)))


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
