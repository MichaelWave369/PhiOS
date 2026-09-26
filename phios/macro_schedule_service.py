"""Persistent schedule-service state for Macro Runtime v0.10.

This layer wraps the pure v0.9 wall-clock producer with append-only cursor
state and v0.8 run-start admission. It does not create a background worker,
grant authority, execute macro operations, or bypass the existing start gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_graph import MacroPlan
from phios.macro_schedule import (
    SchedulePollResult,
    ScheduledTrigger,
    WallClockSchedule,
    WallClockScheduleProducer,
)
from phios.macro_start import (
    MacroRunStartGate,
    RunStartAdmission,
    RunStartAdmissionPolicy,
    RunStartRequest,
    StartStatus,
)
from phios.spine.ledger import RealityLedger

SCHEDULE_SERVICE_STATE_SCHEMA_VERSION = "phios.schedule_service_state.v0.10"
SCHEDULE_SERVICE_POLL_SCHEMA_VERSION = "phios.schedule_service_poll.v0.10"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MacroScheduleServiceContractError(ValueError):
    """Raised when persistent schedule-service state cannot be trusted."""


class ScheduleServiceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    HELD = "HELD"


class ScheduleServiceEntryKind(StrEnum):
    START = "START"
    TRANSITION = "TRANSITION"


class SchedulePollStatus(StrEnum):
    COMMITTED = "COMMITTED"
    HELD = "HELD"


_RETRYABLE_HELD_REASONS = {
    "start_policy_disabled",
    "run_id_claimed",
}

_REPLAY_SETTLED_HELD_REASONS = {
    "trigger_already_admitted",
    "run_id_exists",
}


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroScheduleServiceContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise MacroScheduleServiceContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise MacroScheduleServiceContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise MacroScheduleServiceContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MacroScheduleServiceContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise MacroScheduleServiceContractError(
            f"{field} must include a timezone"
        )
    return text


def _parse_utc(value: str, field: str) -> datetime:
    text = _require_timestamp(value, field)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MacroScheduleServiceContractError(
            "schedule service timestamps must be timezone-aware"
        )
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
        raise MacroScheduleServiceContractError(
            "schedule service payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ScheduleServiceStateEntry:
    """One immutable cursor snapshot in a schedule-service hash chain."""

    service_id: str
    sequence: int
    kind: ScheduleServiceEntryKind
    schedule_id: str
    schedule_sha256: str
    macro_id: str
    macro_version: str
    plan_sha256: str
    policy_id: str
    policy_sha256: str
    cursor_utc: str
    status: ScheduleServiceStatus
    reason: str
    previous_entry_sha256: str | None
    last_poll_receipt_sha256: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_SERVICE_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_SERVICE_STATE_SCHEMA_VERSION:
            raise MacroScheduleServiceContractError(
                "unsupported schedule service state schema"
            )
        _require_text(self.service_id, "service_id")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise MacroScheduleServiceContractError(
                "sequence must be an integer"
            )
        if self.sequence < 0:
            raise MacroScheduleServiceContractError(
                "sequence must be non-negative"
            )
        _require_text(self.schedule_id, "schedule_id")
        _require_sha256(self.schedule_sha256, "schedule_sha256")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        _require_text(self.policy_id, "policy_id")
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_timestamp(self.cursor_utc, "cursor_utc")
        _require_text(self.reason, "reason")
        if self.previous_entry_sha256 is not None:
            _require_sha256(
                self.previous_entry_sha256,
                "previous_entry_sha256",
            )
        if self.last_poll_receipt_sha256 is not None:
            _require_sha256(
                self.last_poll_receipt_sha256,
                "last_poll_receipt_sha256",
            )
        if self.sequence == 0:
            if self.kind is not ScheduleServiceEntryKind.START:
                raise MacroScheduleServiceContractError(
                    "sequence zero schedule service entry must be START"
                )
            if self.previous_entry_sha256 is not None:
                raise MacroScheduleServiceContractError(
                    "START entry cannot reference previous history"
                )
        else:
            if self.kind is not ScheduleServiceEntryKind.TRANSITION:
                raise MacroScheduleServiceContractError(
                    "nonzero schedule service entry must be TRANSITION"
                )
            if self.previous_entry_sha256 is None:
                raise MacroScheduleServiceContractError(
                    "TRANSITION entry requires previous_entry_sha256"
                )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroScheduleServiceContractError(
                "ScheduleServiceStateEntry cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_id": self.service_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "schedule_id": self.schedule_id,
            "schedule_sha256": self.schedule_sha256,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "cursor_utc": self.cursor_utc,
            "status": self.status.value,
            "reason": self.reason,
            "previous_entry_sha256": self.previous_entry_sha256,
            "last_poll_receipt_sha256": self.last_poll_receipt_sha256,
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
    ) -> "ScheduleServiceStateEntry":
        claimed = _require_sha256(
            payload.get("entry_sha256"),
            "entry_sha256",
        )
        try:
            entry = cls(
                service_id=str(payload["service_id"]),
                sequence=int(payload["sequence"]),
                kind=ScheduleServiceEntryKind(str(payload["kind"])),
                schedule_id=str(payload["schedule_id"]),
                schedule_sha256=str(payload["schedule_sha256"]),
                macro_id=str(payload["macro_id"]),
                macro_version=str(payload["macro_version"]),
                plan_sha256=str(payload["plan_sha256"]),
                policy_id=str(payload["policy_id"]),
                policy_sha256=str(payload["policy_sha256"]),
                cursor_utc=str(payload["cursor_utc"]),
                status=ScheduleServiceStatus(str(payload["status"])),
                reason=str(payload["reason"]),
                previous_entry_sha256=(
                    None
                    if payload.get("previous_entry_sha256") is None
                    else str(payload["previous_entry_sha256"])
                ),
                last_poll_receipt_sha256=(
                    None
                    if payload.get("last_poll_receipt_sha256") is None
                    else str(payload["last_poll_receipt_sha256"])
                ),
                operational_authority=bool(
                    payload["operational_authority"]
                ),
                action_authority=bool(payload["action_authority"]),
                execution_authority=bool(
                    payload["execution_authority"]
                ),
                schema_version=str(payload["schema_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MacroScheduleServiceContractError(
                "schedule service state entry is malformed"
            ) from exc
        if entry.entry_sha256 != claimed:
            raise MacroScheduleServiceContractError(
                "schedule service state entry hash mismatch"
            )
        return entry


@dataclass(frozen=True, slots=True)
class ScheduleAdmissionResult:
    occurrence_id: str
    observation_sha256: str
    request_sha256: str
    start_receipt_sha256: str
    start_status: StartStatus
    start_reason: str

    def __post_init__(self) -> None:
        _require_text(self.occurrence_id, "occurrence_id", maximum=128)
        _require_sha256(self.observation_sha256, "observation_sha256")
        _require_sha256(self.request_sha256, "request_sha256")
        _require_sha256(
            self.start_receipt_sha256,
            "start_receipt_sha256",
        )
        _require_text(self.start_reason, "start_reason")


@dataclass(frozen=True, slots=True)
class ScheduleServicePollReceipt:
    """Evidence for one bounded producer + admission polling window."""

    service_id: str
    schedule_id: str
    schedule_sha256: str
    macro_id: str
    macro_version: str
    plan_sha256: str
    policy_id: str
    policy_sha256: str
    after_exclusive_utc: str
    through_inclusive_utc: str
    candidate_count: int
    emitted_count: int
    admissions: tuple[ScheduleAdmissionResult, ...]
    poll_status: SchedulePollStatus
    reason: str
    cursor_advanced: bool
    next_cursor_utc: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_SERVICE_POLL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_SERVICE_POLL_SCHEMA_VERSION:
            raise MacroScheduleServiceContractError(
                "unsupported schedule service poll schema"
            )
        _require_text(self.service_id, "service_id")
        _require_text(self.schedule_id, "schedule_id")
        _require_sha256(self.schedule_sha256, "schedule_sha256")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        _require_text(self.policy_id, "policy_id")
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_timestamp(self.after_exclusive_utc, "after_exclusive_utc")
        _require_timestamp(self.through_inclusive_utc, "through_inclusive_utc")
        _require_timestamp(self.next_cursor_utc, "next_cursor_utc")
        for field, value in (
            ("candidate_count", self.candidate_count),
            ("emitted_count", self.emitted_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MacroScheduleServiceContractError(
                    f"{field} must be a non-negative integer"
                )
        _require_text(self.reason, "reason")
        if not isinstance(self.cursor_advanced, bool):
            raise MacroScheduleServiceContractError(
                "cursor_advanced must be Boolean"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroScheduleServiceContractError(
                "ScheduleServicePollReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_id": self.service_id,
            "schedule_id": self.schedule_id,
            "schedule_sha256": self.schedule_sha256,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "after_exclusive_utc": self.after_exclusive_utc,
            "through_inclusive_utc": self.through_inclusive_utc,
            "candidate_count": self.candidate_count,
            "emitted_count": self.emitted_count,
            "admissions": [
                {
                    "occurrence_id": item.occurrence_id,
                    "observation_sha256": item.observation_sha256,
                    "request_sha256": item.request_sha256,
                    "start_receipt_sha256": item.start_receipt_sha256,
                    "start_status": item.start_status.value,
                    "start_reason": item.start_reason,
                }
                for item in self.admissions
            ],
            "poll_status": self.poll_status.value,
            "reason": self.reason,
            "cursor_advanced": self.cursor_advanced,
            "next_cursor_utc": self.next_cursor_utc,
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
class ScheduleServiceView:
    state: ScheduleServiceStateEntry
    entry_count: int


@dataclass(frozen=True, slots=True)
class ScheduleServicePollOutcome:
    state: ScheduleServiceStateEntry
    poll_receipt: ScheduleServicePollReceipt
    entry_count: int


class ScheduleService:
    """Persistent coordinator around v0.9 producer and v0.8 start gate."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise MacroScheduleServiceContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._producer = WallClockScheduleProducer()
        self._start_gate = MacroRunStartGate(ledger)

    def start(
        self,
        *,
        service_id: str,
        schedule: WallClockSchedule,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
        cursor_utc: datetime,
    ) -> ScheduleServiceView:
        _require_text(service_id, "service_id")
        if self._ledger.schedule_service_state_entries(service_id=service_id):
            raise MacroScheduleServiceContractError(
                "schedule service_id already exists"
            )
        cursor = _utc_iso(cursor_utc)
        entry = ScheduleServiceStateEntry(
            service_id=service_id,
            sequence=0,
            kind=ScheduleServiceEntryKind.START,
            schedule_id=schedule.schedule_id,
            schedule_sha256=schedule.schedule_sha256,
            macro_id=plan.macro_id,
            macro_version=plan.macro_version,
            plan_sha256=plan.plan_sha256,
            policy_id=policy.policy_id,
            policy_sha256=policy.policy_sha256,
            cursor_utc=cursor,
            status=ScheduleServiceStatus.ACTIVE,
            reason="service_started",
            previous_entry_sha256=None,
            last_poll_receipt_sha256=None,
        )
        self._ledger.append_schedule_service_state(entry)
        return ScheduleServiceView(state=entry, entry_count=1)

    def current(
        self,
        *,
        service_id: str,
        schedule: WallClockSchedule,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
    ) -> ScheduleServiceView:
        entries = self._load_and_validate(service_id)
        if not entries:
            raise MacroScheduleServiceContractError(
                "schedule service contains no state"
            )
        head = entries[-1]
        self._validate_binding(
            head=head,
            schedule=schedule,
            plan=plan,
            policy=policy,
        )
        return ScheduleServiceView(
            state=head,
            entry_count=len(entries),
        )

    def poll(
        self,
        *,
        service_id: str,
        schedule: WallClockSchedule,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
        through_inclusive: datetime,
    ) -> ScheduleServicePollOutcome:
        current = self.current(
            service_id=service_id,
            schedule=schedule,
            plan=plan,
            policy=policy,
        )
        head = current.state
        through = _utc_iso(through_inclusive)
        after_dt = _parse_utc(head.cursor_utc, "cursor_utc")
        through_dt = _parse_utc(through, "through_inclusive")
        if through_dt < after_dt:
            raise MacroScheduleServiceContractError(
                "poll target cannot precede persistent cursor"
            )

        produced = self._producer.poll(
            schedule=schedule,
            after_exclusive=after_dt,
            through_inclusive=through_dt,
        )
        admissions = tuple(
            self._admit_trigger(
                service_id=service_id,
                plan=plan,
                policy=policy,
                trigger=trigger,
            )
            for trigger in produced.triggers
        )

        retryable = [
            item
            for item in admissions
            if (
                item.start_status is StartStatus.HELD
                and item.start_reason in _RETRYABLE_HELD_REASONS
            )
        ]
        unsettled = [
            item
            for item in admissions
            if (
                item.start_status is StartStatus.HELD
                and item.start_reason not in _RETRYABLE_HELD_REASONS
                and item.start_reason not in _REPLAY_SETTLED_HELD_REASONS
            )
        ]
        can_advance = not retryable and not unsettled
        poll_status = (
            SchedulePollStatus.COMMITTED
            if can_advance
            else SchedulePollStatus.HELD
        )
        reason = (
            "poll_window_committed"
            if can_advance
            else "poll_window_has_retryable_admission"
        )
        next_cursor = through if can_advance else head.cursor_utc

        poll_receipt = ScheduleServicePollReceipt(
            service_id=service_id,
            schedule_id=schedule.schedule_id,
            schedule_sha256=schedule.schedule_sha256,
            macro_id=plan.macro_id,
            macro_version=plan.macro_version,
            plan_sha256=plan.plan_sha256,
            policy_id=policy.policy_id,
            policy_sha256=policy.policy_sha256,
            after_exclusive_utc=produced.after_exclusive_utc,
            through_inclusive_utc=produced.through_inclusive_utc,
            candidate_count=produced.candidate_count,
            emitted_count=produced.emitted_count,
            admissions=admissions,
            poll_status=poll_status,
            reason=reason,
            cursor_advanced=can_advance,
            next_cursor_utc=next_cursor,
        )
        self._ledger.append_schedule_service_poll_receipt(poll_receipt)

        next_state = ScheduleServiceStateEntry(
            service_id=service_id,
            sequence=head.sequence + 1,
            kind=ScheduleServiceEntryKind.TRANSITION,
            schedule_id=head.schedule_id,
            schedule_sha256=head.schedule_sha256,
            macro_id=head.macro_id,
            macro_version=head.macro_version,
            plan_sha256=head.plan_sha256,
            policy_id=head.policy_id,
            policy_sha256=head.policy_sha256,
            cursor_utc=next_cursor,
            status=(
                ScheduleServiceStatus.ACTIVE
                if can_advance
                else ScheduleServiceStatus.HELD
            ),
            reason=reason,
            previous_entry_sha256=head.entry_sha256,
            last_poll_receipt_sha256=poll_receipt.receipt_sha256,
        )
        self._ledger.append_schedule_service_state(next_state)
        return ScheduleServicePollOutcome(
            state=next_state,
            poll_receipt=poll_receipt,
            entry_count=current.entry_count + 1,
        )

    @staticmethod
    def request_for(
        *,
        service_id: str,
        plan: MacroPlan,
        trigger: ScheduledTrigger,
    ) -> RunStartRequest:
        _require_text(service_id, "service_id")
        identity = _canonical_sha256(
            {
                "service_id": service_id,
                "plan_sha256": plan.plan_sha256,
                "occurrence_id": trigger.occurrence.occurrence_id,
                "observation_sha256": (
                    trigger.observation.observation_sha256
                ),
            }
        )
        return RunStartRequest.build(
            request_id=f"request:schedule:{identity}",
            run_id=f"run:schedule:{identity}",
            plan=plan,
            observation=trigger.observation,
            requested_at=trigger.occurrence.due_at_utc,
        )

    def _admit_trigger(
        self,
        *,
        service_id: str,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
        trigger: ScheduledTrigger,
    ) -> ScheduleAdmissionResult:
        request = self.request_for(
            service_id=service_id,
            plan=plan,
            trigger=trigger,
        )
        admission: RunStartAdmission = self._start_gate.admit(
            observation=trigger.observation,
            request=request,
            policy=policy,
            plan=plan,
        )
        return ScheduleAdmissionResult(
            occurrence_id=trigger.occurrence.occurrence_id,
            observation_sha256=trigger.observation.observation_sha256,
            request_sha256=request.request_sha256,
            start_receipt_sha256=admission.receipt.receipt_sha256,
            start_status=admission.receipt.status,
            start_reason=admission.receipt.reason,
        )

    def _load_and_validate(
        self,
        service_id: str,
    ) -> list[ScheduleServiceStateEntry]:
        _require_text(service_id, "service_id")
        rows = self._ledger.schedule_service_state_entries(
            service_id=service_id
        )
        entries = [
            ScheduleServiceStateEntry.from_dict(row)
            for row in rows
        ]
        if not entries:
            return []

        first = entries[0]
        previous_cursor = _parse_utc(first.cursor_utc, "cursor_utc")
        for expected_sequence, entry in enumerate(entries):
            if entry.service_id != service_id:
                raise MacroScheduleServiceContractError(
                    "schedule service_id changed within state chain"
                )
            if entry.sequence != expected_sequence:
                raise MacroScheduleServiceContractError(
                    "schedule service sequence is not contiguous"
                )
            if (
                entry.schedule_id != first.schedule_id
                or entry.schedule_sha256 != first.schedule_sha256
                or entry.macro_id != first.macro_id
                or entry.macro_version != first.macro_version
                or entry.plan_sha256 != first.plan_sha256
                or entry.policy_id != first.policy_id
                or entry.policy_sha256 != first.policy_sha256
            ):
                raise MacroScheduleServiceContractError(
                    "schedule service binding changed within state chain"
                )
            current_cursor = _parse_utc(entry.cursor_utc, "cursor_utc")
            if current_cursor < previous_cursor:
                raise MacroScheduleServiceContractError(
                    "schedule service cursor moved backward"
                )
            previous_cursor = current_cursor
            if expected_sequence == 0:
                continue
            previous = entries[expected_sequence - 1]
            if entry.previous_entry_sha256 != previous.entry_sha256:
                raise MacroScheduleServiceContractError(
                    "schedule service state hash chain mismatch"
                )
        return entries

    @staticmethod
    def _validate_binding(
        *,
        head: ScheduleServiceStateEntry,
        schedule: WallClockSchedule,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
    ) -> None:
        expected = (
            schedule.schedule_id,
            schedule.schedule_sha256,
            plan.macro_id,
            plan.macro_version,
            plan.plan_sha256,
            policy.policy_id,
            policy.policy_sha256,
        )
        observed = (
            head.schedule_id,
            head.schedule_sha256,
            head.macro_id,
            head.macro_version,
            head.plan_sha256,
            head.policy_id,
            head.policy_sha256,
        )
        if observed != expected:
            raise MacroScheduleServiceContractError(
                "schedule service binding does not match supplied configuration"
            )
