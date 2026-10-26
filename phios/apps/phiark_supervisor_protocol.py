"""PhiARK R1.2: deterministic supervisor lifecycle protocol, not a process runner.

This module is a *simulator* for future governed supervision. It performs no
I/O, creates no process, does not probe or remove Unix sockets, and confers
no launch, network, install, or gateway authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Literal

SupervisorPhase = Literal["stopped", "starting", "ready", "stopping", "failed", "blocked"]
SupervisorEvent = Literal[
    "request_start", "observe_ready", "request_stop", "request_restart",
    "observe_stopped", "observe_exit", "deadline", "manual_recover",
]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_START_BUDGET = 30
_STOP_BUDGET = 15
_MAX_TICK = 10**12


def _digest(body: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class PhiARKSupervisorModel:
    archive_review_sha256: str
    runtime_preview_sha256: str
    phase: SupervisorPhase = "stopped"
    sequence: int = 0
    last_tick: int = 0
    deadline_tick: int | None = None
    socket_tag: str | None = None
    restart_requested: bool = False
    previous_receipt_sha256: str | None = None
    schema: str = "phios.phiark_supervisor_model.v0.1"
    launch_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema != "phios.phiark_supervisor_model.v0.1":
            raise ValueError("unsupported PhiARK supervisor model schema")
        for label, value in (
            ("archive review", self.archive_review_sha256),
            ("runtime preview", self.runtime_preview_sha256),
        ):
            if not _SHA256.fullmatch(value):
                raise ValueError(f"invalid {label} digest")
        if self.previous_receipt_sha256 is not None and not _SHA256.fullmatch(
            self.previous_receipt_sha256
        ):
            raise ValueError("invalid supervisor receipt chain digest")
        if self.socket_tag is not None and not _SHA256.fullmatch(self.socket_tag):
            raise ValueError("socket tag must be an opaque 64-digit digest")
        if self.phase not in {
            "stopped", "starting", "ready", "stopping", "failed", "blocked",
        }:
            raise ValueError("unsupported supervisor phase")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("invalid supervisor event sequence")
        if type(self.last_tick) is not int or not 0 <= self.last_tick <= _MAX_TICK:
            raise ValueError("invalid simulated logical time")
        if self.deadline_tick is not None and (
            type(self.deadline_tick) is not int
            or not self.last_tick <= self.deadline_tick <= _MAX_TICK
        ):
            raise ValueError("invalid supervisor deadline")
        if (self.phase in {"starting", "stopping"}) != (self.deadline_tick is not None):
            raise ValueError("only transitional phases may hold a deadline")
        if self.socket_tag is not None and self.phase not in {"ready", "stopping"}:
            raise ValueError("socket tag outside ready or stopping phase")
        if self.restart_requested and self.phase != "stopping":
            raise ValueError("restart intent only allowed during shutdown")
        if self.launch_authority is not False:
            raise ValueError("a PhiARK supervisor model can never grant launch authority")


@dataclass(frozen=True)
class SupervisorObservation:
    tick: int
    process_alive: bool = False
    socket_exists: bool = False
    socket_tag: str | None = None

    def __post_init__(self) -> None:
        if type(self.tick) is not int or not 0 <= self.tick <= _MAX_TICK:
            raise ValueError("invalid simulated observation tick")
        if type(self.process_alive) is not bool or type(self.socket_exists) is not bool:
            raise ValueError("process/socket observations must be booleans")
        if self.socket_tag is not None:
            if not _SHA256.fullmatch(self.socket_tag):
                raise ValueError("invalid observed socket tag")
            if not self.socket_exists:
                raise ValueError("socket tag cannot exist without an observed socket")


def simulate_phiark_supervisor_event(
    prior: PhiARKSupervisorModel,
    event: SupervisorEvent,
    observation: SupervisorObservation,
) -> tuple[PhiARKSupervisorModel, dict[str, object]]:
    """Apply a synthetic lifecycle transition and return a hash-chained receipt.

    Observations are caller-supplied *fake inputs*, not verified process, owner,
    socket, credential, Linux namespace, or readiness evidence.
    """
    if event not in {
        "request_start", "observe_ready", "request_stop", "request_restart",
        "observe_stopped", "observe_exit", "deadline", "manual_recover",
    }:
        raise ValueError("unsupported simulated PhiARK lifecycle event")
    if observation.tick < prior.last_tick:
        raise ValueError("simulated logical clock cannot move backwards")
    if prior.sequence >= 100000:
        raise ValueError("bounded simulated lifecycle sequence exhausted")

    phase: SupervisorPhase = prior.phase
    deadline: int | None = prior.deadline_tick
    tag: str | None = prior.socket_tag
    restart = prior.restart_requested
    manual_start_after_stop = False
    note = ""

    if event == "request_start":
        if phase != "stopped" or observation.process_alive or observation.socket_exists:
            raise ValueError("start simulation requires a stopped, socket-free session")
        if observation.tick > _MAX_TICK - _START_BUDGET:
            raise ValueError("start deadline would overflow")
        phase, deadline, tag, restart = "starting", observation.tick + _START_BUDGET, None, False
        note = "simulated start intent recorded; no process launched"
    elif event == "observe_ready":
        if phase != "starting" or deadline is None or observation.tick > deadline:
            raise ValueError("readiness observed outside starting deadline")
        if not observation.process_alive or not observation.socket_exists or observation.socket_tag is None:
            raise ValueError("readiness requires synthetic child and socket evidence")
        phase, deadline, tag = "ready", None, observation.socket_tag
        note = "synthetic readiness observed; physical socket identity unverified"
    elif event in {"request_stop", "request_restart"}:
        if phase not in {"starting", "ready"}:
            raise ValueError("stop/restart requires active simulated lifecycle")
        if observation.tick > _MAX_TICK - _STOP_BUDGET:
            raise ValueError("stop deadline would overflow")
        phase, deadline, restart = "stopping", observation.tick + _STOP_BUDGET, event == "request_restart"
        note = "simulated shutdown intent; no signal was sent"
    elif event == "observe_stopped":
        if phase != "stopping" or deadline is None or observation.tick > deadline:
            raise ValueError("stop acknowledgement outside shutdown deadline")
        if observation.process_alive or observation.socket_exists:
            raise ValueError("cannot confirm stop with a live child or occupied socket")
        manual_start_after_stop = restart
        phase, deadline, tag, restart = "stopped", None, None, False
        note = "restart requires a new explicit request; never auto-start"
    elif event == "observe_exit":
        if phase not in {"starting", "ready", "stopping"} or observation.process_alive:
            raise ValueError("unexpected child-exit observation")
        phase, deadline, tag, restart = "failed", None, None, False
        note = "synthetic child exit; stale sockets never auto-removed"
    elif event == "deadline":
        if phase not in {"starting", "stopping"} or deadline is None or observation.tick < deadline:
            raise ValueError("deadline event requires an expired transitional deadline")
        phase, deadline, tag, restart = "blocked", None, None, False
        note = "simulated deadline exceeded; no forced cleanup or restart"
    elif event == "manual_recover":
        if phase not in {"failed", "blocked"}:
            raise ValueError("manual recovery only applies after failure or block")
        if observation.process_alive or observation.socket_exists:
            raise ValueError("manual recovery refused until child and stale socket are absent")
        phase, deadline, tag, restart = "stopped", None, None, False
        note = "simulated manual recovery; no files or processes altered"

    next_state = replace(
        prior, phase=phase, sequence=prior.sequence + 1,
        last_tick=observation.tick, deadline_tick=deadline,
        socket_tag=tag, restart_requested=restart,
    )
    body: dict[str, object] = {
        "schema": "phios.phiark_supervisor_transition.v0.1",
        "status": "SIMULATED_UNQUALIFIED",
        "app_id": "phi.phiark",
        "archive_review_sha256": prior.archive_review_sha256,
        "runtime_preview_sha256": prior.runtime_preview_sha256,
        "sequence": next_state.sequence,
        "event": event,
        "from_phase": prior.phase,
        "to_phase": next_state.phase,
        "tick": observation.tick,
        "deadline_tick": next_state.deadline_tick,
        "fake_child_alive": observation.process_alive,
        "fake_socket_exists": observation.socket_exists,
        "fake_socket_tag": observation.socket_tag,
        "manual_start_required_after_restart": manual_start_after_stop,
        "pending_restart": next_state.restart_requested,
        "prior_receipt_sha256": prior.previous_receipt_sha256,
        "operations_performed": [],
        "source_authenticated_against_github": False,
        "physical_network_isolation_qualified": False,
        "service_supervision_verified": False,
        "launch_authority": False,
        "install_authority": False,
        "gateway_authority": False,
        "note": note,
    }
    digest = _digest(body)
    receipt = {**body, "receipt_sha256": digest}
    next_state = replace(next_state, previous_receipt_sha256=digest)
    return next_state, receipt
