from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlServer,
)
from phios.phivessel_bridge import (
    PHIVESSEL_BRIDGE_VERSION,
    PhiVesselBridgeService,
    PhiVesselObservationKind,
    PhiVesselProposalType,
)
from phios.phivessel_handshake import (
    PhiVesselHostHandshakeService,
    PhiVesselSessionOperation,
)
from phios.phivessel_local_client import PhiVesselLocalClient
from phios.spine.ledger import RealityLedger

NOW = datetime(2026, 9, 27, 23, 50, 0, tzinfo=UTC)
TOKEN = "d" * 64


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


def test_reference_client_handshakes_and_uses_session(
    tmp_path: Path,
) -> None:
    server, thread = _server(tmp_path)
    try:
        client = PhiVesselLocalClient(
            port=server.server_address[1],
        )
        session = client.handshake(
            client_nonce="nonce_0123456789abcdef",
            requested_operations=(
                PhiVesselSessionOperation.OBSERVE,
                PhiVesselSessionOperation.PROPOSE,
                PhiVesselSessionOperation.EXECUTE,
            ),
        )

        assert session.selected_bridge_version == PHIVESSEL_BRIDGE_VERSION
        assert session.granted_operations == (
            PhiVesselSessionOperation.OBSERVE,
            PhiVesselSessionOperation.PROPOSE,
        )
        assert session.client_identity_authenticated is False
        assert session.action_authority is False
        assert session.execution_authority is False

        observed = client.observe(
            kind=PhiVesselObservationKind.BRIDGE_STATUS
        )
        observation = observed["observation"]
        assert isinstance(observation, dict)
        assert observation["effect_performed"] is False

        proposed = client.propose(
            work_id="work:handshake:test",
            packet_refs=("promotion:1",),
            proposal_type=PhiVesselProposalType.RUN,
        )
        proposal = proposed["proposal"]
        assert isinstance(proposal, dict)
        assert proposal["action_lease_created"] is False
        assert proposal["action_authority"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
