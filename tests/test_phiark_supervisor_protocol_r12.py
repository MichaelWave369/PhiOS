"""PhiARK R1.2 lifecycle protocol tests. Pure, deterministic, no spawned tasks."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from phios.apps.phiark_supervisor_protocol import (
    PhiARKSupervisorModel,
    SupervisorObservation,
    simulate_phiark_supervisor_event,
)

ARCHIVE = "a" * 64
PREVIEW = "b" * 64
SOCKET = "c" * 64


def seed() -> PhiARKSupervisorModel:
    return PhiARKSupervisorModel(
        archive_review_sha256=ARCHIVE,
        runtime_preview_sha256=PREVIEW,
    )


def change(state: PhiARKSupervisorModel, event: str, tick: int, *,
           alive: bool = False, socket: bool = False, tag: str | None = None):
    return simulate_phiark_supervisor_event(
        state, event, SupervisorObservation(
            tick=tick, process_alive=alive, socket_exists=socket, socket_tag=tag,
        ),
    )


def test_simulated_start_ready_stop_has_hash_chained_receipts_without_launch() -> None:
    state = seed()
    state, start = change(state, "request_start", 1)
    assert state.phase == "starting"
    assert state.deadline_tick == 31
    assert start["status"] == "SIMULATED_UNQUALIFIED"
    assert start["operations_performed"] == []
    assert start["launch_authority"] is False

    with pytest.raises(ValueError, match="readiness requires"):
        change(state, "observe_ready", 2, alive=True)
    state, ready = change(state, "observe_ready", 3, alive=True, socket=True, tag=SOCKET)
    assert state.phase == "ready"
    assert state.socket_tag == SOCKET
    assert ready["prior_receipt_sha256"] == start["receipt_sha256"]
    state, stopping = change(state, "request_stop", 4, alive=True, socket=True, tag=SOCKET)
    assert state.phase == "stopping"
    assert stopping["note"].startswith("simulated shutdown")
    with pytest.raises(ValueError, match="live child or occupied socket"):
        change(state, "observe_stopped", 5, socket=True, tag=SOCKET)
    state, stopped = change(state, "observe_stopped", 6)
    assert state.phase == "stopped"
    assert state.socket_tag is None
    assert state.deadline_tick is None
    assert stopped["prior_receipt_sha256"] == stopping["receipt_sha256"]
    assert stopped["manual_start_required_after_restart"] is False
    for record in (start, ready, stopping, stopped):
        body = dict(record)
        expected = body.pop("receipt_sha256")
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        assert expected == digest
        assert record["source_authenticated_against_github"] is False
        assert record["service_supervision_verified"] is False
        assert record["operations_performed"] == []


def test_restart_is_shutdown_only_and_cannot_spawn_automatically() -> None:
    state, _ = change(seed(), "request_start", 1)
    state, _ = change(state, "observe_ready", 2, alive=True, socket=True, tag=SOCKET)
    state, intent = change(state, "request_restart", 3, alive=True, socket=True, tag=SOCKET)
    assert state.phase == "stopping"
    assert state.restart_requested is True
    assert intent["pending_restart"] is True
    with pytest.raises(ValueError, match="requires a stopped"):
        change(state, "request_start", 4)
    state, stopped = change(state, "observe_stopped", 5)
    assert state.phase == "stopped"
    assert state.restart_requested is False
    assert stopped["manual_start_required_after_restart"] is True
    assert stopped["operations_performed"] == []
    state, restart = change(state, "request_start", 6)
    assert state.phase == "starting"
    assert restart["event"] == "request_start"


def test_crash_and_deadline_require_explicit_recovery_without_socket_cleanup() -> None:
    state, _ = change(seed(), "request_start", 1)
    state, failure = change(state, "observe_exit", 2, socket=True, tag=SOCKET)
    assert state.phase == "failed"
    assert failure["operations_performed"] == []
    with pytest.raises(ValueError, match="socket-free"):
        change(state, "request_start", 3, socket=True, tag=SOCKET)
    with pytest.raises(ValueError, match="child and stale socket"):
        change(state, "manual_recover", 4, socket=True, tag=SOCKET)
    state, _ = change(state, "manual_recover", 5)
    assert state.phase == "stopped"

    state, _ = change(state, "request_start", 6)
    with pytest.raises(ValueError, match="expired transitional"):
        change(state, "deadline", 35)
    state, blocked = change(state, "deadline", 36)
    assert state.phase == "blocked"
    assert blocked["launch_authority"] is False
    with pytest.raises(ValueError, match="child and stale socket"):
        change(state, "manual_recover", 37, alive=True)
    state, _ = change(state, "manual_recover", 38)
    assert state.phase == "stopped"


def test_refuse_late_readiness_backward_clock_and_unsafe_socket_data() -> None:
    state, _ = change(seed(), "request_start", 10)
    with pytest.raises(ValueError, match="outside starting deadline"):
        change(state, "observe_ready", 41, alive=True, socket=True, tag=SOCKET)
    with pytest.raises(ValueError, match="backwards"):
        change(state, "observe_ready", 9, alive=True, socket=True, tag=SOCKET)
    with pytest.raises(ValueError, match="without an observed socket"):
        change(state, "observe_ready", 11, alive=True, socket=False, tag=SOCKET)
    with pytest.raises(ValueError, match="requires synthetic child and socket"):
        change(state, "observe_ready", 11, alive=False, socket=True, tag=SOCKET)
    with pytest.raises(ValueError, match="requires synthetic child and socket"):
        change(state, "observe_ready", 11, alive=True, socket=True, tag=None)
    with pytest.raises(ValueError, match="unsupported simulated"):
        change(state, "auto_restart", 11)


def test_forged_launch_authority_and_bad_model_invariants_are_rejected() -> None:
    with pytest.raises(ValueError, match="never grant launch authority"):
        replace(seed(), launch_authority=True)
    with pytest.raises(ValueError, match="deadline"):
        replace(seed(), deadline_tick=50)
    with pytest.raises(ValueError, match="socket tag"):
        replace(seed(), socket_tag=SOCKET)
    with pytest.raises(ValueError, match="review digest"):
        replace(seed(), archive_review_sha256="1")
    with pytest.raises(ValueError, match="only allowed during shutdown"):
        replace(seed(), restart_requested=True)
    with pytest.raises(ValueError, match="simulated logical time"):
        replace(seed(), last_tick=-1)


def test_stopped_state_blocks_existing_child_and_stale_unix_socket() -> None:
    with pytest.raises(ValueError, match="socket-free"):
        change(seed(), "request_start", 1, alive=True)
    with pytest.raises(ValueError, match="socket-free"):
        change(seed(), "request_start", 1, socket=True, tag=SOCKET)
    with pytest.raises(ValueError, match="only applies after failure"):
        change(seed(), "manual_recover", 1)
