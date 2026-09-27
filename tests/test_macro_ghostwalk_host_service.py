from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from phios.macro_baseline_refresh_service import BaselineRefreshStatus
from phios.macro_ghostwalk_host_service import (
    GhostWalkHostContractError,
    GhostWalkHostEventKind,
    GhostWalkHostReason,
    GhostWalkHostReceipt,
    GhostWalkHostService,
    GhostWalkHostStatus,
)
from phios.spine.ledger import RealityLedger

HOST_ID = "ghostwalk-host:test"
SESSION = "ghost:host-session"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _health(
    *,
    armed: bool,
    baseline_label: str | None,
    refresh_due: bool = False,
):
    return SimpleNamespace(
        armed=armed,
        session_id=SESSION if armed else None,
        baseline_sha256=(
            None if baseline_label is None else _sha(baseline_label)
        ),
        baseline_age_ms=0 if baseline_label is not None else None,
        refresh_interval_ms=50,
        max_baseline_age_ms=1500,
        refresh_due=refresh_due,
        observed_at="2026-09-27T05:30:00+00:00",
    )


def _service_outcome(
    *,
    label: str,
    status: BaselineRefreshStatus,
    baseline_label: str | None,
):
    return SimpleNamespace(
        receipt=SimpleNamespace(
            status=status,
            receipt_sha256=_sha(f"service:{label}"),
        ),
        health=_health(
            armed=True,
            baseline_label=baseline_label,
            refresh_due=(baseline_label is None),
        ),
        baseline=(
            None
            if baseline_label is None
            else SimpleNamespace(
                baseline_sha256=_sha(baseline_label)
            )
        ),
    )


class FakeBaselineService:
    refresh_interval_ms = 50

    def __init__(
        self,
        *,
        arm_status: BaselineRefreshStatus = BaselineRefreshStatus.FRESH,
        tick_status: BaselineRefreshStatus = BaselineRefreshStatus.FRESH,
        tick_error: Exception | None = None,
    ) -> None:
        self.armed_session_id: str | None = None
        self.arm_status = arm_status
        self.tick_status = tick_status
        self.tick_error = tick_error
        self.arm_calls = 0
        self.tick_calls = 0
        self.handle_calls = 0
        self.disarm_calls = 0
        self.tick_event = threading.Event()
        self.handle_event = threading.Event()
        self.current_baseline_label: str | None = None

    def arm(self, *, session_id: str):
        self.arm_calls += 1
        self.armed_session_id = session_id
        self.current_baseline_label = (
            f"baseline-arm-{self.arm_calls}"
            if self.arm_status is BaselineRefreshStatus.FRESH
            else None
        )
        return _service_outcome(
            label=f"arm-{self.arm_calls}",
            status=self.arm_status,
            baseline_label=self.current_baseline_label,
        )

    def tick(self):
        self.tick_calls += 1
        self.tick_event.set()
        if self.tick_error is not None:
            raise self.tick_error
        self.current_baseline_label = (
            f"baseline-tick-{self.tick_calls}"
            if self.tick_status is BaselineRefreshStatus.FRESH
            else None
        )
        return _service_outcome(
            label=f"tick-{self.tick_calls}",
            status=self.tick_status,
            baseline_label=self.current_baseline_label,
        )

    def handle_listener_outcome(self, outcome):
        self.handle_calls += 1
        self.handle_event.set()
        self.current_baseline_label = f"baseline-after-{self.handle_calls}"
        return SimpleNamespace(
            coordination=SimpleNamespace(
                receipt=SimpleNamespace(
                    receipt_sha256=_sha(
                        f"coordination-{self.handle_calls}"
                    )
                )
            ),
            service_receipt=SimpleNamespace(
                status=BaselineRefreshStatus.FRESH,
                receipt_sha256=_sha(
                    f"coordination-service-{self.handle_calls}"
                ),
            ),
            health=_health(
                armed=True,
                baseline_label=self.current_baseline_label,
            ),
            baseline=SimpleNamespace(
                baseline_sha256=_sha(self.current_baseline_label)
            ),
        )

    def disarm(self):
        self.disarm_calls += 1
        self.armed_session_id = None
        self.current_baseline_label = None
        return SimpleNamespace(
            receipt=SimpleNamespace(
                status=BaselineRefreshStatus.DISARMED,
                receipt_sha256=_sha(f"disarm-{self.disarm_calls}"),
            ),
            health=_health(
                armed=False,
                baseline_label=None,
                refresh_due=False,
            ),
            baseline=None,
        )

    def health(self, *, observed_at: str):
        return _health(
            armed=self.armed_session_id is not None,
            baseline_label=self.current_baseline_label,
            refresh_due=(
                self.armed_session_id is not None
                and self.current_baseline_label is None
            ),
        )


class FakeListener:
    def __init__(
        self,
        handler,
        *,
        fail_on_run: Exception | None = None,
    ) -> None:
        self.handler = handler
        self.fail_on_run = fail_on_run
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.session_id: str | None = None

    def run(self, *, session_id: str) -> None:
        self.session_id = session_id
        self.started.set()
        if self.fail_on_run is not None:
            raise self.fail_on_run
        self.stopped.wait(timeout=5.0)

    def stop(self) -> None:
        self.stopped.set()

    def emit(self, outcome) -> object:
        return self.handler(outcome)


