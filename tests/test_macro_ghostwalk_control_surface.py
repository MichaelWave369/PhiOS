from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phios.macro_ghostwalk_control_surface import (
    GhostWalkControlAction,
    GhostWalkControlReason,
    GhostWalkControlResult,
    GhostWalkControlSurface,
    GhostWalkRecoveryState,
)
from phios.macro_ghostwalk_host_service import (
    GhostWalkHostHealth,
    GhostWalkHostStatus,
)
from phios.spine.ledger import RealityLedger

SURFACE = "ghostwalk-control:test"
HOST = "ghostwalk-host:test"
SESSION = "ghost:control-session"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


class FakeHost:
    host_id = HOST

    def __init__(self) -> None:
        self.status = GhostWalkHostStatus.STOPPED
        self.run_generation = 0
        self.session_id: str | None = None
        self.baseline_armed = False
        self.start_calls = 0
        self.stop_calls = 0
        self.arm_calls = 0
        self.disarm_calls = 0

    def health(self) -> GhostWalkHostHealth:
        return GhostWalkHostHealth(
            host_id=self.host_id,
            status=self.status,
            run_generation=self.run_generation,
            session_id=self.session_id,
            listener_alive=self.status in {
                GhostWalkHostStatus.RUNNING,
                GhostWalkHostStatus.DEGRADED,
            },
            tick_alive=self.status in {
                GhostWalkHostStatus.RUNNING,
                GhostWalkHostStatus.DEGRADED,
            },
            baseline_armed=self.baseline_armed,
            baseline_sha256=(
                _sha("baseline") if self.baseline_armed else None
            ),
            baseline_age_ms=0 if self.baseline_armed else None,
            baseline_refresh_due=(
                self.status is GhostWalkHostStatus.DEGRADED
                and not self.baseline_armed
            ),
            error_type=(
                "RuntimeError"
                if self.status is GhostWalkHostStatus.FAILED
                else None
            ),
            observed_at="2026-09-27T05:40:00+00:00",
        )

    def start(self, *, session_id: str) -> GhostWalkHostHealth:
        self.start_calls += 1
        self.run_generation += 1
        self.session_id = session_id
        self.status = GhostWalkHostStatus.RUNNING
        self.baseline_armed = True
        return self.health()

    def stop(self) -> GhostWalkHostHealth:
        self.stop_calls += 1
        self.session_id = None
        self.status = GhostWalkHostStatus.STOPPED
        self.baseline_armed = False
        return self.health()

    def arm_baseline(self) -> GhostWalkHostHealth:
        self.arm_calls += 1
        if self.session_id is None:
            raise RuntimeError("host is not running")
        self.status = GhostWalkHostStatus.RUNNING
        self.baseline_armed = True
        return self.health()

    def disarm_baseline(self) -> GhostWalkHostHealth:
        self.disarm_calls += 1
        if self.session_id is None:
            raise RuntimeError("host is not running")
        self.status = GhostWalkHostStatus.DEGRADED
        self.baseline_armed = False
        return self.health()


def _surface(
    tmp_path: Path,
    *,
    host: FakeHost | None = None,
) -> tuple[GhostWalkControlSurface, FakeHost, RealityLedger]:
    ledger = _ledger(tmp_path)
    actual_host = host or FakeHost()
    surface = GhostWalkControlSurface(
        ledger=ledger,
        host=actual_host,
        surface_id=SURFACE,
    )
    return surface, actual_host, ledger


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_control_001_stopped_snapshot_exposes_safe_actions(
    tmp_path: Path,
) -> None:
    surface, _, _ = _surface(tmp_path)

    snapshot = surface.snapshot()

    assert snapshot.host_status is GhostWalkHostStatus.STOPPED
    assert snapshot.available_actions == (
        GhostWalkControlAction.START,
        GhostWalkControlAction.STATUS,
    )
    assert snapshot.recovery_state is GhostWalkRecoveryState.NONE
    assert snapshot.operational_authority is False
    assert snapshot.action_authority is False
    assert snapshot.execution_authority is False


