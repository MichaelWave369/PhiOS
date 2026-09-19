"""Advisory structural geometry for reducing governed PhiOS state spaces.

This module reasons about equivalence classes, admissible regions, conserved
invariants, and quotient-space search. It never grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence


State = Any
StateId = Callable[[State], str]
StateKey = Callable[[State], object]
StatePredicate = Callable[[State], bool]
StateExpansion = Callable[[State], Iterable[State]]


class GeometryContractError(ValueError):
    """Raised when a geometric reasoning contract cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class ConstraintSpec:
    """Named admissibility predicate."""

    name: str
    predicate: StatePredicate


@dataclass(frozen=True, slots=True)
class InvariantSpec:
    """Named invariant, optionally declared conserved by the transition set."""

    name: str
    evaluate: StateKey
    conserved: bool = True


@dataclass(frozen=True, slots=True)
class QuotientClass:
    """One equivalence class in the reduced state space."""

    key_sha256: str
    representative_id: str
    member_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "key_sha256": self.key_sha256,
            "representative_id": self.representative_id,
            "member_ids": list(self.member_ids),
        }


@dataclass(frozen=True, slots=True)
class ReductionReceipt:
    """Deterministic receipt for quotient-space reduction."""

    schema: str
    raw_state_count: int
    admissible_state_count: int
    rejected_state_count: int
    quotient_class_count: int
    classes: tuple[QuotientClass, ...]
    rejections: tuple[tuple[str, tuple[str, ...]], ...]
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "raw_state_count": self.raw_state_count,
            "admissible_state_count": self.admissible_state_count,
            "rejected_state_count": self.rejected_state_count,
            "quotient_class_count": self.quotient_class_count,
            "classes": [item.to_dict() for item in self.classes],
            "rejections": [
                {"state_id": state_id, "reasons": list(reasons)}
                for state_id, reasons in self.rejections
            ],
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class InvariantReceipt:
    """Narrow proof about conserved-invariant compatibility."""

    schema: str
    source_id: str
    target_id: str
    invariant_matches: tuple[tuple[str, bool], ...]
    mismatched_conserved_invariants: tuple[str, ...]
    status: str
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "invariant_matches": [
                {"name": name, "matches": matches}
                for name, matches in self.invariant_matches
            ],
            "mismatched_conserved_invariants": list(self.mismatched_conserved_invariants),
            "status": self.status,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class SearchReceipt:
    """Receipt for a bounded quotient-space search."""

    schema: str
    status: str
    raw_states_seen: int
    quotient_classes_visited: int
    states_pruned: int
    equivalent_states_skipped: int
    representative_path_ids: tuple[str, ...]
    solution_id: str | None
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "raw_states_seen": self.raw_states_seen,
            "quotient_classes_visited": self.quotient_classes_visited,
            "states_pruned": self.states_pruned,
            "equivalent_states_skipped": self.equivalent_states_skipped,
            "representative_path_ids": list(self.representative_path_ids),
            "solution_id": self.solution_id,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GeometricReasoner:
    """Advisory reducer and bounded search engine over structural state geometry."""

    def __init__(
        self,
        *,
        state_id: StateId,
        equivalence_key: StateKey,
        constraints: Sequence[ConstraintSpec] = (),
        invariants: Sequence[InvariantSpec] = (),
    ) -> None:
        self._state_id = state_id
        self._equivalence_key = equivalence_key
        self._constraints = tuple(constraints)
        self._invariants = tuple(invariants)
        _require_unique_names("constraint", [item.name for item in self._constraints])
        _require_unique_names("invariant", [item.name for item in self._invariants])

    def reduce(self, states: Iterable[State]) -> ReductionReceipt:
        materialized = list(states)
        identified = sorted(
            ((_require_state_id(self._state_id(state)), state) for state in materialized),
            key=lambda pair: pair[0],
        )
        _require_unique_state_ids(identified)

        buckets: dict[str, list[str]] = {}
        rejections: list[tuple[str, tuple[str, ...]]] = []

        for state_id, state in identified:
            reasons = self._constraint_failures(state)
            if reasons:
                rejections.append((state_id, reasons))
                continue
            key_sha = self._class_digest(state)
            buckets.setdefault(key_sha, []).append(state_id)

        classes = tuple(
            QuotientClass(
                key_sha256=key_sha,
                representative_id=sorted(member_ids)[0],
                member_ids=tuple(sorted(member_ids)),
            )
            for key_sha, member_ids in sorted(buckets.items())
        )
        raw_state_count = len(materialized)
        admissible_state_count = sum(len(item.member_ids) for item in classes)
        rejected_state_count = len(rejections)
        quotient_class_count = len(classes)
        payload: dict[str, object] = {
            "schema": "phios.geometric_reduction_receipt.v0.1",
            "raw_state_count": raw_state_count,
            "admissible_state_count": admissible_state_count,
            "rejected_state_count": rejected_state_count,
            "quotient_class_count": quotient_class_count,
            "classes": [item.to_dict() for item in classes],
            "rejections": [
                {"state_id": state_id, "reasons": list(reasons)}
                for state_id, reasons in rejections
            ],
            "action_authority": False,
        }
        return ReductionReceipt(
            schema="phios.geometric_reduction_receipt.v0.1",
            raw_state_count=raw_state_count,
            admissible_state_count=admissible_state_count,
            rejected_state_count=rejected_state_count,
            quotient_class_count=quotient_class_count,
            classes=classes,
            rejections=tuple(rejections),
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )

    def compare_invariants(self, source: State, target: State) -> InvariantReceipt:
        source_id = _require_state_id(self._state_id(source))
        target_id = _require_state_id(self._state_id(target))
        matches: list[tuple[str, bool]] = []
        mismatched_conserved: list[str] = []

        for spec in self._invariants:
            try:
                source_value = _canonical_json(spec.evaluate(source))
                target_value = _canonical_json(spec.evaluate(target))
            except Exception as exc:
                raise GeometryContractError(
                    f"invariant {spec.name!r} could not be evaluated: {type(exc).__name__}"
                ) from exc
            same = source_value == target_value
            matches.append((spec.name, same))
            if spec.conserved and not same:
                mismatched_conserved.append(spec.name)

        status = (
            "unreachable_under_conserved_invariants"
            if mismatched_conserved
            else "not_disproved_by_conserved_invariants"
        )
        payload: dict[str, object] = {
            "schema": "phios.geometric_invariant_receipt.v0.1",
            "source_id": source_id,
            "target_id": target_id,
            "invariant_matches": [
                {"name": name, "matches": same}
                for name, same in matches
            ],
            "mismatched_conserved_invariants": mismatched_conserved,
            "status": status,
            "action_authority": False,
        }
        return InvariantReceipt(
            schema="phios.geometric_invariant_receipt.v0.1",
            source_id=source_id,
            target_id=target_id,
            invariant_matches=tuple(matches),
            mismatched_conserved_invariants=tuple(mismatched_conserved),
            status=status,
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )

    def search(
        self,
        starts: Iterable[State],
        *,
        expand: StateExpansion,
        goal: StatePredicate,
        max_classes: int = 10_000,
    ) -> SearchReceipt:
        if max_classes < 1:
            raise ValueError("max_classes must be >= 1")

        start_states = sorted(
            list(starts),
            key=lambda state: _require_state_id(self._state_id(state)),
        )
        queue: deque[tuple[State, str | None]] = deque(
            (state, None) for state in start_states
        )
        visited: dict[str, tuple[str, str | None]] = {}
        raw_states_seen = 0
        states_pruned = 0
        equivalent_states_skipped = 0
        solution_class: str | None = None
        status = "exhausted"

        while queue:
            state, parent_class = queue.popleft()
            raw_states_seen += 1
            state_id = _require_state_id(self._state_id(state))

            if self._constraint_failures(state):
                states_pruned += 1
                continue

            class_sha = self._class_digest(state)
            if class_sha in visited:
                equivalent_states_skipped += 1
                continue

            visited[class_sha] = (state_id, parent_class)

            try:
                is_goal = bool(goal(state))
            except Exception as exc:
                raise GeometryContractError(
                    f"goal predicate could not be evaluated: {type(exc).__name__}"
                ) from exc
            if is_goal:
                solution_class = class_sha
                status = "found"
                break

            if len(visited) >= max_classes:
                status = "limit_reached"
                break

            try:
                neighbors = list(expand(state))
            except Exception as exc:
                raise GeometryContractError(
                    f"state expansion failed: {type(exc).__name__}"
                ) from exc
            neighbors.sort(
                key=lambda item: _require_state_id(self._state_id(item))
            )
            queue.extend((neighbor, class_sha) for neighbor in neighbors)

        path: tuple[str, ...] = ()
        solution_id: str | None = None
        if solution_class is not None:
            path_ids: list[str] = []
            cursor: str | None = solution_class
            while cursor is not None:
                state_id, parent = visited[cursor]
                path_ids.append(state_id)
                cursor = parent
            path = tuple(reversed(path_ids))
            solution_id = visited[solution_class][0]

        payload: dict[str, object] = {
            "schema": "phios.geometric_search_receipt.v0.1",
            "status": status,
            "raw_states_seen": raw_states_seen,
            "quotient_classes_visited": len(visited),
            "states_pruned": states_pruned,
            "equivalent_states_skipped": equivalent_states_skipped,
            "representative_path_ids": list(path),
            "solution_id": solution_id,
            "action_authority": False,
        }
        return SearchReceipt(
            schema="phios.geometric_search_receipt.v0.1",
            status=status,
            raw_states_seen=raw_states_seen,
            quotient_classes_visited=len(visited),
            states_pruned=states_pruned,
            equivalent_states_skipped=equivalent_states_skipped,
            representative_path_ids=path,
            solution_id=solution_id,
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )

    def _constraint_failures(self, state: State) -> tuple[str, ...]:
        failures: list[str] = []
        for spec in self._constraints:
            try:
                accepted = bool(spec.predicate(state))
            except Exception:
                accepted = False
            if not accepted:
                failures.append(spec.name)
        return tuple(failures)

    def _class_digest(self, state: State) -> str:
        try:
            key = self._equivalence_key(state)
            canonical = _canonical_json(key)
        except Exception as exc:
            raise GeometryContractError(
                f"equivalence key could not be evaluated: {type(exc).__name__}"
            ) from exc
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        raise GeometryContractError(
            "geometric keys must be canonical JSON values"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()


def _require_state_id(value: object) -> str:
    state_id = str(value).strip()
    if not state_id:
        raise GeometryContractError("state_id must be non-empty")
    return state_id


def _require_unique_names(kind: str, names: Sequence[str]) -> None:
    normalized = [name.strip() for name in names]
    if any(not name for name in normalized):
        raise GeometryContractError(f"{kind} names must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise GeometryContractError(f"{kind} names must be unique")


def _require_unique_state_ids(
    identified: Sequence[tuple[str, State]],
) -> None:
    ids = [state_id for state_id, _ in identified]
    if len(set(ids)) != len(ids):
        raise GeometryContractError(
            "state_id values must be unique for reduction"
        )