class FakeListenerFactory:
    def __init__(self, *, fail_on_run: Exception | None = None) -> None:
        self.fail_on_run = fail_on_run
        self.instances: list[FakeListener] = []

    def __call__(self, handler):
        listener = FakeListener(
            handler,
            fail_on_run=self.fail_on_run,
        )
        self.instances.append(listener)
        return listener


def _host(
    tmp_path: Path,
    *,
    baseline_service: FakeBaselineService | None = None,
    listener_factory: FakeListenerFactory | None = None,
    tick_interval_ms: int = 25,
) -> tuple[
    GhostWalkHostService,
    FakeBaselineService,
    FakeListenerFactory,
    RealityLedger,
]:
    ledger = _ledger(tmp_path)
    service = baseline_service or FakeBaselineService()
    factory = listener_factory or FakeListenerFactory()
    host = GhostWalkHostService(
        ledger=ledger,
        baseline_service=service,
        listener_factory=factory,
        host_id=HOST_ID,
        tick_interval_ms=tick_interval_ms,
        shutdown_timeout_seconds=1.0,
    )
    return host, service, factory, ledger


def _listener_outcome(label: str = "1"):
    return SimpleNamespace(
        receipt=SimpleNamespace(
            receipt_sha256=_sha(f"listener:{label}")
        )
    )