def test_control_002_start_and_stop_are_receipted(
    tmp_path: Path,
) -> None:
    surface, host, ledger = _surface(tmp_path)

    started = surface.apply(
        action=GhostWalkControlAction.START,
        session_id=SESSION,
    )
    stopped = surface.apply(
        action=GhostWalkControlAction.STOP,
    )

    assert started.receipt.result is GhostWalkControlResult.APPLIED
    assert started.receipt.reason is GhostWalkControlReason.HOST_STARTED
    assert started.snapshot.host_status is GhostWalkHostStatus.RUNNING
    assert started.snapshot.baseline_armed is True
    assert stopped.receipt.reason is GhostWalkControlReason.HOST_STOPPED
    assert stopped.snapshot.host_status is GhostWalkHostStatus.STOPPED
    assert host.start_calls == 1
    assert host.stop_calls == 1
    rows = ledger.ghostwalk_control_receipts(surface_id=SURFACE)
    assert [row["sequence"] for row in rows] == [0, 1]


def test_control_003_disarm_and_arm_are_host_mediated(
    tmp_path: Path,
) -> None:
    host = FakeHost()
    host.start(session_id=SESSION)
    surface, _, _ = _surface(tmp_path, host=host)

    before = surface.snapshot()
    assert GhostWalkControlAction.DISARM in before.available_actions

    disarmed = surface.apply(
        action=GhostWalkControlAction.DISARM,
    )
    assert disarmed.snapshot.host_status is GhostWalkHostStatus.DEGRADED
    assert disarmed.snapshot.baseline_armed is False
    assert GhostWalkControlAction.ARM in disarmed.snapshot.available_actions

    armed = surface.apply(action=GhostWalkControlAction.ARM)
    assert armed.snapshot.host_status is GhostWalkHostStatus.RUNNING
    assert armed.snapshot.baseline_armed is True
    assert host.disarm_calls == 1
    assert host.arm_calls == 1


def test_control_004_stop_when_already_stopped_is_noop(
    tmp_path: Path,
) -> None:
    surface, host, _ = _surface(tmp_path)

    outcome = surface.apply(action=GhostWalkControlAction.STOP)

    assert outcome.receipt.result is GhostWalkControlResult.NOOP
    assert outcome.receipt.reason is GhostWalkControlReason.ALREADY_STOPPED
    assert host.stop_calls == 0


def test_control_005_unavailable_arm_is_rejected_without_host_call(
    tmp_path: Path,
) -> None:
    surface, host, _ = _surface(tmp_path)

    outcome = surface.apply(action=GhostWalkControlAction.ARM)

    assert outcome.receipt.result is GhostWalkControlResult.REJECTED
    assert (
        outcome.receipt.reason
        is GhostWalkControlReason.ACTION_NOT_AVAILABLE
    )
    assert host.arm_calls == 0


def test_control_006_transition_summary_links_latest_editable_note(
    tmp_path: Path,
) -> None:
    surface, _, ledger = _surface(tmp_path)
    inference_sha = _sha("inference")
    _append_jsonl(
        ledger.path.parent / "transition-inference-receipts.jsonl",
        {
            "receipt_sha256": inference_sha,
            "session_id": SESSION,
            "action_observation_sha256": _sha("action"),
            "status": "CANDIDATES",
            "inferred_at": "2026-09-27T05:40:01+00:00",
            "candidates": [
                {
                    "expectation": {"kind": "SEMANTIC_PRESENT"},
                },
                {
                    "expectation": {"kind": "WINDOW_TITLE_CHANGED"},
                },
            ],
        },
    )
    _append_jsonl(
        ledger.path.parent / "operator-log-revisions.jsonl",
        {
            "revision_sha256": _sha("note-1"),
            "target_sha256": inference_sha,
            "revision": 1,
            "status": "ACTIVE",
        },
    )
    _append_jsonl(
        ledger.path.parent / "operator-log-revisions.jsonl",
        {
            "revision_sha256": _sha("note-2"),
            "target_sha256": inference_sha,
            "revision": 2,
            "status": "ACTIVE",
        },
    )

    snapshot = surface.snapshot()

    assert len(snapshot.learned_transitions) == 1
    learned = snapshot.learned_transitions[0]
    assert learned.candidate_kinds == (
        "SEMANTIC_PRESENT",
        "WINDOW_TITLE_CHANGED",
    )
    assert learned.operator_note_revision == 2
    assert learned.operator_note_revision_sha256 == _sha("note-2")


