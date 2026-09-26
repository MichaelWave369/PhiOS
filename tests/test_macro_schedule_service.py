from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.macro_schedule import (
    MisfirePolicy,
    ScheduleCadence,
    WallClockSchedule,
    WallClockScheduleProducer,
)
from phios.macro_schedule_service import (
    MacroScheduleServiceContractError,
    SchedulePollStatus,
    ScheduleService,
    ScheduleServiceStatus,
)
from phios.macro_start import (
    MacroRunStartGate,
    RunStartAdmissionPolicy,
    StartStatus,
)
from phios.spine.ledger import RealityLedger


def _operation(text: str = "service") -> Operation:
    return Operation(
        operation_id="macro.schedule-service.write",
        operation_version="0.10.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "schedule-service", "text": text},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _plan(text: str = "service"):
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:schedule-service-test",
            macro_version="0.10.0",
            steps=(DoStep(_operation(text)),),
        )
    )


def _schedule(
    *,
    start_date: str = "2026-09-26",
    local_time: str = "16:00:00",
    misfire_policy: MisfirePolicy = MisfirePolicy.CATCH_UP,
) -> WallClockSchedule:
    return WallClockSchedule(
        schedule_id="schedule:service-test",
        source_id="source:schedule-service",
        cadence=ScheduleCadence.DAILY,
        timezone="America/Los_Angeles",
        local_time=local_time,
        start_date=start_date,
        misfire_policy=misfire_policy,
    )


