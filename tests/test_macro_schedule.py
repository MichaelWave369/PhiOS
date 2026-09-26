from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_runner import RunnerStatus
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.macro_schedule import (
    AmbiguousTimePolicy,
    MacroScheduleContractError,
    MisfirePolicy,
    ScheduleCadence,
    WallClockSchedule,
    WallClockScheduleProducer,
    Weekday,
)
from phios.macro_start import (
    MacroRunStartGate,
    RunStartAdmissionPolicy,
    RunStartRequest,
    StartStatus,
)
from phios.spine.ledger import RealityLedger


def _operation() -> Operation:
    return Operation(
        operation_id="macro.schedule.write",
        operation_version="0.9.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "scheduled", "text": "due"},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _plan():
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:schedule-test",
            macro_version="0.9.0",
            steps=(DoStep(_operation()),),
        )
    )


def _daily(
    *,
    local_time: str = "16:00:00",
    start_date: str = "2026-09-26",
    end_date: str | None = None,
    misfire_policy: MisfirePolicy = MisfirePolicy.CATCH_UP,
    ambiguous_time_policy: AmbiguousTimePolicy = AmbiguousTimePolicy.EARLIER,
    max_occurrences_per_poll: int = 100,
) -> WallClockSchedule:
    return WallClockSchedule(
        schedule_id="schedule:daily-test",
        source_id="source:wall-clock",
        cadence=ScheduleCadence.DAILY,
        timezone="America/Los_Angeles",
        local_time=local_time,
        start_date=start_date,
        end_date=end_date,
        misfire_policy=misfire_policy,
        ambiguous_time_policy=ambiguous_time_policy,
        max_occurrences_per_poll=max_occurrences_per_poll,
    )


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def test_schedule_001_daily_due_occurrence_is_deterministic() -> None:
    schedule = _daily()
    producer = WallClockScheduleProducer()

    first = producer.poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )
    second = producer.poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 26, 22, 58, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 2, tzinfo=UTC),
    )

    assert first.candidate_count == 1
    assert first.emitted_count == 1
    assert second.emitted_count == 1

    one = first.triggers[0]
    two = second.triggers[0]
    assert one.occurrence.due_at_utc == "2026-09-26T23:00:00Z"
    assert one.occurrence.local_due_at.startswith(
        "2026-09-26T16:00:00-07:00"
    )
    assert one.occurrence.occurrence_id == two.occurrence.occurrence_id
    assert (
        one.observation.observation_sha256
        == two.observation.observation_sha256
    )
    assert one.observation.source_event_id == one.occurrence.occurrence_id


def test_schedule_002_weekly_emits_only_declared_weekdays() -> None:
    schedule = WallClockSchedule(
        schedule_id="schedule:weekly-test",
        source_id="source:wall-clock",
        cadence=ScheduleCadence.WEEKLY,
        timezone="America/Los_Angeles",
        local_time="09:00:00",
        start_date="2026-09-01",
        weekdays=(Weekday.MON, Weekday.WED, Weekday.FRI),
    )

    result = WallClockScheduleProducer().poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 21, 0, 0, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 28, 0, 0, tzinfo=UTC),
    )

    local_dates = [
        item.occurrence.local_due_at[:10]
        for item in result.triggers
    ]
    assert local_dates == [
        "2026-09-21",
        "2026-09-23",
        "2026-09-25",
    ]


def test_schedule_003_latest_only_collapses_missed_occurrences() -> None:
    schedule = _daily(
        start_date="2026-09-20",
        misfire_policy=MisfirePolicy.LATEST_ONLY,
    )

    result = WallClockScheduleProducer().poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 30, tzinfo=UTC),
    )

    assert result.candidate_count == 7
    assert result.emitted_count == 1
    assert result.triggers[0].occurrence.local_due_at.startswith(
        "2026-09-26T16:00:00"
    )