def test_control_007_recent_issues_aggregate_runtime_layers(
    tmp_path: Path,
) -> None:
    surface, _, ledger = _surface(tmp_path)
    _append_jsonl(
        ledger.path.parent / "ghostwalk-host-receipts.jsonl",
        {
            "receipt_sha256": _sha("host-issue"),
            "host_id": HOST,
            "status": "FAILED",
            "reason": "TICK_FAILED",
            "observed_at": "2026-09-27T05:40:01+00:00",
        },
    )
    _append_jsonl(
        ledger.path.parent / "transition-coordinator-receipts.jsonl",
        {
            "receipt_sha256": _sha("coord-issue"),
            "status": "HELD",
            "reason": "BASELINE_STALE",
            "coordinated_at": "2026-09-27T05:40:02+00:00",
        },
    )
    _append_jsonl(
        ledger.path.parent / "baseline-refresh-receipts.jsonl",
        {
            "receipt_sha256": _sha("refresh-issue"),
            "status": "DEGRADED",
            "reason": "FRAME_UNAVAILABLE",
            "observed_at": "2026-09-27T05:40:03+00:00",
        },
    )

    issues = surface.snapshot().recent_issues

    assert [item.source for item in issues] == [
        "BASELINE_REFRESH",
        "TRANSITION_COORDINATOR",
        "HOST",
    ]


def test_control_008_recovery_state_is_visible(
    tmp_path: Path,
) -> None:
    surface, _, ledger = _surface(tmp_path)
    _append_jsonl(
        ledger.path.parent / "ghostwalk-host-receipts.jsonl",
        {
            "receipt_sha256": _sha("recovery"),
            "host_id": HOST,
            "event_kind": "RECOVERY",
            "status": "STOPPED",
            "reason": "PRIOR_RUN_ABANDONED",
            "observed_at": "2026-09-27T05:40:00+00:00",
        },
    )

    snapshot = surface.snapshot()

    assert (
        snapshot.recovery_state
        is GhostWalkRecoveryState.PRIOR_RUN_ABANDONED
    )
    assert snapshot.recovery_receipt_sha256 == _sha("recovery")


def test_control_009_status_is_observation_only(
    tmp_path: Path,
) -> None:
    surface, host, _ = _surface(tmp_path)

    outcome = surface.apply(action=GhostWalkControlAction.STATUS)

    assert outcome.receipt.result is GhostWalkControlResult.OBSERVED
    assert outcome.receipt.reason is GhostWalkControlReason.STATUS_OBSERVED
    assert host.start_calls == 0
    assert host.stop_calls == 0
    assert host.arm_calls == 0
    assert host.disarm_calls == 0


def test_control_010_control_receipts_form_hash_chain(
    tmp_path: Path,
) -> None:
    surface, _, ledger = _surface(tmp_path)

    surface.apply(action=GhostWalkControlAction.STATUS)
    surface.apply(
        action=GhostWalkControlAction.START,
        session_id=SESSION,
    )
    surface.apply(action=GhostWalkControlAction.DISARM)
    surface.apply(action=GhostWalkControlAction.ARM)
    surface.apply(action=GhostWalkControlAction.STOP)

    rows = ledger.ghostwalk_control_receipts(surface_id=SURFACE)
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