def _policy(*, enabled: bool = True) -> RunStartAdmissionPolicy:
    return RunStartAdmissionPolicy(
        policy_id="policy:schedule-service",
        allowed_trigger_types=("schedule",),
        allowed_source_ids=("source:schedule-service",),
        enabled=enabled,
    )


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def test_schedule_service_001_start_persists_initial_cursor(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    service = ScheduleService(ledger)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()

    started = service.start(
        service_id="svc:one",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )

    assert started.entry_count == 1
    assert started.state.sequence == 0
    assert started.state.cursor_utc == "2026-09-26T22:00:00Z"
    assert started.state.status is ScheduleServiceStatus.ACTIVE
    assert started.state.operational_authority is False
    assert started.state.action_authority is False
    assert started.state.execution_authority is False


def test_schedule_service_002_due_occurrence_starts_run_and_advances_cursor(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    service = ScheduleService(ledger)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()
    service.start(
        service_id="svc:due",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
    )

    outcome = service.poll(
        service_id="svc:due",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert outcome.poll_receipt.poll_status is SchedulePollStatus.COMMITTED
    assert outcome.poll_receipt.cursor_advanced is True
    assert outcome.state.cursor_utc == "2026-09-26T23:01:00Z"
    assert outcome.state.status is ScheduleServiceStatus.ACTIVE
    assert outcome.poll_receipt.emitted_count == 1
    assert outcome.poll_receipt.admissions[0].start_status is StartStatus.STARTED
    assert ledger.recent() == []

    run_rows = ledger.macro_run_journal_entries()
    assert len(run_rows) == 2
    assert run_rows[-1]["state"]["status"] == "WAITING_OPERATION"


def test_schedule_service_003_policy_hold_keeps_cursor_then_revision_retries(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    service = ScheduleService(ledger)
    schedule = _schedule()
    plan = _plan()
    disabled = _policy(enabled=False)
    enabled = _policy(enabled=True)
    service.start(
        service_id="svc:policy-retry",
        schedule=schedule,
        plan=plan,
        policy=disabled,
        cursor_utc=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
    )

    held = service.poll(
        service_id="svc:policy-retry",
        schedule=schedule,
        plan=plan,
        policy=disabled,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert held.poll_receipt.poll_status is SchedulePollStatus.HELD
    assert held.poll_receipt.cursor_advanced is False
    assert held.state.cursor_utc == "2026-09-26T22:59:00Z"
    assert held.state.status is ScheduleServiceStatus.HELD

    retried = ScheduleService(ledger).poll(
        service_id="svc:policy-retry",
        schedule=schedule,
        plan=plan,
        policy=enabled,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert retried.poll_receipt.poll_status is SchedulePollStatus.COMMITTED
    assert retried.state.cursor_utc == "2026-09-26T23:01:00Z"
    assert retried.poll_receipt.admissions[0].start_status is StartStatus.STARTED
    assert retried.state.policy_sha256 == enabled.policy_sha256


def test_schedule_service_004_crash_after_start_admission_replays_safely(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()
    service = ScheduleService(ledger)
    service.start(
        service_id="svc:crash",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
    )

    trigger = WallClockScheduleProducer().poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    ).triggers[0]
    request = ScheduleService.request_for(
        service_id="svc:crash",
        plan=plan,
        trigger=trigger,
    )
    first = MacroRunStartGate(ledger).admit(
        observation=trigger.observation,
        request=request,
        policy=policy,
        plan=plan,
    )
    assert first.receipt.status is StartStatus.STARTED

    replayed = ScheduleService(ledger).poll(
        service_id="svc:crash",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert replayed.poll_receipt.poll_status is SchedulePollStatus.COMMITTED
    assert replayed.poll_receipt.admissions[0].start_status is StartStatus.HELD
    assert replayed.poll_receipt.admissions[0].start_reason == "run_id_exists"
    assert replayed.state.cursor_utc == "2026-09-26T23:01:00Z"

    run_rows = ledger.macro_run_journal_entries(run_id=request.run_id)
    assert len(run_rows) == 2


def test_schedule_service_005_multi_occurrence_window_is_all_or_nothing(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _schedule(start_date="2026-09-25")
    plan = _plan()
    policy = _policy()
    service = ScheduleService(ledger)
    service.start(
        service_id="svc:atomic-window",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 25, 22, 59, tzinfo=UTC),
    )

    producer = WallClockScheduleProducer()
    triggers = producer.poll(
        schedule=schedule,
        after_exclusive=datetime(2026, 9, 25, 22, 59, tzinfo=UTC),
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    ).triggers
    assert len(triggers) == 2

    second_request = ScheduleService.request_for(
        service_id="svc:atomic-window",
        plan=plan,
        trigger=triggers[1],
    )
    assert ledger.claim_macro_run_id(second_request.run_id_sha256) is True

    held = service.poll(
        service_id="svc:atomic-window",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert held.poll_receipt.poll_status is SchedulePollStatus.HELD
    assert held.poll_receipt.cursor_advanced is False
    assert held.state.cursor_utc == "2026-09-25T22:59:00Z"
    assert [item.start_status for item in held.poll_receipt.admissions] == [
        StartStatus.STARTED,
        StartStatus.HELD,
    ]

    ledger.release_macro_run_id_claim(second_request.run_id_sha256)

    committed = ScheduleService(ledger).poll(
        service_id="svc:atomic-window",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert committed.poll_receipt.poll_status is SchedulePollStatus.COMMITTED
    assert committed.poll_receipt.cursor_advanced is True
    assert committed.state.cursor_utc == "2026-09-26T23:01:00Z"
    assert committed.poll_receipt.admissions[0].start_status is StartStatus.HELD
    assert committed.poll_receipt.admissions[0].start_reason == "run_id_exists"
    assert committed.poll_receipt.admissions[1].start_status is StartStatus.STARTED


def test_schedule_service_006_restart_reconstructs_cursor_and_continues(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()
    ScheduleService(ledger).start(
        service_id="svc:restart",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )
    first = ScheduleService(ledger).poll(
        service_id="svc:restart",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 22, 30, tzinfo=UTC),
    )
    assert first.state.cursor_utc == "2026-09-26T22:30:00Z"

    restarted = ScheduleService(ledger)
    current = restarted.current(
        service_id="svc:restart",
        schedule=schedule,
        plan=plan,
        policy=policy,
    )
    assert current.state == first.state

    second = restarted.poll(
        service_id="svc:restart",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )
    assert second.state.cursor_utc == "2026-09-26T23:01:00Z"
    assert second.poll_receipt.admissions[0].start_status is StartStatus.STARTED


def test_schedule_service_007_tampered_state_chain_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()
    service = ScheduleService(ledger)
    service.start(
        service_id="svc:tamper",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )
    service.poll(
        service_id="svc:tamper",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 22, 30, tzinfo=UTC),
    )

    path = tmp_path / "ledger" / "schedule-service-state.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    rows[1]["previous_entry_sha256"] = "f" * 64
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        MacroScheduleServiceContractError,
        match="state entry hash mismatch",
    ):
        ScheduleService(ledger).current(
            service_id="svc:tamper",
            schedule=schedule,
            plan=plan,
            policy=policy,
        )


def test_schedule_service_008_configuration_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    service = ScheduleService(ledger)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()
    service.start(
        service_id="svc:scope",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )

    with pytest.raises(
        MacroScheduleServiceContractError,
        match="binding does not match",
    ):
        service.current(
            service_id="svc:scope",
            schedule=_schedule(local_time="17:00:00"),
            plan=plan,
            policy=policy,
        )


def test_schedule_service_009_poll_receipt_and_state_are_zero_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _schedule()
    plan = _plan()
    policy = _policy()
    service = ScheduleService(ledger)
    service.start(
        service_id="svc:zero",
        schedule=schedule,
        plan=plan,
        policy=policy,
        cursor_utc=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
    )
    outcome = service.poll(
        service_id="svc:zero",
        schedule=schedule,
        plan=plan,
        policy=policy,
        through_inclusive=datetime(2026, 9, 26, 23, 1, tzinfo=UTC),
    )

    assert outcome.state.operational_authority is False
    assert outcome.state.action_authority is False
    assert outcome.state.execution_authority is False
    assert outcome.poll_receipt.operational_authority is False
    assert outcome.poll_receipt.action_authority is False
    assert outcome.poll_receipt.execution_authority is False
