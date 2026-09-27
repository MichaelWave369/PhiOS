from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from phios.macro_baseline_refresh_service import (
    BaselineRefreshContractError,
    BaselineRefreshReason,
    BaselineRefreshStatus,
    GhostWalkBaselineRefreshService,
)
from phios.macro_interaction_guard import WindowFrame
from phios.macro_transition_coordinator import GhostWalkTransitionBaseline
from phios.macro_transition_inference import (
    GhostWalkUiStateSnapshot,
    SnapshotPhase,
)
from phios.spine.ledger import RealityLedger

TITLE = "a" * 64
SESSION = "ghost:baseline-refresh"


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    title: str = TITLE,
    left: int = 100,
    captured_at: str = "2026-09-27T05:00:00+00:00",
    foreground: bool = True,
) -> WindowFrame:
    return WindowFrame(
        process_id="pid:4242",
        window_title_sha256=title,
        left_px=left,
        top_px=50,
        width_px=800,
        height_px=600,
        display_scale_percent=100,
        foreground=foreground,
        captured_at=captured_at,
    )


def _baseline(
    *,
    frame: WindowFrame,
    captured_at: str,
    serial: int,
    session_id: str = SESSION,
) -> GhostWalkTransitionBaseline:
    binding = hashlib.sha256(
        f"baseline:{serial}:{captured_at}".encode()
    ).hexdigest()
    snapshot = GhostWalkUiStateSnapshot(
        session_id=session_id,
        action_observation_sha256=binding,
        phase=SnapshotPhase.BEFORE,
        process_id=frame.process_id,
        window_title_sha256=frame.window_title_sha256,
        frame_sha256=frame.frame_sha256,
        semantic_targets=(),
        observed_at=captured_at,
    )
    return GhostWalkTransitionBaseline(
        session_id=session_id,
        baseline_binding_sha256=binding,
        frame=frame,
        state_observation_receipt_sha256=hashlib.sha256(
            f"receipt:{serial}".encode()
        ).hexdigest(),
        state_snapshot=snapshot,
        captured_at=captured_at,
    )


class SequenceClock:
    def __init__(self, *values: str) -> None:
        self.values = list(values)

    def __call__(self) -> str:
        if not self.values:
            raise RuntimeError("clock sequence exhausted")
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


class SequenceFrameProvider:
    provider_id = "test.baseline-refresh-frame"

    def __init__(self, *frames: WindowFrame | None) -> None:
        self.frames = list(frames)
        self.calls = 0

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None:
        self.calls += 1
        if not self.frames:
            return None
        if len(self.frames) == 1:
            return self.frames[0]
        return self.frames.pop(0)


@dataclass
class FakeCoordReceipt:
    receipt_sha256: str


@dataclass
class FakeCoordination:
    receipt: FakeCoordReceipt


class StubCoordinator:
    coordinator_id = "coordinator:test"

    def __init__(
        self,
        *refreshes: GhostWalkTransitionBaseline | None,
        max_baseline_age_ms: int = 1500,
    ) -> None:
        self.max_baseline_age_ms = max_baseline_age_ms
        self._refreshes = list(refreshes)
        self._baseline: GhostWalkTransitionBaseline | None = None
        self.refresh_calls = 0
        self.clear_calls = 0
        self.handle_calls = 0

    @property
    def baseline(self) -> GhostWalkTransitionBaseline | None:
        return self._baseline

    def clear_baseline(self) -> None:
        self.clear_calls += 1
        self._baseline = None

    def refresh_baseline(
        self,
        *,
        session_id: str,
    ) -> GhostWalkTransitionBaseline | None:
        self.refresh_calls += 1
        if not self._refreshes:
            self._baseline = None
            return None
        value = self._refreshes.pop(0)
        self._baseline = value
        return value

    def handle_listener_outcome(self, outcome):
        self.handle_calls += 1
        self._baseline = None
        digest = hashlib.sha256(
            f"coord:{self.handle_calls}".encode()
        ).hexdigest()
        return FakeCoordination(FakeCoordReceipt(digest))


