from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from phios.macro_schedule import ScheduleCadence, WallClockSchedule
from phios.macro_schedule_service import ScheduleService
from phios.macro_schedule_worker import (
    MacroScheduleWorkerContractError,
    ScheduleWorkerManager,
    WorkerAcquireStatus,
    WorkerLeaseEventKind,
    WorkerTickStatus,
)
from phios.macro_start import RunStartAdmissionPolicy
from phios.spine.ledger import RealityLedger


def _operation() -> Operation:
    return Operation(
        operation_id="macro.schedule-worker.write",
        operation_version="0.11.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "worker", "text": "tick"},
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
            macro_id="macro:schedule-worker-test",
            macro_version="0.11.0",
            steps=(DoStep(_operation()),),
        )
    )


def _schedule(*, local_time: str = "16:00:00") -> WallClockSchedule:
    return WallClockSchedule(
        schedule_id="schedule:worker-test",
        source_id="source:schedule-worker",
        cadence=ScheduleCadence.DAILY,
        timezone="America/Los_Angeles",
        local_time=local_time,
        start_date="2026-09-26",
    )


def _policy() -> RunStartAdmissionPolicy:
    return RunStartAdmissionPolicy(
        policy_id="policy:schedule-worker",
        allowed_trigger_types=("schedule",),
        allowed_source_ids=("source:schedule-worker",),
    )


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _service(
    ledger: RealityLedger,
    *,
    service_id: str,
    cursor: datetime,
    schedule: WallClockSchedule | None = None,
):
    chosen = schedule or _schedule()
    plan = _plan()
    policy = _policy()
    ScheduleService(ledger).start(
        service_id=service_id,
        schedule=chosen,
        plan=plan,
        policy=policy,
        cursor_utc=cursor,
    )
    return chosen, plan, policy


def test_worker_001_single_live_owner_per_service(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:owner",
        cursor=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
    )
    first = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:owner",
        worker_id="worker:a",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 23, 0, tzinfo=UTC),
        lease_seconds=60,
        max_tick_seconds=60,
    )
    second = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:owner",
        worker_id="worker:b",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 23, 0, 1, tzinfo=UTC),
        lease_seconds=60,
        max_tick_seconds=60,
    )

    assert first.status is WorkerAcquireStatus.ACQUIRED
    assert first.worker is not None
    assert second.status is WorkerAcquireStatus.HELD
    assert second.worker is None
    assert second.event.event_kind is WorkerLeaseEventKind.ACQUIRE_HELD

    first.worker.release(
        released_at=datetime(2026, 9, 26, 23, 0, 2, tzinfo=UTC)
    )


def test_worker_002_tick_reanchors_and_starts_due_control_flow(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:tick",
        cursor=datetime(2026, 9, 26, 22, 59, tzinfo=UTC),
    )
    acquired = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:tick",
        worker_id="worker:tick",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 22, 59, 30, tzinfo=UTC),
        lease_seconds=300,
        max_tick_seconds=120,
    )
    assert acquired.worker is not None

    outcome = acquired.worker.tick(
        tick_at=datetime(2026, 9, 26, 23, 1, tzinfo=UTC)
    )

    assert outcome.receipt.tick_status is WorkerTickStatus.COMMITTED
    assert outcome.receipt.cycle_index == 0
    assert outcome.receipt.cursor_before_utc == "2026-09-26T22:59:00Z"
    assert outcome.receipt.cursor_after_utc == "2026-09-26T23:01:00Z"
    assert outcome.receipt.service_state_before_sha256 != (
        outcome.receipt.service_state_after_sha256
    )
    assert outcome.service_outcome is not None
    assert len(outcome.receipt.cycle_anchor_sha256) == 64
    assert ledger.recent() == []

    run_rows = ledger.macro_run_journal_entries()
    assert len(run_rows) == 2
    assert run_rows[-1]["state"]["status"] == "WAITING_OPERATION"

    acquired.worker.release(
        released_at=datetime(2026, 9, 26, 23, 1, 1, tzinfo=UTC)
    )


def test_worker_003_renewal_extends_same_generation(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:renew",
        cursor=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )
    acquired = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:renew",
        worker_id="worker:renew",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 22, 1, tzinfo=UTC),
        lease_seconds=60,
        max_tick_seconds=30,
    )
    assert acquired.worker is not None
    original = acquired.worker.lease

    renewed = acquired.worker.renew(
        renewed_at=datetime(2026, 9, 26, 22, 1, 30, tzinfo=UTC)
    )

    assert renewed.generation == original.generation
    assert renewed.renewal_index == 1
    assert renewed.previous_lease_sha256 == original.lease_sha256
    assert renewed.valid_until == "2026-09-26T22:02:30Z"

    acquired.worker.release(
        released_at=datetime(2026, 9, 26, 22, 1, 31, tzinfo=UTC)
    )


