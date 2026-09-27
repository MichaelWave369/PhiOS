from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phios.macro_ghostwalk_control_server import (
    GhostWalkControlBridgeError,
    parse_phivessel_execute_payload,
    parse_phivessel_observe_query,
    parse_phivessel_proposal_payload,
    phivessel_execute_envelope,
    phivessel_observation_envelope,
    phivessel_proposal_envelope,
)
from phios.macro_lease_execution_handoff import GhostWalkLeaseExecutionReceipt
from phios.phivessel_bridge import (
    PHIVESSEL_BRIDGE_VERSION,
    PhiVesselBridgeError,
    PhiVesselBridgeService,
    PhiVesselBridgeUnavailableError,
    PhiVesselObservationKind,
    PhiVesselProposalType,
)
from phios.spine.ledger import RealityLedger

NOW = datetime(2026, 9, 27, 20, 0, 0, tzinfo=UTC)
LEASE = "a" * 64


class _Snapshot:
    def to_dict(self) -> dict[str, object]:
        return {"active": False, "state": "IDLE"}


class _Surface:
    def snapshot(self) -> _Snapshot:
        return _Snapshot()


class _Executor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(
        self,
        *,
        action_lease_sha256: str,
    ) -> GhostWalkLeaseExecutionReceipt:
        self.calls.append(action_lease_sha256)
        return GhostWalkLeaseExecutionReceipt(
            status="HELD",
            reason="lease_consumed",
            action_lease_sha256=action_lease_sha256,
            attempted_at=NOW.isoformat(),
            lease_record_sha256=None,
            target_inference_receipt_sha256=None,
            executable_binding_sha256=None,
            authority_epoch_sha256=None,
            policy_sha256=None,
            enforcement_profile_sha256=None,
            spine_receipt_id=None,
            spine_permission_status=None,
            spine_execution_status=None,
            executor_entered=False,
            lease_claimed=False,
            lease_consumed=False,
            replay_blocked=True,
            effect_performed=False,
        )


def _service(
    tmp_path: Path,
    *,
    executor: _Executor | None = None,
) -> PhiVesselBridgeService:
    return PhiVesselBridgeService(
        ledger=RealityLedger(tmp_path / "ledger" / "receipts.jsonl"),
        ghostwalk_surface=_Surface(),
        lease_executor=executor,
        clock=lambda: NOW,
    )


def test_bridge_status_is_zero_authority_and_reports_execution_mount(
    tmp_path: Path,
) -> None:
    executor = _Executor()
    service = _service(tmp_path, executor=executor)

    observation = service.observe(
        kind=PhiVesselObservationKind.BRIDGE_STATUS
    )

    assert observation.payload["bridge_version"] == PHIVESSEL_BRIDGE_VERSION
    assert observation.payload["execution_available"] is True
    assert observation.payload["proposal_creates_authority_request"] is False
    assert observation.payload["proposal_creates_lease"] is False
    assert observation.action_authority is False
    assert observation.execution_authority is False
    assert observation.effect_performed is False


def test_ghostwalk_observation_is_read_only(tmp_path: Path) -> None:
    service = _service(tmp_path)

    observation = service.observe(
        kind=PhiVesselObservationKind.GHOSTWALK_CONTROL
    )

    assert observation.payload == {
        "snapshot": {"active": False, "state": "IDLE"}
    }
    assert observation.effect_performed is False


def test_proposal_is_documentary_only_and_persisted(tmp_path: Path) -> None:
    service = _service(tmp_path)

    packet = service.propose(
        work_id="work_bridge_001",
        packet_refs=("promotion:2", "promotion:1", "promotion:1"),
        proposal_type=PhiVesselProposalType.RUN,
    )

    assert packet.packet_refs == ("promotion:1", "promotion:2")
    assert packet.authority_request_created is False
    assert packet.authorization_granted is False
    assert packet.action_lease_created is False
    assert packet.action_authority is False
    assert packet.execution_authority is False
    rows = service._ledger.phivessel_proposals(work_id="work_bridge_001")
    assert len(rows) == 1
    assert rows[0]["proposal_sha256"] == packet.proposal_sha256


def test_proposal_requires_evidence_reference(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(PhiVesselBridgeError, match="at least one"):
        service.propose(
            work_id="work_bridge_001",
            packet_refs=(),
            proposal_type=PhiVesselProposalType.RUN,
        )


def test_execute_delegates_only_existing_lease_identity(tmp_path: Path) -> None:
    executor = _Executor()
    service = _service(tmp_path, executor=executor)

    receipt = service.execute(action_lease_sha256=LEASE)

    assert executor.calls == [LEASE]
    assert receipt.action_lease_sha256 == LEASE
    assert receipt.action_authority is False
    assert receipt.execution_authority is False


def test_execute_is_unavailable_without_trusted_executor(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(
        PhiVesselBridgeUnavailableError,
        match="not mounted",
    ):
        service.execute(action_lease_sha256=LEASE)


def test_transport_execute_accepts_lease_id_only() -> None:
    assert parse_phivessel_execute_payload({"leaseId": LEASE}) == LEASE

    with pytest.raises(
        GhostWalkControlBridgeError,
        match="leaseId only",
    ):
        parse_phivessel_execute_payload(
            {"leaseId": LEASE, "payload": {"x": 1}}
        )


def test_transport_observe_and_proposal_are_bounded() -> None:
    kind, lease = parse_phivessel_observe_query(
        "kind=LEASE_STATUS&leaseId=" + LEASE
    )
    assert kind is PhiVesselObservationKind.LEASE_STATUS
    assert lease == LEASE

    work, refs, proposal_type = parse_phivessel_proposal_payload(
        {
            "workId": "work_bridge_001",
            "packetRefs": ["promotion:1"],
            "proposalType": "PATCH",
        }
    )
    assert work == "work_bridge_001"
    assert refs == ("promotion:1",)
    assert proposal_type is PhiVesselProposalType.PATCH


def test_transport_envelopes_preserve_authority_boundary(
    tmp_path: Path,
) -> None:
    executor = _Executor()
    service = _service(tmp_path, executor=executor)

    observed = phivessel_observation_envelope(
        service,
        kind=PhiVesselObservationKind.BRIDGE_STATUS,
    )
    proposed = phivessel_proposal_envelope(
        service,
        work_id="work_bridge_001",
        packet_refs=("promotion:1",),
        proposal_type=PhiVesselProposalType.RUN,
    )
    executed = phivessel_execute_envelope(
        service,
        action_lease_sha256=LEASE,
    )

    assert observed["actionAuthority"] is False
    assert proposed["authorityRequestCreated"] is False
    assert proposed["actionLeaseCreated"] is False
    assert proposed["bridgeMutation"] is True
    assert executed["actionAuthority"] is False
    assert executed["executionAuthority"] is False
    assert executed["receipt"]["action_lease_sha256"] == LEASE
