from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path

from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    PHIVESSEL_SESSION_ID_HEADER,
    PHIVESSEL_SESSION_TOKEN_HEADER,
    GhostWalkControlServer,
)
from phios.phivessel_bridge import (
    PHIVESSEL_BRIDGE_VERSION,
    PhiVesselBridgeService,
)
from phios.phivessel_handshake import (
    PhiVesselHostHandshakeService,
    PhiVesselSessionOperation,
)
from phios.spine.ledger import RealityLedger

NOW = datetime(2026, 9, 27, 23, 40, 0, tzinfo=UTC)
TOKEN = "c" * 64


class _Snapshot:
    def to_dict(self) -> dict[str, object]:
        return {"active": False, "state": "IDLE"}


class _Surface:
    def snapshot(self) -> _Snapshot:
        return _Snapshot()


def _server(
    tmp_path: Path,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    ledger = RealityLedger(tmp_path / "ledger" / "receipts.jsonl")
    bridge = PhiVesselBridgeService(
        ledger=ledger,
        ghostwalk_surface=_Surface(),
        lease_executor=None,
        clock=lambda: NOW,
    )
    handshake = PhiVesselHostHandshakeService(
        bridge_version=PHIVESSEL_BRIDGE_VERSION,
        available_operations=(
            PhiVesselSessionOperation.OBSERVE,
            PhiVesselSessionOperation.PROPOSE,
        ),
        session_ttl_seconds=60,
        clock=lambda: NOW,
        token_factory=lambda: TOKEN,
    )
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=_Surface(),  # type: ignore[arg-type]
        phivessel_bridge=bridge,
        phivessel_handshake=handshake,
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
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(
        LOOPBACK_HOST,
        server.server_address[1],
        timeout=2,
    )
    encoded = None
    merged = {"accept": "application/json"}
    if headers:
        merged.update(headers)
    if body is not None:
        encoded = json.dumps(body).encode("utf-8")
        merged["content-type"] = "application/json"
        merged["content-length"] = str(len(encoded))
    connection.request(
        method,
        path,
        body=encoded,
        headers=merged,
    )
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, payload


def _handshake(
    server: GhostWalkControlServer,
    operations: list[str],
) -> dict[str, object]:
    status, payload = _request(
        server,
        "POST",
        "/api/v1/phivessel/handshake",
        body={
            "clientInstanceId": "super-phivessel:desktop:local",
            "clientNonce": "nonce_0123456789abcdef",
            "supportedBridgeVersions": [PHIVESSEL_BRIDGE_VERSION],
            "requestedOperations": operations,
        },
    )
    assert status == 200
    handshake = payload["handshake"]
    assert isinstance(handshake, dict)
    return handshake


def _session_headers(
    handshake: dict[str, object],
) -> dict[str, str]:
    session_id = handshake["session_id"]
    token = handshake["session_token"]
    assert isinstance(session_id, str)
    assert isinstance(token, str)
    return {
        PHIVESSEL_SESSION_ID_HEADER: session_id,
        PHIVESSEL_SESSION_TOKEN_HEADER: token,
    }


def test_handshake_is_zero_authority_and_not_identity_authentication(
    tmp_path: Path,
) -> None:
    server, thread = _server(tmp_path)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/phivessel/handshake",
            body={
                "clientInstanceId": "super-phivessel:desktop:local",
                "clientNonce": "nonce_0123456789abcdef",
                "supportedBridgeVersions": [PHIVESSEL_BRIDGE_VERSION],
                "requestedOperations": ["OBSERVE", "PROPOSE"],
            },
        )
        assert status == 200
        assert payload["clientIdentityAuthenticated"] is False
        assert payload["transportSessionOnly"] is True
        assert payload["actionLeaseStillRequiredForExecution"] is True
        assert payload["actionAuthority"] is False
        assert payload["executionAuthority"] is False
        handshake = payload["handshake"]
        assert isinstance(handshake, dict)
        assert handshake["client_identity_authenticated"] is False
        assert handshake["session_token"] == TOKEN
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_observe_requires_negotiated_session(tmp_path: Path) -> None:
    server, thread = _server(tmp_path)
    try:
        status, _ = _request(
            server,
            "GET",
            "/api/v1/phivessel/observe?kind=BRIDGE_STATUS",
        )
        assert status == 401

        handshake = _handshake(server, ["OBSERVE"])
        status, payload = _request(
            server,
            "GET",
            "/api/v1/phivessel/observe?kind=BRIDGE_STATUS",
            headers=_session_headers(handshake),
        )
        assert status == 200
        assert payload["actionAuthority"] is False
        assert payload["executionAuthority"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unnegotiated_operation_is_rejected(tmp_path: Path) -> None:
    server, thread = _server(tmp_path)
    try:
        handshake = _handshake(server, ["OBSERVE"])
        status, _ = _request(
            server,
            "POST",
            "/api/v1/phivessel/proposals",
            headers=_session_headers(handshake),
            body={
                "workId": "work:1",
                "packetRefs": ["promotion:1"],
                "proposalType": "RUN",
            },
        )
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_handshake_cannot_negotiate_unavailable_execute(
    tmp_path: Path,
) -> None:
    server, thread = _server(tmp_path)
    try:
        handshake = _handshake(
            server,
            ["OBSERVE", "EXECUTE"],
        )
        assert handshake["granted_operations"] == ["OBSERVE"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_handshake_does_not_write_proposal_or_authority_state(
    tmp_path: Path,
) -> None:
    server, thread = _server(tmp_path)
    try:
        _handshake(server, ["OBSERVE", "PROPOSE"])
        ledger = server.phivessel_bridge._ledger
        assert ledger.phivessel_proposals() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