def test_worker_004_expired_lease_cannot_tick_or_renew(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:expiry",
        cursor=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )
    acquired = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:expiry",
        worker_id="worker:expiry",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
        lease_seconds=1,
        max_tick_seconds=1,
    )
    assert acquired.worker is not None

    with pytest.raises(
        MacroScheduleWorkerContractError,
        match="lease expired before tick",
    ):
        acquired.worker.tick(
            tick_at=datetime(2026, 9, 26, 22, 0, 2, tzinfo=UTC)
        )
    with pytest.raises(
        MacroScheduleWorkerContractError,
        match="expired schedule worker lease cannot be renewed",
    ):
        acquired.worker.renew(
            renewed_at=datetime(2026, 9, 26, 22, 0, 2, tzinfo=UTC)
        )

    acquired.worker.release(
        released_at=datetime(2026, 9, 26, 22, 0, 3, tzinfo=UTC)
    )


def test_worker_005_release_allows_next_generation_owner(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:generation",
        cursor=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )
    first = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:generation",
        worker_id="worker:first",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
    )
    assert first.worker is not None
    first_generation = first.worker.lease.generation
    first.worker.release(
        released_at=datetime(2026, 9, 26, 22, 0, 1, tzinfo=UTC)
    )

    second = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:generation",
        worker_id="worker:second",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=datetime(2026, 9, 26, 22, 0, 2, tzinfo=UTC),
    )
    assert second.worker is not None
    assert second.worker.lease.generation == first_generation + 1
    assert second.worker.lease.previous_lease_sha256 is not None

    second.worker.release(
        released_at=datetime(2026, 9, 26, 22, 0, 3, tzinfo=UTC)
    )


def test_worker_006_long_cycle_chain_does_not_drift(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    schedule = _schedule(local_time="23:59:59")
    base = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:long-cycle",
        cursor=base,
        schedule=schedule,
    )
    acquired = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:long-cycle",
        worker_id="worker:long-cycle",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=base,
        lease_seconds=300,
        max_tick_seconds=1,
    )
    assert acquired.worker is not None

    anchors: list[str] = []
    for index in range(128):
        now = base + timedelta(seconds=index + 1)
        outcome = acquired.worker.tick(tick_at=now)
        assert outcome.receipt.cycle_index == index
        assert outcome.receipt.tick_status is WorkerTickStatus.COMMITTED
        assert outcome.receipt.cursor_after_utc == now.isoformat().replace(
            "+00:00",
            "Z",
        )
        anchors.append(outcome.receipt.cycle_anchor_sha256)

    rows = ledger.schedule_worker_tick_receipts(
        service_id="svc:long-cycle"
    )
    assert [row["cycle_index"] for row in rows] == list(range(128))
    assert len(set(anchors)) == 128

    reconstructed = ScheduleService(ledger).current(
        service_id="svc:long-cycle",
        schedule=schedule,
        plan=plan,
        policy=policy,
    )
    assert reconstructed.state.cursor_utc == (
        base + timedelta(seconds=128)
    ).isoformat().replace("+00:00", "Z")
    assert ledger.next_schedule_worker_cycle_index(
        service_id="svc:long-cycle"
    ) == 128

    acquired.worker.release(
        released_at=base + timedelta(seconds=129)
    )


def test_worker_007_tick_at_cursor_is_noop_but_receipted(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    cursor = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
    schedule, plan, policy = _service(
        ledger,
        service_id="svc:noop",
        cursor=cursor,
    )
    acquired = ScheduleWorkerManager(ledger).acquire(
        service_id="svc:noop",
        worker_id="worker:noop",
        schedule=schedule,
        plan=plan,
        policy=policy,
        acquired_at=cursor,
        lease_seconds=60,
        max_tick_seconds=60,
    )
    assert acquired.worker is not None

    outcome = acquired.worker.tick(tick_at=cursor)

    assert outcome.receipt.tick_status is WorkerTickStatus.NOOP
    assert outcome.service_outcome is None
    assert outcome.receipt.cursor_before_utc == outcome.receipt.cursor_after_utc
    assert outcome.receipt.operational_authority is False
    assert outcome.receipt.action_authority is False
    assert outcome.receipt.execution_authority is False

    acquired.worker.release(
        released_at=cursor + timedelta(seconds=1)
    )
