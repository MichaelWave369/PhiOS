"""Single-host schedule worker ownership for Macro Runtime v0.11.

The worker owns polling of one v0.10 ScheduleService through a live OS file
lock plus persisted lease/cycle evidence. It never gains authority over macro
effects and reconstructs persistent state before every cycle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from phios.macro_graph import MacroPlan
from phios.macro_schedule import WallClockSchedule
from phios.macro_schedule_service import (
    SchedulePollStatus,
    ScheduleService,
    ScheduleServicePollOutcome,
)
from phios.macro_start import RunStartAdmissionPolicy
from phios.spine.ledger import RealityLedger

SCHEDULE_WORKER_LEASE_SCHEMA_VERSION = "phios.schedule_worker_lease.v0.11"
SCHEDULE_WORKER_EVENT_SCHEMA_VERSION = "phios.schedule_worker_event.v0.11"
SCHEDULE_WORKER_TICK_SCHEMA_VERSION = "phios.schedule_worker_tick.v0.11"
MAX_LEASE_SECONDS = 86400
MAX_TICK_SECONDS = 86400
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MacroScheduleWorkerContractError(ValueError):
    """Raised when schedule worker ownership cannot be proven safely."""


class WorkerAcquireStatus(StrEnum):
    ACQUIRED = "ACQUIRED"
    HELD = "HELD"


class WorkerLeaseEventKind(StrEnum):
    ACQUIRED = "ACQUIRED"
    ORPHAN_TAKEOVER = "ORPHAN_TAKEOVER"
    ACQUIRE_HELD = "ACQUIRE_HELD"
    RENEWED = "RENEWED"
    RELEASED = "RELEASED"


class WorkerTickStatus(StrEnum):
    COMMITTED = "COMMITTED"
    HELD = "HELD"
    NOOP = "NOOP"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroScheduleWorkerContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise MacroScheduleWorkerContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise MacroScheduleWorkerContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise MacroScheduleWorkerContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MacroScheduleWorkerContractError(
            f"{field} must be an integer"
        )
    if value < minimum:
        raise MacroScheduleWorkerContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise MacroScheduleWorkerContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MacroScheduleWorkerContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise MacroScheduleWorkerContractError(
            f"{field} must include a timezone"
        )
    return text


def _require_aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise MacroScheduleWorkerContractError(
            f"{field} must be a datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise MacroScheduleWorkerContractError(
            f"{field} must be timezone-aware"
        )
    return value.astimezone(UTC)


def _parse_utc(value: str, field: str) -> datetime:
    parsed = datetime.fromisoformat(
        _require_timestamp(value, field).replace("Z", "+00:00")
    )
    return parsed.astimezone(UTC)


def _utc_iso(value: datetime) -> str:
    return _require_aware(value, "timestamp").isoformat().replace(
        "+00:00",
        "Z",
    )


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
        raise MacroScheduleWorkerContractError(
            "schedule worker payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ScheduleWorkerLease:
    service_id: str
    service_key_sha256: str
    worker_id: str
    lease_id: str
    generation: int
    renewal_index: int
    acquired_at: str
    renewed_at: str
    valid_until: str
    lease_seconds: int
    max_tick_seconds: int
    previous_lease_sha256: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_WORKER_LEASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_WORKER_LEASE_SCHEMA_VERSION:
            raise MacroScheduleWorkerContractError(
                "unsupported schedule worker lease schema"
            )
        _require_text(self.service_id, "service_id")
        _require_sha256(self.service_key_sha256, "service_key_sha256")
        _require_text(self.worker_id, "worker_id")
        _require_text(self.lease_id, "lease_id", maximum=128)
        _require_int(self.generation, "generation", minimum=1)
        _require_int(self.renewal_index, "renewal_index")
        acquired = _parse_utc(self.acquired_at, "acquired_at")
        renewed = _parse_utc(self.renewed_at, "renewed_at")
        valid_until = _parse_utc(self.valid_until, "valid_until")
        if renewed < acquired or valid_until <= renewed:
            raise MacroScheduleWorkerContractError(
                "schedule worker lease timestamps are not monotonic"
            )
        _require_int(
            self.lease_seconds,
            "lease_seconds",
            minimum=1,
            maximum=MAX_LEASE_SECONDS,
        )
        _require_int(
            self.max_tick_seconds,
            "max_tick_seconds",
            minimum=1,
            maximum=MAX_TICK_SECONDS,
        )
        if self.previous_lease_sha256 is not None:
            _require_sha256(
                self.previous_lease_sha256,
                "previous_lease_sha256",
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise MacroScheduleWorkerContractError(
                "ScheduleWorkerLease cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_id": self.service_id,
            "service_key_sha256": self.service_key_sha256,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "generation": self.generation,
            "renewal_index": self.renewal_index,
            "acquired_at": self.acquired_at,
            "renewed_at": self.renewed_at,
            "valid_until": self.valid_until,
            "lease_seconds": self.lease_seconds,
            "max_tick_seconds": self.max_tick_seconds,
            "previous_lease_sha256": self.previous_lease_sha256,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def lease_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["lease_sha256"] = self.lease_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ScheduleWorkerLeaseEvent:
    event_kind: WorkerLeaseEventKind
    reason: str
    service_id: str
    service_key_sha256: str
    worker_id: str
    at: str
    lease_sha256: str | None
    previous_lease_sha256: str | None
    generation: int | None
    valid_until: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_WORKER_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_WORKER_EVENT_SCHEMA_VERSION:
            raise MacroScheduleWorkerContractError(
                "unsupported schedule worker event schema"
            )
        _require_text(self.reason, "reason")
        _require_text(self.service_id, "service_id")
        _require_sha256(self.service_key_sha256, "service_key_sha256")
        _require_text(self.worker_id, "worker_id")
        _require_timestamp(self.at, "at")
        if self.lease_sha256 is not None:
            _require_sha256(self.lease_sha256, "lease_sha256")
        if self.previous_lease_sha256 is not None:
            _require_sha256(
                self.previous_lease_sha256,
                "previous_lease_sha256",
            )
        if self.generation is not None:
            _require_int(self.generation, "generation", minimum=1)
        if self.valid_until is not None:
            _require_timestamp(self.valid_until, "valid_until")
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise MacroScheduleWorkerContractError(
                "ScheduleWorkerLeaseEvent cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_kind": self.event_kind.value,
            "reason": self.reason,
            "service_id": self.service_id,
            "service_key_sha256": self.service_key_sha256,
            "worker_id": self.worker_id,
            "at": self.at,
            "lease_sha256": self.lease_sha256,
            "previous_lease_sha256": self.previous_lease_sha256,
            "generation": self.generation,
            "valid_until": self.valid_until,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def event_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["event_sha256"] = self.event_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ScheduleWorkerTickReceipt:
    service_id: str
    worker_id: str
    lease_sha256: str
    cycle_index: int
    cycle_anchor_sha256: str
    tick_at: str
    cursor_before_utc: str
    through_inclusive_utc: str
    cursor_after_utc: str
    service_state_before_sha256: str
    service_state_after_sha256: str
    schedule_poll_receipt_sha256: str | None
    tick_status: WorkerTickStatus
    reason: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_WORKER_TICK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_WORKER_TICK_SCHEMA_VERSION:
            raise MacroScheduleWorkerContractError(
                "unsupported schedule worker tick schema"
            )
        _require_text(self.service_id, "service_id")
        _require_text(self.worker_id, "worker_id")
        _require_sha256(self.lease_sha256, "lease_sha256")
        _require_int(self.cycle_index, "cycle_index")
        _require_sha256(self.cycle_anchor_sha256, "cycle_anchor_sha256")
        _require_timestamp(self.tick_at, "tick_at")
        before = _parse_utc(self.cursor_before_utc, "cursor_before_utc")
        through = _parse_utc(
            self.through_inclusive_utc,
            "through_inclusive_utc",
        )
        after = _parse_utc(self.cursor_after_utc, "cursor_after_utc")
        if through < before or after < before or after > through:
            raise MacroScheduleWorkerContractError(
                "worker tick cursor/window ordering is invalid"
            )
        _require_sha256(
            self.service_state_before_sha256,
            "service_state_before_sha256",
        )
        _require_sha256(
            self.service_state_after_sha256,
            "service_state_after_sha256",
        )
        if self.schedule_poll_receipt_sha256 is not None:
            _require_sha256(
                self.schedule_poll_receipt_sha256,
                "schedule_poll_receipt_sha256",
            )
        _require_text(self.reason, "reason")
        if self.tick_status is WorkerTickStatus.NOOP:
            if self.schedule_poll_receipt_sha256 is not None:
                raise MacroScheduleWorkerContractError(
                    "NOOP tick cannot reference schedule poll receipt"
                )
            if through != before or after != before:
                raise MacroScheduleWorkerContractError(
                    "NOOP tick must leave cursor unchanged"
                )
        elif self.schedule_poll_receipt_sha256 is None:
            raise MacroScheduleWorkerContractError(
                "polled worker tick requires schedule poll receipt"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise MacroScheduleWorkerContractError(
                "ScheduleWorkerTickReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_id": self.service_id,
            "worker_id": self.worker_id,
            "lease_sha256": self.lease_sha256,
            "cycle_index": self.cycle_index,
            "cycle_anchor_sha256": self.cycle_anchor_sha256,
            "tick_at": self.tick_at,
            "cursor_before_utc": self.cursor_before_utc,
            "through_inclusive_utc": self.through_inclusive_utc,
            "cursor_after_utc": self.cursor_after_utc,
            "service_state_before_sha256": (
                self.service_state_before_sha256
            ),
            "service_state_after_sha256": self.service_state_after_sha256,
            "schedule_poll_receipt_sha256": (
                self.schedule_poll_receipt_sha256
            ),
            "tick_status": self.tick_status.value,
            "reason": self.reason,
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
class ScheduleWorkerTickOutcome:
    receipt: ScheduleWorkerTickReceipt
    service_outcome: ScheduleServicePollOutcome | None


@dataclass(frozen=True, slots=True)
class ScheduleWorkerAcquireResult:
    status: WorkerAcquireStatus
    reason: str
    event: ScheduleWorkerLeaseEvent
    worker: "ScheduleWorker | None"


class _WorkerFileLock:
    """Cross-platform nonblocking lock held for the ScheduleWorker lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None

    def acquire(self) -> bool:
        if self.handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
        except (BlockingIOError, OSError):
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self) -> None:
        handle = self.handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self.handle = None

    @property
    def held(self) -> bool:
        return self.handle is not None