def _service(
    tmp_path: Path,
    *,
    coordinator: StubCoordinator,
    frames: SequenceFrameProvider,
    clock: SequenceClock,
    interval_ms: int = 500,
):
    return GhostWalkBaselineRefreshService(
        ledger=_ledger(tmp_path),
        coordinator=coordinator,
        frame_provider=frames,
        service_id="baseline-service:test",
        refresh_interval_ms=interval_ms,
        clock=clock,
    )


def test_refresh_001_arm_captures_fresh_baseline(tmp_path: Path) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    coordinator = StubCoordinator(first)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(_frame()),
        clock=SequenceClock("2026-09-27T05:00:00+00:00"),
    )

    outcome = service.arm(session_id=SESSION)

    assert outcome.receipt.status is BaselineRefreshStatus.FRESH
    assert outcome.receipt.reason is BaselineRefreshReason.ARMED
    assert outcome.receipt.sequence == 0
    assert outcome.receipt.refreshed is True
    assert outcome.baseline == first
    assert outcome.health.armed is True
    assert outcome.health.refresh_due is False


def test_refresh_002_tick_retains_young_matching_baseline(
    tmp_path: Path,
) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    coordinator = StubCoordinator(first)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:00.200000+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    outcome = service.tick()

    assert outcome.receipt.reason is BaselineRefreshReason.BASELINE_RETAINED
    assert outcome.receipt.baseline_age_ms == 200
    assert outcome.receipt.refreshed is False
    assert coordinator.refresh_calls == 1


def test_refresh_003_tick_refreshes_aging_baseline(tmp_path: Path) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    second = _baseline(
        frame=_frame(captured_at="2026-09-27T05:00:00.600000+00:00"),
        captured_at="2026-09-27T05:00:00.600000+00:00",
        serial=2,
    )
    coordinator = StubCoordinator(first, second)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:00.600000+00:00",
            "2026-09-27T05:00:00.600000+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    outcome = service.tick()

    assert outcome.receipt.reason is BaselineRefreshReason.BASELINE_REFRESHED
    assert outcome.receipt.refreshed is True
    assert outcome.baseline == second
    assert outcome.receipt.prior_baseline_sha256 == first.baseline_sha256
    assert coordinator.refresh_calls == 2


def test_refresh_004_scope_drift_invalidates_and_rebuilds(
    tmp_path: Path,
) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    drifted_frame = _frame(
        left=140,
        captured_at="2026-09-27T05:00:00.100000+00:00",
    )
    second = _baseline(
        frame=drifted_frame,
        captured_at="2026-09-27T05:00:00.100000+00:00",
        serial=2,
    )
    coordinator = StubCoordinator(first, second)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(drifted_frame),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:00.100000+00:00",
            "2026-09-27T05:00:00.100000+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    outcome = service.tick()

    assert (
        outcome.receipt.reason
        is BaselineRefreshReason.SCOPE_DRIFT_REFRESHED
    )
    assert outcome.receipt.invalidated is True
    assert outcome.receipt.refreshed is True
    assert outcome.baseline == second
    assert coordinator.clear_calls >= 2


def test_refresh_005_missing_frame_invalidates_and_degrades(
    tmp_path: Path,
) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    coordinator = StubCoordinator(first)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(None),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:00.100000+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    outcome = service.tick()

    assert outcome.receipt.status is BaselineRefreshStatus.DEGRADED
    assert outcome.receipt.reason is BaselineRefreshReason.FRAME_UNAVAILABLE
    assert outcome.receipt.invalidated is True
    assert outcome.baseline is None
    assert outcome.health.refresh_due is True


def test_refresh_006_failed_refresh_degrades_without_stale_fallback(
    tmp_path: Path,
) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    coordinator = StubCoordinator(first, None)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:00.600000+00:00",
            "2026-09-27T05:00:00.600000+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    outcome = service.tick()

    assert outcome.receipt.status is BaselineRefreshStatus.DEGRADED
    assert (
        outcome.receipt.reason
        is BaselineRefreshReason.BASELINE_CAPTURE_FAILED
    )
    assert outcome.baseline is None
    assert outcome.receipt.prior_baseline_sha256 == first.baseline_sha256


