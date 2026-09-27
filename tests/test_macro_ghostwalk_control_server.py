from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import Any

import pytest

from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlBridgeError,
    GhostWalkControlServer,
    parse_action_payload,
    status_envelope,
)
from phios.macro_ghostwalk_control_surface import GhostWalkControlAction


@dataclass
class FakeSnapshot:
    marker: str = "snapshot"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "phios.ghostwalk_control_snapshot.v0.25",
            "surface_id": "ghostwalk-control:test",
            "host_id": "ghostwalk-host:test",
            "host_status": "STOPPED",
            "run_generation": 0,
            "session_id": None,
            "listener_alive": False,
            "tick_alive": False,
            "baseline_armed": False,
            "baseline_sha256": None,
            "baseline_age_ms": None,
            "baseline_refresh_due": False,
            "error_type": None,
            "recovery_state": "NONE",
            "recovery_receipt_sha256": None,
            "available_actions": ["START", "STATUS"],
            "last_action_observation_sha256": None,
            "learned_transitions": [],
            "recent_issues": [],
            "observed_at": "2026-09-27T00:00:00+00:00",
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
            "snapshot_sha256": "1" * 64,
        }


@dataclass
class FakeReceipt:
    result_value: str = "APPLIED"

    @property
    def result(self) -> Any:
        return type("Result", (), {"value": self.result_value})()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "phios.ghostwalk_control_receipt.v0.25",
            "surface_id": "ghostwalk-control:test",
            "sequence": 0,
            "action": "START",
            "requested_session_id": "demo",
            "result": self.result_value,
            "reason": "HOST_STARTED",
            "before_snapshot_sha256": "2" * 64,
            "after_snapshot_sha256": "3" * 64,
            "applied_at": "2026-09-27T00:00:00+00:00",
            "error_type": None,
            "previous_receipt_sha256": None,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
            "receipt_sha256": "4" * 64,
        }


@dataclass
class FakeOutcome:
    receipt: FakeReceipt
    snapshot: FakeSnapshot


class FakeSurface:
    def __init__(self) -> None:
        self.calls: list[tuple[GhostWalkControlAction, str | None]] = []

    def snapshot(self) -> FakeSnapshot:
        return FakeSnapshot()

    def apply(
        self,
        *,
        action: GhostWalkControlAction,
        session_id: str | None = None,
    ) -> FakeOutcome:
        self.calls.append((action, session_id))
        return FakeOutcome(FakeReceipt(), FakeSnapshot())


def _start_server(
    surface: FakeSurface,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=surface,  # type: ignore[arg-type]
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()
    return server, thread


def _request(
    server: GhostWalkControlServer,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(
        LOOPBACK_HOST,
        server.server_address[1],
        timeout=2,
    )
    encoded = None
    headers: dict[str, str] = {"accept": "application/json"}
    if body is not None:
        encoded = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
        headers["content-length"] = str(len(encoded))
    connection.request(method, path, body=encoded, headers=headers)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, payload


def test_status_envelope_is_zero_authority() -> None:
    envelope = status_envelope(FakeSurface())  # type: ignore[arg-type]

    assert (
        envelope["transportSchemaVersion"]
        == "phios.ghostwalk-control-transport.v0.26"
    )
    assert envelope["localOnly"] is True
    assert envelope["operationalAuthority"] is False
    assert envelope["actionAuthority"] is False
    assert envelope["executionAuthority"] is False
    assert envelope["effectPerformed"] is False


def test_parse_action_payload_is_strict() -> None:
    action, session_id = parse_action_payload(
        {"action": "START", "session_id": "demo"}
    )
    assert action is GhostWalkControlAction.START
    assert session_id == "demo"

    with pytest.raises(GhostWalkControlBridgeError):
        parse_action_payload({"action": "START"})
    with pytest.raises(GhostWalkControlBridgeError):
        parse_action_payload(
            {"action": "STOP", "session_id": "demo"}
        )
    with pytest.raises(GhostWalkControlBridgeError):
        parse_action_payload(
            {"action": "STATUS", "extra": True}
        )


def test_loopback_server_exposes_status_and_action() -> None:
    surface = FakeSurface()
    server, thread = _start_server(surface)
    try:
        status, payload = _request(
            server,
            "GET",
            "/api/v1/ghostwalk",
        )
        assert status == 200
        assert payload["executionAuthority"] is False
        snapshot = payload["snapshot"]
        assert isinstance(snapshot, dict)
        assert snapshot["host_status"] == "STOPPED"

        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/actions",
            {"action": "START", "session_id": "demo"},
        )
        assert status == 200
        assert payload["controlPlaneMutation"] is True
        assert payload["effectPerformed"] is False
        assert surface.calls == [
            (GhostWalkControlAction.START, "demo")
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_server_rejects_malformed_action() -> None:
    surface = FakeSurface()
    server, thread = _start_server(surface)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/actions",
            {"action": "ARM", "session_id": "not-allowed"},
        )
        assert status == 400
        assert (
            payload["error"]
            == "invalid_ghostwalk_control_request"
        )
        assert payload["executionAuthority"] is False
        assert surface.calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