class ScheduleWorker:
    """One acquired schedule worker; every tick re-anchors to persisted state."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        lock: _WorkerFileLock,
        lease: ScheduleWorkerLease,
        schedule: WallClockSchedule,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
    ) -> None:
        self._ledger = ledger
        self._lock = lock
        self.lease = lease
        self.schedule = schedule
        self.plan = plan
        self.policy = policy

    def renew(self, *, renewed_at: datetime) -> ScheduleWorkerLease:
        now = _require_aware(renewed_at, "renewed_at")
        self._require_live_lock()
        current = self.lease
        if now > _parse_utc(current.valid_until, "valid_until"):
            raise MacroScheduleWorkerContractError(
                "expired schedule worker lease cannot be renewed"
            )
        renewed = ScheduleWorkerLease(
            service_id=current.service_id,
            service_key_sha256=current.service_key_sha256,
            worker_id=current.worker_id,
            lease_id=current.lease_id,
            generation=current.generation,
            renewal_index=current.renewal_index + 1,
            acquired_at=current.acquired_at,
            renewed_at=_utc_iso(now),
            valid_until=_utc_iso(
                now + timedelta(seconds=current.lease_seconds)
            ),
            lease_seconds=current.lease_seconds,
            max_tick_seconds=current.max_tick_seconds,
            previous_lease_sha256=current.lease_sha256,
        )
        self._ledger.append_schedule_worker_lease(renewed)
        self._ledger.append_schedule_worker_event(
            _event_for(
                kind=WorkerLeaseEventKind.RENEWED,
                reason="worker_lease_renewed",
                lease=renewed,
                at=now,
                previous=current.lease_sha256,
            )
        )
        self.lease = renewed
        return renewed

    def tick(self, *, tick_at: datetime) -> ScheduleWorkerTickOutcome:
        now = _require_aware(tick_at, "tick_at")
        self._require_live_lock()
        lease = self.lease
        if now > _parse_utc(lease.valid_until, "valid_until"):
            raise MacroScheduleWorkerContractError(
                "schedule worker lease expired before tick"
            )

        service = ScheduleService(self._ledger)
        before = service.current(
            service_id=lease.service_id,
            schedule=self.schedule,
            plan=self.plan,
            policy=self.policy,
        )
        cursor = _parse_utc(before.state.cursor_utc, "cursor_utc")
        cycle_index = self._ledger.next_schedule_worker_cycle_index(
            service_id=lease.service_id
        )
        cycle_anchor = _canonical_sha256(
            {
                "service_id": lease.service_id,
                "worker_id": lease.worker_id,
                "lease_sha256": lease.lease_sha256,
                "cycle_index": cycle_index,
                "service_state_sha256": before.state.entry_sha256,
                "cursor_utc": before.state.cursor_utc,
            }
        )

        if now <= cursor:
            receipt = ScheduleWorkerTickReceipt(
                service_id=lease.service_id,
                worker_id=lease.worker_id,
                lease_sha256=lease.lease_sha256,
                cycle_index=cycle_index,
                cycle_anchor_sha256=cycle_anchor,
                tick_at=_utc_iso(now),
                cursor_before_utc=before.state.cursor_utc,
                through_inclusive_utc=before.state.cursor_utc,
                cursor_after_utc=before.state.cursor_utc,
                service_state_before_sha256=before.state.entry_sha256,
                service_state_after_sha256=before.state.entry_sha256,
                schedule_poll_receipt_sha256=None,
                tick_status=WorkerTickStatus.NOOP,
                reason="tick_not_after_persistent_cursor",
            )
            self._ledger.append_schedule_worker_tick_receipt(receipt)
            return ScheduleWorkerTickOutcome(
                receipt=receipt,
                service_outcome=None,
            )

        through = min(
            now,
            cursor + timedelta(seconds=lease.max_tick_seconds),
        )
        outcome = service.poll(
            service_id=lease.service_id,
            schedule=self.schedule,
            plan=self.plan,
            policy=self.policy,
            through_inclusive=through,
        )
        tick_status = (
            WorkerTickStatus.COMMITTED
            if outcome.poll_receipt.poll_status
            is SchedulePollStatus.COMMITTED
            else WorkerTickStatus.HELD
        )
        receipt = ScheduleWorkerTickReceipt(
            service_id=lease.service_id,
            worker_id=lease.worker_id,
            lease_sha256=lease.lease_sha256,
            cycle_index=cycle_index,
            cycle_anchor_sha256=cycle_anchor,
            tick_at=_utc_iso(now),
            cursor_before_utc=before.state.cursor_utc,
            through_inclusive_utc=_utc_iso(through),
            cursor_after_utc=outcome.state.cursor_utc,
            service_state_before_sha256=before.state.entry_sha256,
            service_state_after_sha256=outcome.state.entry_sha256,
            schedule_poll_receipt_sha256=(
                outcome.poll_receipt.receipt_sha256
            ),
            tick_status=tick_status,
            reason=(
                "schedule_poll_committed"
                if tick_status is WorkerTickStatus.COMMITTED
                else "schedule_poll_held"
            ),
        )
        self._ledger.append_schedule_worker_tick_receipt(receipt)
        return ScheduleWorkerTickOutcome(
            receipt=receipt,
            service_outcome=outcome,
        )

    def release(self, *, released_at: datetime) -> None:
        now = _require_aware(released_at, "released_at")
        if not self._lock.held:
            return
        lease = self.lease
        self._ledger.append_schedule_worker_event(
            _event_for(
                kind=WorkerLeaseEventKind.RELEASED,
                reason="worker_lock_released",
                lease=lease,
                at=now,
                previous=lease.lease_sha256,
            )
        )
        self._lock.release()

    def _require_live_lock(self) -> None:
        if not self._lock.held:
            raise MacroScheduleWorkerContractError(
                "schedule worker does not hold live OS ownership lock"
            )


class ScheduleWorkerManager:
    """Acquire one single-host worker ownership lease for a service."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise MacroScheduleWorkerContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger

    def acquire(
        self,
        *,
        service_id: str,
        worker_id: str,
        schedule: WallClockSchedule,
        plan: MacroPlan,
        policy: RunStartAdmissionPolicy,
        acquired_at: datetime,
        lease_seconds: int = 60,
        max_tick_seconds: int = 60,
    ) -> ScheduleWorkerAcquireResult:
        _require_text(service_id, "service_id")
        _require_text(worker_id, "worker_id")
        now = _require_aware(acquired_at, "acquired_at")
        _require_int(
            lease_seconds,
            "lease_seconds",
            minimum=1,
            maximum=MAX_LEASE_SECONDS,
        )
        _require_int(
            max_tick_seconds,
            "max_tick_seconds",
            minimum=1,
            maximum=MAX_TICK_SECONDS,
        )

        ScheduleService(self._ledger).current(
            service_id=service_id,
            schedule=schedule,
            plan=plan,
            policy=policy,
        )

        service_key = _canonical_sha256({"service_id": service_id})
        lock = _WorkerFileLock(
            self._ledger.path.parent
            / "schedule-worker-locks"
            / f"{service_key}.lock"
        )
        if not lock.acquire():
            event = ScheduleWorkerLeaseEvent(
                event_kind=WorkerLeaseEventKind.ACQUIRE_HELD,
                reason="service_owned_by_live_worker",
                service_id=service_id,
                service_key_sha256=service_key,
                worker_id=worker_id,
                at=_utc_iso(now),
                lease_sha256=None,
                previous_lease_sha256=None,
                generation=None,
                valid_until=None,
            )
            self._ledger.append_schedule_worker_event(event)
            return ScheduleWorkerAcquireResult(
                status=WorkerAcquireStatus.HELD,
                reason=event.reason,
                event=event,
                worker=None,
            )

        previous = self._ledger.latest_schedule_worker_lease(
            service_id=service_id
        )
        previous_sha = (
            _require_sha256(
                previous.get("lease_sha256"),
                "previous lease_sha256",
            )
            if previous is not None
            else None
        )
        generation = (
            _require_int(
                previous.get("generation"),
                "previous generation",
                minimum=1,
            )
            + 1
            if previous is not None
            else 1
        )
        lease_identity = _canonical_sha256(
            {
                "service_id": service_id,
                "worker_id": worker_id,
                "generation": generation,
                "acquired_at": _utc_iso(now),
            }
        )
        lease = ScheduleWorkerLease(
            service_id=service_id,
            service_key_sha256=service_key,
            worker_id=worker_id,
            lease_id=f"schedule-worker:{lease_identity}",
            generation=generation,
            renewal_index=0,
            acquired_at=_utc_iso(now),
            renewed_at=_utc_iso(now),
            valid_until=_utc_iso(
                now + timedelta(seconds=lease_seconds)
            ),
            lease_seconds=lease_seconds,
            max_tick_seconds=max_tick_seconds,
            previous_lease_sha256=previous_sha,
        )
        self._ledger.append_schedule_worker_lease(lease)

        previous_events = self._ledger.schedule_worker_events(
            service_id=service_id
        )
        prior_open = bool(
            previous_events
            and previous_events[-1].get("event_kind") != "RELEASED"
        )
        kind = (
            WorkerLeaseEventKind.ORPHAN_TAKEOVER
            if prior_open
            else WorkerLeaseEventKind.ACQUIRED
        )
        reason = (
            "os_lock_acquired_after_unreleased_prior_worker"
            if prior_open
            else "worker_ownership_acquired"
        )
        event = _event_for(
            kind=kind,
            reason=reason,
            lease=lease,
            at=now,
            previous=previous_sha,
        )
        self._ledger.append_schedule_worker_event(event)
        worker = ScheduleWorker(
            ledger=self._ledger,
            lock=lock,
            lease=lease,
            schedule=schedule,
            plan=plan,
            policy=policy,
        )
        return ScheduleWorkerAcquireResult(
            status=WorkerAcquireStatus.ACQUIRED,
            reason=reason,
            event=event,
            worker=worker,
        )


def _event_for(
    *,
    kind: WorkerLeaseEventKind,
    reason: str,
    lease: ScheduleWorkerLease,
    at: datetime,
    previous: str | None,
) -> ScheduleWorkerLeaseEvent:
    return ScheduleWorkerLeaseEvent(
        event_kind=kind,
        reason=reason,
        service_id=lease.service_id,
        service_key_sha256=lease.service_key_sha256,
        worker_id=lease.worker_id,
        at=_utc_iso(at),
        lease_sha256=lease.lease_sha256,
        previous_lease_sha256=previous,
        generation=lease.generation,
        valid_until=lease.valid_until,
    )