def test_schedule_004_spring_forward_nonexistent_time_is_skipped() -> None:
    schedule = _daily(
        local_time="02:30:00",
        start_date="2026-03-08",
        end_date="2026-03-08",
    )

    result = WallClockScheduleProducer().poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 3, 8, 0, 0, tzinfo=UTC),
        through_inclusive=datetime(2026, 3, 9, 0, 0, tzinfo=UTC),
    )

    assert result.candidate_count == 0
    assert result.emitted_count == 0


def test_schedule_005_fall_back_ambiguous_time_obeys_policy() -> None:
    earlier = _daily(
        local_time="01:30:00",
        start_date="2026-11-01",
        end_date="2026-11-01",
        ambiguous_time_policy=AmbiguousTimePolicy.EARLIER,
    )
    later = _daily(
        local_time="01:30:00",
        start_date="2026-11-01",
        end_date="2026-11-01",
        ambiguous_time_policy=AmbiguousTimePolicy.LATER,
    )
    producer = WallClockScheduleProducer()
    window = {
        "after_exclusive": datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
        "through_inclusive": datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    }

    first = producer.poll(schedule=earlier, **window)
    second = producer.poll(schedule=later, **window)

    assert first.triggers[0].occurrence.due_at_utc == "2026-11-01T08:30:00Z"
    assert second.triggers[0].occurrence.due_at_utc == "2026-11-01T09:30:00Z"
    assert (
        first.triggers[0].occurrence.occurrence_id
        != second.triggers[0].occurrence.occurrence_id
    )


def test_schedule_006_catch_up_fails_closed_on_occurrence_limit() -> None:
    schedule = _daily(
        start_date="2026-09-20",
        max_occurrences_per_poll=2,
    )

    with pytest.raises(
        MacroScheduleContractError,
        match="due occurrences exceed max_occurrences_per_poll",
    ):
        WallClockScheduleProducer().poll(
            schedule=schedule,
            after_exclusive=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
            through_inclusive=datetime(2026, 9, 26, 23, 30, tzinfo=UTC),
        )


def test_schedule_007_poll_window_is_bounded() -> None:
    schedule = _daily(start_date="2025-01-01")

    with pytest.raises(
        MacroScheduleContractError,
        match="poll window cannot exceed",
    ):
        WallClockScheduleProducer().poll(
            schedule=schedule,
            after_exclusive=datetime(2025, 1, 1, tzinfo=UTC),
            through_inclusive=datetime(2026, 9, 26, tzinfo=UTC),
        )


def test_schedule_008_schedule_observation_enters_v08_start_gate_only(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _daily()
    trigger = WallClockScheduleProducer().poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    ).triggers[0]
    plan = _plan()
    request = RunStartRequest.build(
        request_id="request:schedule-001",
        run_id="run:schedule-001",
        plan=plan,
        observation=trigger.observation,
        requested_at="2026-09-26T23:01:01+00:00",
    )
    policy = RunStartAdmissionPolicy(
        policy_id="policy:schedule-start",
        allowed_trigger_types=("schedule",),
        allowed_source_ids=("source:wall-clock",),
    )

    admitted = MacroRunStartGate(ledger).admit(
        observation=trigger.observation,
        request=request,
        policy=policy,
        plan=plan,
    )

    assert admitted.receipt.status is StartStatus.STARTED
    assert admitted.run is not None
    assert admitted.run.state.status is RunnerStatus.WAITING_OPERATION
    assert ledger.recent() == []


def test_schedule_009_schedule_and_occurrence_are_zero_authority() -> None:
    schedule = _daily()
    result = WallClockScheduleProducer().poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )
    occurrence = result.triggers[0].occurrence
    observation = result.triggers[0].observation

    assert schedule.operational_authority is False
    assert schedule.action_authority is False
    assert schedule.execution_authority is False
    assert occurrence.operational_authority is False
    assert occurrence.action_authority is False
    assert occurrence.execution_authority is False
    assert observation.operational_authority is False
    assert observation.action_authority is False
    assert observation.execution_authority is False