def test_refresh_007_coordination_automatically_rearms(
    tmp_path: Path,
) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    second = _baseline(
        frame=_frame(captured_at="2026-09-27T05:00:01+00:00"),
        captured_at="2026-09-27T05:00:01+00:00",
        serial=2,
    )
    coordinator = StubCoordinator(first, second)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:01+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    outcome = service.handle_listener_outcome(object())

    assert coordinator.handle_calls == 1
    assert outcome.service_receipt.status is BaselineRefreshStatus.FRESH
    assert (
        outcome.service_receipt.reason
        is BaselineRefreshReason.POST_ACTION_REARMED
    )
    assert outcome.service_receipt.refreshed is True
    assert outcome.baseline == second
    assert outcome.health.refresh_due is False


def test_refresh_008_disarm_clears_baseline_and_future_tick_is_idle(
    tmp_path: Path,
) -> None:
    first = _baseline(
        frame=_frame(),
        captured_at="2026-09-27T05:00:00+00:00",
        serial=1,
    )
    coordinator = StubCoordinator(first)
    service = _service(
        tmp_path,
        coordinator=coordinator,
        frames=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T05:00:00+00:00",
            "2026-09-27T05:00:01+00:00",
            "2026-09-27T05:00:02+00:00",
        ),
    )
    service.arm(session_id=SESSION)

    disarmed = service.disarm()
    idle = service.tick()

    assert disarmed.receipt.status is BaselineRefreshStatus.DISARMED
    assert service.armed_session_id is None
    assert idle.receipt.status is BaselineRefreshStatus.DISARMED
    assert coordinator.refresh_calls == 1


def test_refresh_009_receipts_form_contiguous_hash_chain(
    tmp_path: Path,
) -> None:
    baselines = tuple(
        _baseline(
            frame=_frame(
                captured_at=f"2026-09-27T05:00:0{index}+00:00"
            ),
            captured_at=f"2026-09-27T05:00:0{index}+00:00",
            serial=index,
        )
        for index in range(1, 5)
    )
    ledger = _ledger(tmp_path)
    coordinator = StubCoordinator(*baselines)
    service = GhostWalkBaselineRefreshService(
        ledger=ledger,
        coordinator=coordinator,
        frame_provider=SequenceFrameProvider(_frame()),
        service_id="baseline-service:test",
        refresh_interval_ms=500,
        clock=SequenceClock(
            "2026-09-27T05:00:01+00:00",
            "2026-09-27T05:00:02+00:00",
            "2026-09-27T05:00:02+00:00",
            "2026-09-27T05:00:03+00:00",
            "2026-09-27T05:00:03+00:00",
            "2026-09-27T05:00:04+00:00",
            "2026-09-27T05:00:04+00:00",
        ),
    )

    service.arm(session_id=SESSION)
    service.tick()
    service.tick()
    service.tick()

    rows = ledger.baseline_refresh_receipts(
        service_id="baseline-service:test"
    )
    assert [row["sequence"] for row in rows] == [0, 1, 2, 3]
    assert rows[0]["previous_receipt_sha256"] is None
    for previous, current in zip(rows, rows[1:], strict=True):
        assert (
            current["previous_receipt_sha256"]
            == previous["receipt_sha256"]
        )
    assert all(row["operational_authority"] is False for row in rows)
    assert all(row["action_authority"] is False for row in rows)
    assert all(row["execution_authority"] is False for row in rows)


def test_refresh_010_interval_must_precede_stale_boundary(
    tmp_path: Path,
) -> None:
    coordinator = StubCoordinator(max_baseline_age_ms=500)

    with pytest.raises(
        BaselineRefreshContractError,
        match="less than coordinator max baseline age",
    ):
        _service(
            tmp_path,
            coordinator=coordinator,
            frames=SequenceFrameProvider(_frame()),
            clock=SequenceClock("2026-09-27T05:00:00+00:00"),
            interval_ms=500,
        )
