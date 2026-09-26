"""Deterministic wall-clock schedule producer for Macro Runtime v0.9.

This module evaluates schedule definitions and emits stable TriggerObservation
objects. It does not run a background worker, persist a cursor, admit a run, or
grant authority. Schedule observations still pass through the v0.8 start gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from phios.macro_start import TriggerObservation

SCHEDULE_DEFINITION_SCHEMA_VERSION = "phios.wall_clock_schedule.v0.9"
SCHEDULE_OCCURRENCE_SCHEMA_VERSION = "phios.schedule_occurrence.v0.9"
MAX_POLL_WINDOW_DAYS = 366
MAX_OCCURRENCES_PER_POLL = 1000
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MacroScheduleContractError(ValueError):
    """Raised when schedule configuration or evaluation is unsafe."""


class ScheduleCadence(StrEnum):
    ONCE = "ONCE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"


class MisfirePolicy(StrEnum):
    CATCH_UP = "CATCH_UP"
    LATEST_ONLY = "LATEST_ONLY"


class AmbiguousTimePolicy(StrEnum):
    EARLIER = "EARLIER"
    LATER = "LATER"


class NonexistentTimePolicy(StrEnum):
    SKIP = "SKIP"


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


_WEEKDAY_ISO = {
    Weekday.MON: 1,
    Weekday.TUE: 2,
    Weekday.WED: 3,
    Weekday.THU: 4,
    Weekday.FRI: 5,
    Weekday.SAT: 6,
    Weekday.SUN: 7,
}


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroScheduleContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise MacroScheduleContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise MacroScheduleContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if len(text) != 64:
        raise MacroScheduleContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    try:
        int(text, 16)
    except ValueError as exc:
        raise MacroScheduleContractError(
            f"{field} must be a lowercase SHA-256 digest"
        ) from exc
    if text != text.lower():
        raise MacroScheduleContractError(
            f"{field} must be a lowercase SHA-256 digest"
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
        raise MacroScheduleContractError(
            "schedule payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_date(value: str, field: str) -> date:
    _require_text(value, field, maximum=10)
    if not _DATE_RE.fullmatch(value):
        raise MacroScheduleContractError(
            f"{field} must be YYYY-MM-DD"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MacroScheduleContractError(
            f"{field} is not a valid calendar date"
        ) from exc


def _parse_time(value: str) -> time:
    _require_text(value, "local_time", maximum=8)
    if not _TIME_RE.fullmatch(value):
        raise MacroScheduleContractError(
            "local_time must be HH:MM:SS"
        )
    return time.fromisoformat(value)


def _zone(value: str) -> ZoneInfo:
    _require_text(value, "timezone", maximum=128)
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise MacroScheduleContractError(
            f"unknown IANA timezone: {value}"
        ) from exc


def _utc_iso(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise MacroScheduleContractError(
            f"{field} must be a datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise MacroScheduleContractError(
            f"{field} must be timezone-aware"
        )
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class WallClockSchedule:
    """Zero-authority local wall-clock schedule definition."""

    schedule_id: str
    source_id: str
    cadence: ScheduleCadence
    timezone: str
    local_time: str
    start_date: str
    end_date: str | None = None
    weekdays: tuple[Weekday, ...] = ()
    misfire_policy: MisfirePolicy = MisfirePolicy.CATCH_UP
    ambiguous_time_policy: AmbiguousTimePolicy = AmbiguousTimePolicy.EARLIER
    nonexistent_time_policy: NonexistentTimePolicy = NonexistentTimePolicy.SKIP
    max_occurrences_per_poll: int = 100
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_DEFINITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_DEFINITION_SCHEMA_VERSION:
            raise MacroScheduleContractError(
                "unsupported schedule definition schema"
            )
        _require_text(self.schedule_id, "schedule_id")
        _require_text(self.source_id, "source_id")
        _zone(self.timezone)
        _parse_time(self.local_time)
        start = _parse_date(self.start_date, "start_date")
        if self.end_date is not None:
            end = _parse_date(self.end_date, "end_date")
            if end < start:
                raise MacroScheduleContractError(
                    "end_date cannot precede start_date"
                )

        if isinstance(self.max_occurrences_per_poll, bool) or not isinstance(
            self.max_occurrences_per_poll,
            int,
        ):
            raise MacroScheduleContractError(
                "max_occurrences_per_poll must be an integer"
            )
        if (
            self.max_occurrences_per_poll < 1
            or self.max_occurrences_per_poll > MAX_OCCURRENCES_PER_POLL
        ):
            raise MacroScheduleContractError(
                "max_occurrences_per_poll must be between "
                f"1 and {MAX_OCCURRENCES_PER_POLL}"
            )

        if self.cadence is ScheduleCadence.WEEKLY:
            if not self.weekdays:
                raise MacroScheduleContractError(
                    "WEEKLY schedule requires weekdays"
                )
            ordered = tuple(
                sorted(
                    set(self.weekdays),
                    key=lambda item: _WEEKDAY_ISO[item],
                )
            )
            if ordered != self.weekdays:
                raise MacroScheduleContractError(
                    "weekdays must be unique and Monday-to-Sunday ordered"
                )
        elif self.weekdays:
            raise MacroScheduleContractError(
                "weekdays are allowed only for WEEKLY schedules"
            )

        if self.cadence is ScheduleCadence.ONCE and self.end_date is not None:
            if self.end_date != self.start_date:
                raise MacroScheduleContractError(
                    "ONCE schedule end_date must equal start_date or be omitted"
                )

        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroScheduleContractError(
                "WallClockSchedule cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "schedule_id": self.schedule_id,
            "source_id": self.source_id,
            "cadence": self.cadence.value,
            "timezone": self.timezone,
            "local_time": self.local_time,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "weekdays": [item.value for item in self.weekdays],
            "misfire_policy": self.misfire_policy.value,
            "ambiguous_time_policy": self.ambiguous_time_policy.value,
            "nonexistent_time_policy": self.nonexistent_time_policy.value,
            "max_occurrences_per_poll": self.max_occurrences_per_poll,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def schedule_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["schedule_sha256"] = self.schedule_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ScheduleOccurrence:
    """One deterministic resolved wall-clock occurrence."""

    schedule_id: str
    schedule_sha256: str
    local_due_at: str
    due_at_utc: str
    occurrence_id: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SCHEDULE_OCCURRENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_OCCURRENCE_SCHEMA_VERSION:
            raise MacroScheduleContractError(
                "unsupported schedule occurrence schema"
            )
        _require_text(self.schedule_id, "schedule_id")
        _require_sha256(self.schedule_sha256, "schedule_sha256")
        _require_text(self.local_due_at, "local_due_at", maximum=64)
        _require_text(self.due_at_utc, "due_at_utc", maximum=64)
        _require_text(self.occurrence_id, "occurrence_id", maximum=128)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroScheduleContractError(
                "ScheduleOccurrence cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "schedule_id": self.schedule_id,
            "schedule_sha256": self.schedule_sha256,
            "local_due_at": self.local_due_at,
            "due_at_utc": self.due_at_utc,
            "occurrence_id": self.occurrence_id,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def occurrence_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["occurrence_sha256"] = self.occurrence_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ScheduledTrigger:
    occurrence: ScheduleOccurrence
    observation: TriggerObservation


@dataclass(frozen=True, slots=True)
class SchedulePollResult:
    schedule_sha256: str
    after_exclusive_utc: str
    through_inclusive_utc: str
    candidate_count: int
    emitted_count: int
    triggers: tuple[ScheduledTrigger, ...]


class WallClockScheduleProducer:
    """Pure evaluator that emits deterministic schedule TriggerObservations."""

    def poll(
        self,
        *,
        schedule: WallClockSchedule,
        after_exclusive: datetime,
        through_inclusive: datetime,
    ) -> SchedulePollResult:
        if not isinstance(schedule, WallClockSchedule):
            raise MacroScheduleContractError(
                "schedule must be a WallClockSchedule"
            )
        after = _require_aware(after_exclusive, "after_exclusive")
        through = _require_aware(through_inclusive, "through_inclusive")
        if through < after:
            raise MacroScheduleContractError(
                "through_inclusive cannot precede after_exclusive"
            )
        if through - after > timedelta(days=MAX_POLL_WINDOW_DAYS):
            raise MacroScheduleContractError(
                f"poll window cannot exceed {MAX_POLL_WINDOW_DAYS} days"
            )

        occurrences = self._due_occurrences(
            schedule=schedule,
            after=after,
            through=through,
        )
        candidate_count = len(occurrences)

        if schedule.misfire_policy is MisfirePolicy.LATEST_ONLY:
            selected = occurrences[-1:] if occurrences else []
        else:
            selected = occurrences

        if len(selected) > schedule.max_occurrences_per_poll:
            raise MacroScheduleContractError(
                "due occurrences exceed max_occurrences_per_poll"
            )

        triggers = tuple(
            self._trigger(schedule=schedule, occurrence=item)
            for item in selected
        )
        return SchedulePollResult(
            schedule_sha256=schedule.schedule_sha256,
            after_exclusive_utc=_utc_iso(after),
            through_inclusive_utc=_utc_iso(through),
            candidate_count=candidate_count,
            emitted_count=len(triggers),
            triggers=triggers,
        )

    def _due_occurrences(
        self,
        *,
        schedule: WallClockSchedule,
        after: datetime,
        through: datetime,
    ) -> list[ScheduleOccurrence]:
        zone = _zone(schedule.timezone)
        wall_time = _parse_time(schedule.local_time)
        schedule_start = _parse_date(schedule.start_date, "start_date")
        schedule_end = (
            _parse_date(schedule.end_date, "end_date")
            if schedule.end_date is not None
            else None
        )

        first_local = after.astimezone(zone).date() - timedelta(days=1)
        last_local = through.astimezone(zone).date() + timedelta(days=1)
        current = max(first_local, schedule_start)
        if schedule_end is not None:
            last_local = min(last_local, schedule_end)

        occurrences: list[ScheduleOccurrence] = []
        while current <= last_local:
            if self._date_matches(schedule, current):
                naive = datetime.combine(current, wall_time)
                resolved = self._resolve_local(
                    naive=naive,
                    zone=zone,
                    policy=schedule.ambiguous_time_policy,
                )
                if resolved is not None:
                    due_utc = resolved.astimezone(UTC)
                    if after < due_utc <= through:
                        occurrences.append(
                            self._occurrence(
                                schedule=schedule,
                                local_due=resolved,
                                due_utc=due_utc,
                            )
                        )
            current += timedelta(days=1)

        occurrences.sort(
            key=lambda item: (
                item.due_at_utc,
                item.occurrence_id,
            )
        )
        return occurrences

    @staticmethod
    def _date_matches(
        schedule: WallClockSchedule,
        candidate: date,
    ) -> bool:
        if candidate < _parse_date(schedule.start_date, "start_date"):
            return False
        if schedule.end_date is not None and candidate > _parse_date(
            schedule.end_date,
            "end_date",
        ):
            return False
        if schedule.cadence is ScheduleCadence.ONCE:
            return candidate == _parse_date(
                schedule.start_date,
                "start_date",
            )
        if schedule.cadence is ScheduleCadence.DAILY:
            return True
        return candidate.isoweekday() in {
            _WEEKDAY_ISO[item] for item in schedule.weekdays
        }

    @staticmethod
    def _resolve_local(
        *,
        naive: datetime,
        zone: ZoneInfo,
        policy: AmbiguousTimePolicy,
    ) -> datetime | None:
        candidates: dict[str, datetime] = {}
        for fold in (0, 1):
            aware = naive.replace(tzinfo=zone, fold=fold)
            utc_value = aware.astimezone(UTC)
            roundtrip = utc_value.astimezone(zone)
            if roundtrip.replace(tzinfo=None) != naive:
                continue
            candidates[_utc_iso(utc_value)] = aware

        if not candidates:
            return None
        ordered = [
            candidates[key]
            for key in sorted(candidates)
        ]
        if len(ordered) == 1:
            return ordered[0]
        if policy is AmbiguousTimePolicy.EARLIER:
            return ordered[0]
        return ordered[-1]

    @staticmethod
    def _occurrence(
        *,
        schedule: WallClockSchedule,
        local_due: datetime,
        due_utc: datetime,
    ) -> ScheduleOccurrence:
        local_due_at = local_due.isoformat()
        due_at_utc = _utc_iso(due_utc)
        occurrence_digest = _canonical_sha256(
            {
                "schedule_sha256": schedule.schedule_sha256,
                "local_due_at": local_due_at,
                "due_at_utc": due_at_utc,
            }
        )
        return ScheduleOccurrence(
            schedule_id=schedule.schedule_id,
            schedule_sha256=schedule.schedule_sha256,
            local_due_at=local_due_at,
            due_at_utc=due_at_utc,
            occurrence_id=f"schedule:{occurrence_digest}",
        )

    @staticmethod
    def _trigger(
        *,
        schedule: WallClockSchedule,
        occurrence: ScheduleOccurrence,
    ) -> ScheduledTrigger:
        observation = TriggerObservation(
            observation_id=(
                f"observation:{occurrence.occurrence_id}"
            ),
            trigger_type="schedule",
            source_id=schedule.source_id,
            source_event_id=occurrence.occurrence_id,
            observed_at=occurrence.due_at_utc,
            payload_sha256=occurrence.occurrence_sha256,
            evidence_ref_sha256s=(schedule.schedule_sha256,),
        )
        return ScheduledTrigger(
            occurrence=occurrence,
            observation=observation,
        )