def _wait_for(
    predicate,
    *,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


def test_host_001_clean_start_and_stop(tmp_path: Path) -> None:
    host, service, factory, ledger = _host(tmp_path)

    started = host.start(session_id=SESSION)
    assert started.status is GhostWalkHostStatus.RUNNING
    assert factory.instances[0].started.wait(timeout=1.0)
    assert started.baseline_armed is True

    stopped = host.stop()

    assert stopped.status is GhostWalkHostStatus.STOPPED
    assert stopped.listener_alive is False
    assert stopped.tick_alive is False
    assert service.disarm_calls == 1
    rows = ledger.ghostwalk_host_receipts(host_id=HOST_ID)
    assert rows[0]["event_kind"] == "START"
    assert rows[-2]["reason"] == "STOP_REQUESTED"
    assert rows[-1]["reason"] == "STOPPED_CLEAN"


def test_host_002_tick_loop_delivers_bounded_ticks(tmp_path: Path) -> None:
    host, service, _, ledger = _host(tmp_path)
    host.start(session_id=SESSION)

    assert service.tick_event.wait(timeout=1.0)
    _wait_for(
        lambda: any(
            row["event_kind"] == "TICK"
            for row in ledger.ghostwalk_host_receipts(host_id=HOST_ID)
        )
    )

    host.stop()
    assert service.tick_calls >= 1


def test_host_003_listener_outcome_reaches_baseline_service(
    tmp_path: Path,
) -> None:
    host, service, factory, ledger = _host(tmp_path)
    host.start(session_id=SESSION)
    listener = factory.instances[0]
    assert listener.started.wait(timeout=1.0)

    listener.emit(_listener_outcome())

    assert service.handle_event.wait(timeout=1.0)
    rows = ledger.ghostwalk_host_receipts(host_id=HOST_ID)
    listener_rows = [
        row for row in rows if row["event_kind"] == "LISTENER"
    ]
    assert len(listener_rows) == 1
    assert (
        listener_rows[0]["listener_receipt_sha256"]
        == _sha("listener:1")
    )
    assert (
        listener_rows[0]["transition_coordinator_receipt_sha256"]
        == _sha("coordination-1")
    )
    host.stop()


def test_host_004_degraded_arm_still_starts_listener(
    tmp_path: Path,
) -> None:
    service = FakeBaselineService(
        arm_status=BaselineRefreshStatus.DEGRADED
    )
    host, _, factory, _ = _host(
        tmp_path,
        baseline_service=service,
    )

    health = host.start(session_id=SESSION)

    assert health.status is GhostWalkHostStatus.DEGRADED
    assert factory.instances[0].started.wait(timeout=1.0)
    assert health.baseline_armed is False
    host.stop()


def test_host_005_restart_recovers_history_but_not_baseline(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    abandoned = GhostWalkHostReceipt(
        host_id=HOST_ID,
        sequence=0,
        run_generation=0,
        event_kind=GhostWalkHostEventKind.START,
        session_id="ghost:old",
        status=GhostWalkHostStatus.RUNNING,
        reason=GhostWalkHostReason.STARTED_FRESH,
        observed_at="2026-09-27T05:20:00+00:00",
        baseline_service_receipt_sha256=_sha("old-service"),
        transition_coordinator_receipt_sha256=None,
        listener_receipt_sha256=None,
        baseline_sha256=_sha("old-baseline"),
        baseline_age_ms=10,
        listener_alive=True,
        tick_alive=True,
        recovered_prior_run=False,
    )
    ledger.append_ghostwalk_host_receipt(abandoned)

    service = FakeBaselineService()
    factory = FakeListenerFactory()
    host = GhostWalkHostService(
        ledger=ledger,
        baseline_service=service,
        listener_factory=factory,
        host_id=HOST_ID,
        tick_interval_ms=25,
        shutdown_timeout_seconds=1.0,
    )

    health = host.start(session_id=SESSION)

    rows = ledger.ghostwalk_host_receipts(host_id=HOST_ID)
    assert rows[1]["event_kind"] == "RECOVERY"
    assert rows[1]["reason"] == "PRIOR_RUN_ABANDONED"
    assert rows[1]["baseline_sha256"] is None
    assert rows[2]["event_kind"] == "START"
    assert rows[2]["run_generation"] == 1
    assert rows[2]["baseline_sha256"] != _sha("old-baseline")
    assert service.arm_calls == 1
    assert health.run_generation == 1
    host.stop()


def test_host_006_corrupted_history_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first = GhostWalkHostReceipt(
        host_id=HOST_ID,
        sequence=0,
        run_generation=0,
        event_kind=GhostWalkHostEventKind.START,
        session_id=SESSION,
        status=GhostWalkHostStatus.RUNNING,
        reason=GhostWalkHostReason.STARTED_FRESH,
        observed_at="2026-09-27T05:20:00+00:00",
        baseline_service_receipt_sha256=_sha("service"),
        transition_coordinator_receipt_sha256=None,
        listener_receipt_sha256=None,
        baseline_sha256=_sha("baseline"),
        baseline_age_ms=0,
        listener_alive=True,
        tick_alive=True,
        recovered_prior_run=False,
    )
    ledger.append_ghostwalk_host_receipt(first)
    path = ledger.path.parent / "ghostwalk-host-receipts.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["baseline_age_ms"] = 999
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    host = GhostWalkHostService(
        ledger=ledger,
        baseline_service=FakeBaselineService(),
        listener_factory=FakeListenerFactory(),
        host_id=HOST_ID,
        tick_interval_ms=25,
        shutdown_timeout_seconds=1.0,
    )

    with pytest.raises(
        GhostWalkHostContractError,
        match="receipt hash mismatch",
    ):
        host.start(session_id=SESSION)


def test_host_007_listener_failure_is_receipted_and_stoppable(
    tmp_path: Path,
) -> None:
    factory = FakeListenerFactory(
        fail_on_run=RuntimeError("listener exploded")
    )
    host, service, _, ledger = _host(
        tmp_path,
        listener_factory=factory,
    )

    host.start(session_id=SESSION)
    _wait_for(
        lambda: host.health().status is GhostWalkHostStatus.FAILED
    )

    rows = ledger.ghostwalk_host_receipts(host_id=HOST_ID)
    assert any(row["reason"] == "LISTENER_FAILED" for row in rows)

    stopped = host.stop()
    assert stopped.status is GhostWalkHostStatus.STOPPED
    assert service.disarm_calls == 1


def test_host_008_tick_failure_stops_listener_and_is_receipted(
    tmp_path: Path,
) -> None:
    service = FakeBaselineService(
        tick_error=RuntimeError("tick exploded")
    )
    host, _, factory, ledger = _host(
        tmp_path,
        baseline_service=service,
    )

    host.start(session_id=SESSION)
    _wait_for(
        lambda: host.health().status is GhostWalkHostStatus.FAILED
    )
    assert factory.instances[0].stopped.wait(timeout=1.0)
    rows = ledger.ghostwalk_host_receipts(host_id=HOST_ID)
    assert any(row["reason"] == "TICK_FAILED" for row in rows)
    host.stop()


def test_host_009_duplicate_start_is_rejected(tmp_path: Path) -> None:
    host, _, _, _ = _host(tmp_path)
    host.start(session_id=SESSION)

    with pytest.raises(
        GhostWalkHostContractError,
        match="already running",
    ):
        host.start(session_id=SESSION)

    host.stop()


def test_host_010_tick_cadence_cannot_exceed_refresh_cadence(
    tmp_path: Path,
) -> None:
    service = FakeBaselineService()

    with pytest.raises(
        GhostWalkHostContractError,
        match="cannot exceed baseline refresh interval",
    ):
        GhostWalkHostService(
            ledger=_ledger(tmp_path),
            baseline_service=service,
            listener_factory=FakeListenerFactory(),
            host_id=HOST_ID,
            tick_interval_ms=100,
            shutdown_timeout_seconds=1.0,
        )


def test_host_011_receipts_are_contiguous_and_hash_chained(
    tmp_path: Path,
) -> None:
    host, _, _, ledger = _host(tmp_path)
    host.start(session_id=SESSION)
    host.stop()

    rows = ledger.ghostwalk_host_receipts(host_id=HOST_ID)
    assert [row["sequence"] for row in rows] == list(range(len(rows)))
    assert rows[0]["previous_receipt_sha256"] is None
    for previous, current in zip(rows[:-1], rows[1:], strict=True):
        assert (
            current["previous_receipt_sha256"]
            == previous["receipt_sha256"]
        )
    assert all(row["operational_authority"] is False for row in rows)
    assert all(row["action_authority"] is False for row in rows)
    assert all(row["execution_authority"] is False for row in rows)
