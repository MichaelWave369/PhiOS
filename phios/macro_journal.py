"""Append-only MacroRun journal and restart-safe reconstruction.

v0.6 persists deterministic MacroRunState snapshots as a hash-chained journal.
The journal can reconstruct the latest valid state after restart, but it does
not execute work, resolve authority, or rewrite prior history.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_graph import MacroPlan
from phios.macro_runner import (
    TERMINAL_STATUSES,
    MacroRunState,
    RunnerStatus,
)
from phios.spine.ledger import RealityLedger

MACRO_RUN_JOURNAL_SCHEMA_VERSION = "phios.macro_run_journal.v0.6"
MACRO_RUN_RESUME_RECEIPT_SCHEMA_VERSION = "phios.macro_run_resume.v0.6"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MacroRunJournalContractError(ValueError):
    """Raised when a persistent macro-run chain cannot be trusted."""


class JournalEntryKind(StrEnum):
    START = "START"
    TRANSITION = "TRANSITION"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroRunJournalContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise MacroRunJournalContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise MacroRunJournalContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise MacroRunJournalContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MacroRunJournalContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise MacroRunJournalContractError(
            f"{field} must include a timezone"
        )
    return text


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MacroRunJournalContractError(
            f"{field} must be an integer"
        )
    if value < minimum:
        raise MacroRunJournalContractError(
            f"{field} must be at least {minimum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise MacroRunJournalContractError(
            f"{field} must be Boolean"
        )
    return value


def _require_counter_pairs(
    value: object,
    field: str,
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list):
        raise MacroRunJournalContractError(
            f"{field} must be a list"
        )
    result: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise MacroRunJournalContractError(
                f"{field} items must be two-item lists"
            )
        key = _require_sha256(item[0], f"{field} key")
        count = _require_int(item[1], f"{field} count")
        result.append((key, count))
    return tuple(result)


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
        raise MacroRunJournalContractError(
            "macro run journal payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_evidence(values: tuple[str, ...]) -> tuple[str, ...]:
    for value in values:
        _require_sha256(value, "evidence_ref_sha256")
    if tuple(sorted(set(values))) != values:
        raise MacroRunJournalContractError(
            "evidence_ref_sha256s must be sorted and unique"
        )
    return values


def _state_from_dict(payload: Mapping[str, object]) -> MacroRunState:
    claimed_hash = _require_sha256(
        payload.get("state_sha256"),
        "state.state_sha256",
    )
    try:
        status = RunnerStatus(
            _require_text(payload.get("status"), "state.status")
        )
    except ValueError as exc:
        raise MacroRunJournalContractError(
            "persisted MacroRunState status is unsupported"
        ) from exc

    loop_iterations = _require_counter_pairs(
        payload.get("loop_iterations"),
        "state.loop_iterations",
    )
    foreach_indices = _require_counter_pairs(
        payload.get("foreach_indices"),
        "state.foreach_indices",
    )

    variables_raw = payload.get("variables")
    waiting_raw = payload.get("waiting_on")
    if not isinstance(variables_raw, dict):
        raise MacroRunJournalContractError(
            "persisted MacroRunState variables must be an object"
        )
    if not isinstance(waiting_raw, dict):
        raise MacroRunJournalContractError(
            "persisted MacroRunState waiting_on must be an object"
        )
    last_path_raw = payload.get("last_instruction_path")
    if last_path_raw is not None and not isinstance(last_path_raw, str):
        raise MacroRunJournalContractError(
            "persisted last_instruction_path must be string or null"
        )

    state = MacroRunState(
        macro_id=_require_text(payload.get("macro_id"), "state.macro_id"),
        macro_version=_require_text(
            payload.get("macro_version"),
            "state.macro_version",
            maximum=128,
        ),
        plan_sha256=_require_sha256(
            payload.get("plan_sha256"),
            "state.plan_sha256",
        ),
        cursor=_require_int(payload.get("cursor"), "state.cursor"),
        status=status,
        reason=_require_text(payload.get("reason"), "state.reason"),
        loop_iterations=loop_iterations,
        foreach_indices=foreach_indices,
        variables=dict(variables_raw),
        waiting_on=dict(waiting_raw),
        last_instruction_path=last_path_raw,
        transitions=_require_int(
            payload.get("transitions"),
            "state.transitions",
        ),
        operational_authority=_require_bool(
            payload.get("operational_authority"),
            "state.operational_authority",
        ),
        action_authority=_require_bool(
            payload.get("action_authority"),
            "state.action_authority",
        ),
        execution_authority=_require_bool(
            payload.get("execution_authority"),
            "state.execution_authority",
        ),
        schema_version=_require_text(
            payload.get("schema_version"),
            "state.schema_version",
        ),
    )

    if state.state_sha256 != claimed_hash:
        raise MacroRunJournalContractError(
            "persisted MacroRunState hash mismatch"
        )
    return state


@dataclass(frozen=True, slots=True)
class MacroRunJournalEntry:
    """One immutable snapshot in a hash-chained MacroRun history."""

    run_id: str
    sequence: int
    kind: JournalEntryKind
    macro_id: str
    macro_version: str
    plan_sha256: str
    previous_entry_sha256: str | None
    previous_state_sha256: str | None
    state_sha256: str
    state: dict[str, object]
    evidence_ref_sha256s: tuple[str, ...] = ()
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = MACRO_RUN_JOURNAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_RUN_JOURNAL_SCHEMA_VERSION:
            raise MacroRunJournalContractError(
                "unsupported macro run journal schema"
            )
        _require_text(self.run_id, "run_id")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise MacroRunJournalContractError(
                "journal sequence must be an integer"
            )
        if self.sequence < 0:
            raise MacroRunJournalContractError(
                "journal sequence must be non-negative"
            )
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        _require_sha256(self.state_sha256, "state_sha256")
        if self.previous_entry_sha256 is not None:
            _require_sha256(
                self.previous_entry_sha256,
                "previous_entry_sha256",
            )
        if self.previous_state_sha256 is not None:
            _require_sha256(
                self.previous_state_sha256,
                "previous_state_sha256",
            )
        _canonical_evidence(self.evidence_ref_sha256s)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunJournalContractError(
                "MacroRunJournalEntry cannot carry authority"
            )

        reconstructed = _state_from_dict(self.state)
        if reconstructed.state_sha256 != self.state_sha256:
            raise MacroRunJournalContractError(
                "journal state_sha256 does not match persisted state"
            )
        if (
            reconstructed.macro_id != self.macro_id
            or reconstructed.macro_version != self.macro_version
            or reconstructed.plan_sha256 != self.plan_sha256
        ):
            raise MacroRunJournalContractError(
                "journal identity does not match persisted state"
            )

        if self.sequence == 0:
            if self.kind is not JournalEntryKind.START:
                raise MacroRunJournalContractError(
                    "sequence zero journal entry must be START"
                )
            if (
                self.previous_entry_sha256 is not None
                or self.previous_state_sha256 is not None
            ):
                raise MacroRunJournalContractError(
                    "START entry cannot reference prior history"
                )
        else:
            if self.kind is not JournalEntryKind.TRANSITION:
                raise MacroRunJournalContractError(
                    "nonzero journal entry must be TRANSITION"
                )
            if (
                self.previous_entry_sha256 is None
                or self.previous_state_sha256 is None
            ):
                raise MacroRunJournalContractError(
                    "TRANSITION entry requires prior hashes"
                )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "previous_entry_sha256": self.previous_entry_sha256,
            "previous_state_sha256": self.previous_state_sha256,
            "state_sha256": self.state_sha256,
            "state": dict(self.state),
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def entry_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["entry_sha256"] = self.entry_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "MacroRunJournalEntry":
        claimed_hash = _require_sha256(
            payload.get("entry_sha256"),
            "entry_sha256",
        )
        state_raw = payload.get("state")
        if not isinstance(state_raw, dict):
            raise MacroRunJournalContractError(
                "journal state must be an object"
            )
        evidence_raw = payload.get("evidence_ref_sha256s", [])
        if not isinstance(evidence_raw, list) or not all(
            isinstance(item, str) for item in evidence_raw
        ):
            raise MacroRunJournalContractError(
                "evidence_ref_sha256s must be a string list"
            )
        try:
            entry = cls(
                run_id=str(payload["run_id"]),
                sequence=_require_int(
                    payload.get("sequence"),
                    "journal sequence",
                ),
                kind=JournalEntryKind(str(payload["kind"])),
                macro_id=str(payload["macro_id"]),
                macro_version=str(payload["macro_version"]),
                plan_sha256=str(payload["plan_sha256"]),
                previous_entry_sha256=(
                    None
                    if payload.get("previous_entry_sha256") is None
                    else str(payload["previous_entry_sha256"])
                ),
                previous_state_sha256=(
                    None
                    if payload.get("previous_state_sha256") is None
                    else str(payload["previous_state_sha256"])
                ),
                state_sha256=str(payload["state_sha256"]),
                state=dict(state_raw),
                evidence_ref_sha256s=tuple(evidence_raw),
                operational_authority=bool(payload["operational_authority"]),
                action_authority=bool(payload["action_authority"]),
                execution_authority=bool(payload["execution_authority"]),
                schema_version=str(payload["schema_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MacroRunJournalContractError(
                "journal entry is malformed"
            ) from exc
        if entry.entry_sha256 != claimed_hash:
            raise MacroRunJournalContractError(
                "journal entry hash mismatch"
            )
        return entry


@dataclass(frozen=True, slots=True)
class MacroRunResumeReceipt:
    """Evidence that one complete journal chain was validated for resume."""

    run_id: str
    macro_id: str
    macro_version: str
    plan_sha256: str
    entry_count: int
    head_entry_sha256: str
    resumed_state_sha256: str
    resumed_status: str
    resumed_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = MACRO_RUN_RESUME_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_RUN_RESUME_RECEIPT_SCHEMA_VERSION:
            raise MacroRunJournalContractError(
                "unsupported macro run resume schema"
            )
        _require_text(self.run_id, "run_id")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        if isinstance(self.entry_count, bool) or not isinstance(
            self.entry_count,
            int,
        ):
            raise MacroRunJournalContractError(
                "entry_count must be an integer"
            )
        if self.entry_count < 1:
            raise MacroRunJournalContractError(
                "entry_count must be positive"
            )
        _require_sha256(self.head_entry_sha256, "head_entry_sha256")
        _require_sha256(self.resumed_state_sha256, "resumed_state_sha256")
        _require_text(self.resumed_status, "resumed_status", maximum=64)
        _require_timestamp(self.resumed_at, "resumed_at")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunJournalContractError(
                "MacroRunResumeReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "entry_count": self.entry_count,
            "head_entry_sha256": self.head_entry_sha256,
            "resumed_state_sha256": self.resumed_state_sha256,
            "resumed_status": self.resumed_status,
            "resumed_at": self.resumed_at,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True, slots=True)
class MacroRunReconstruction:
    state: MacroRunState
    head_entry: MacroRunJournalEntry
    entry_count: int


class MacroRunJournal:
    """Persist and reconstruct immutable MacroRunState history."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise MacroRunJournalContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger

    def append_state(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
        state: MacroRunState,
        expected_head_sha256: str | None,
        evidence_ref_sha256s: tuple[str, ...] = (),
    ) -> MacroRunJournalEntry:
        _require_text(run_id, "run_id")
        self._validate_plan_state(plan=plan, state=state)
        evidence = _canonical_evidence(evidence_ref_sha256s)

        existing = self._load_and_validate(run_id)
        if not existing:
            if expected_head_sha256 is not None:
                raise MacroRunJournalContractError(
                    "new run cannot specify expected journal head"
                )
            entry = MacroRunJournalEntry(
                run_id=run_id,
                sequence=0,
                kind=JournalEntryKind.START,
                macro_id=state.macro_id,
                macro_version=state.macro_version,
                plan_sha256=state.plan_sha256,
                previous_entry_sha256=None,
                previous_state_sha256=None,
                state_sha256=state.state_sha256,
                state=state.to_dict(),
                evidence_ref_sha256s=evidence,
            )
            self._ledger.append_macro_run_journal_entry(entry)
            return entry

        head = existing[-1]
        if expected_head_sha256 is None:
            raise MacroRunJournalContractError(
                "existing run requires expected_head_sha256"
            )
        _require_sha256(expected_head_sha256, "expected_head_sha256")
        if expected_head_sha256 != head.entry_sha256:
            raise MacroRunJournalContractError(
                "expected journal head does not match current head"
            )
        previous_state = _state_from_dict(head.state)
        if previous_state.status in TERMINAL_STATUSES:
            raise MacroRunJournalContractError(
                "terminal MacroRunState cannot be followed by another state"
            )
        if state.state_sha256 == previous_state.state_sha256:
            raise MacroRunJournalContractError(
                "journal transition must change MacroRunState"
            )
        if state.transitions < previous_state.transitions:
            raise MacroRunJournalContractError(
                "journal transition count cannot move backward"
            )

        entry = MacroRunJournalEntry(
            run_id=run_id,
            sequence=head.sequence + 1,
            kind=JournalEntryKind.TRANSITION,
            macro_id=state.macro_id,
            macro_version=state.macro_version,
            plan_sha256=state.plan_sha256,
            previous_entry_sha256=head.entry_sha256,
            previous_state_sha256=previous_state.state_sha256,
            state_sha256=state.state_sha256,
            state=state.to_dict(),
            evidence_ref_sha256s=evidence,
        )
        self._ledger.append_macro_run_journal_entry(entry)
        return entry

    def reconstruct(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
    ) -> MacroRunReconstruction:
        _require_text(run_id, "run_id")
        entries = self._load_and_validate(run_id)
        if not entries:
            raise MacroRunJournalContractError(
                "macro run journal contains no entries for run_id"
            )
        head = entries[-1]
        if head.plan_sha256 != plan.plan_sha256:
            raise MacroRunJournalContractError(
                "journal plan hash does not match supplied MacroPlan"
            )
        if (
            head.macro_id != plan.macro_id
            or head.macro_version != plan.macro_version
        ):
            raise MacroRunJournalContractError(
                "journal macro identity does not match supplied MacroPlan"
            )
        state = _state_from_dict(head.state)
        self._validate_plan_state(plan=plan, state=state)
        return MacroRunReconstruction(
            state=state,
            head_entry=head,
            entry_count=len(entries),
        )

    def resume(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
        resumed_at: str,
    ) -> tuple[MacroRunState, MacroRunResumeReceipt]:
        reconstruction = self.reconstruct(run_id=run_id, plan=plan)
        receipt = MacroRunResumeReceipt(
            run_id=run_id,
            macro_id=plan.macro_id,
            macro_version=plan.macro_version,
            plan_sha256=plan.plan_sha256,
            entry_count=reconstruction.entry_count,
            head_entry_sha256=(
                reconstruction.head_entry.entry_sha256
            ),
            resumed_state_sha256=reconstruction.state.state_sha256,
            resumed_status=reconstruction.state.status.value,
            resumed_at=_require_timestamp(resumed_at, "resumed_at"),
        )
        self._ledger.append_macro_run_resume_receipt(receipt)
        return reconstruction.state, receipt

    def _load_and_validate(
        self,
        run_id: str,
    ) -> list[MacroRunJournalEntry]:
        rows = self._ledger.macro_run_journal_entries(run_id=run_id)
        entries = [
            MacroRunJournalEntry.from_dict(row)
            for row in rows
        ]
        if not entries:
            return []

        first = entries[0]
        for expected_sequence, entry in enumerate(entries):
            if entry.run_id != run_id:
                raise MacroRunJournalContractError(
                    "journal entry run_id mismatch"
                )
            if entry.sequence != expected_sequence:
                raise MacroRunJournalContractError(
                    "journal sequence is not contiguous"
                )
            if (
                entry.macro_id != first.macro_id
                or entry.macro_version != first.macro_version
                or entry.plan_sha256 != first.plan_sha256
            ):
                raise MacroRunJournalContractError(
                    "journal identity changed within one run"
                )
            if expected_sequence == 0:
                continue
            previous = entries[expected_sequence - 1]
            if entry.previous_entry_sha256 != previous.entry_sha256:
                raise MacroRunJournalContractError(
                    "journal previous-entry hash chain mismatch"
                )
            if entry.previous_state_sha256 != previous.state_sha256:
                raise MacroRunJournalContractError(
                    "journal previous-state hash chain mismatch"
                )
            previous_state = _state_from_dict(previous.state)
            current_state = _state_from_dict(entry.state)
            if previous_state.status in TERMINAL_STATUSES:
                raise MacroRunJournalContractError(
                    "journal continues after terminal state"
                )
            if current_state.transitions < previous_state.transitions:
                raise MacroRunJournalContractError(
                    "journal transition count moved backward"
                )
        return entries

    @staticmethod
    def _validate_plan_state(
        *,
        plan: MacroPlan,
        state: MacroRunState,
    ) -> None:
        if not isinstance(plan, MacroPlan):
            raise MacroRunJournalContractError(
                "plan must be a MacroPlan"
            )
        if not isinstance(state, MacroRunState):
            raise MacroRunJournalContractError(
                "state must be a MacroRunState"
            )
        if state.plan_sha256 != plan.plan_sha256:
            raise MacroRunJournalContractError(
                "MacroRunState plan hash does not match MacroPlan"
            )
        if (
            state.macro_id != plan.macro_id
            or state.macro_version != plan.macro_version
        ):
            raise MacroRunJournalContractError(
                "MacroRunState macro identity does not match MacroPlan"
            )
