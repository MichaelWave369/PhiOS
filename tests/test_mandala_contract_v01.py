from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from phios.mandala import (
    MANDALA_CONTRACT_VERSION,
    AuthorityContext,
    Gate,
    MandalaPacket,
    MandalaStatus,
    OriginKind,
    OriginRef,
    PhiCoreState,
)
from phios.spine.runtime import PhiOSSpine


def test_status_vocabulary_is_frozen() -> None:
    assert [status.value for status in MandalaStatus] == [
        "ACCEPTED",
        "REJECTED",
        "QUARANTINED",
        "DEGRADED",
        "BLOCKED",
        "ABORTED",
        "DISPUTED",
        "UNKNOWN",
    ]


def test_four_gates_are_canonical() -> None:
    assert [gate.value for gate in Gate] == [
        "PERCEPTION",
        "DELIBERATION",
        "ACTION",
        "MEMORY",
    ]


def test_phi_core_authority_is_frozen() -> None:
    core = PhiCoreState.initialize(
        task_id="task-1",
        authority_ceiling=("artifact.write",),
        explicit_grants=(),
    )
    with pytest.raises(FrozenInstanceError):
        core.authority = AuthorityContext(
            ceiling=("artifact.write",),
            grants=("artifact.write",),
        )


def test_packet_digest_is_deterministic_and_authority_explicit() -> None:
    authority = AuthorityContext(
        ceiling=("artifact.write",),
        grants=("artifact.write",),
    )
    packet_a = MandalaPacket.create(
        task_id="task-1",
        gate=Gate.ACTION,
        origin=OriginRef(kind=OriginKind.HUMAN, identifier="operator"),
        payload={"b": 2, "a": 1},
        authority=authority,
        allowed_destinations=(Gate.MEMORY,),
    )
    packet_b = MandalaPacket.create(
        task_id="task-1",
        gate=Gate.ACTION,
        origin=OriginRef(kind=OriginKind.HUMAN, identifier="operator"),
        payload={"a": 1, "b": 2},
        authority=authority,
        allowed_destinations=(Gate.MEMORY,),
    )
    assert packet_a.payload_digest == packet_b.payload_digest
    assert packet_a.authority.grants == ("artifact.write",)
    assert packet_a.contract_version == MANDALA_CONTRACT_VERSION


def test_denied_action_emits_blocked_gate_and_action_receipts(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="task-denied")
    legacy = spine.run(
        "commons.text_artifact",
        {"text": "blocked", "name": "blocked"},
    )
    mandala = spine.mandala_ledger.recent(2)
    assert [item["receipt_type"] for item in mandala] == [
        "GateReceipt",
        "ActionReceipt",
    ]
    assert mandala[0]["status"] == "BLOCKED"
    assert mandala[1]["status"] == "BLOCKED"
    assert mandala[1]["outcome"] == "not_executed"
    assert legacy.packet_id == mandala[0]["packet_id"] == mandala[1]["packet_id"]
    assert legacy.mandala_status == "BLOCKED"
    assert not (tmp_path / "artifacts" / "blocked.txt").exists()


def test_authorized_action_is_tied_to_grant_and_artifact(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
        task_id="task-accepted",
    )
    legacy = spine.run(
        "commons.text_artifact",
        {"text": "Mandala Spine", "name": "mandala-proof"},
    )
    mandala = spine.mandala_ledger.recent(2)
    action = mandala[-1]
    assert action["receipt_type"] == "ActionReceipt"
    assert action["status"] == "ACCEPTED"
    assert action["approved_grant"] == ["artifact.write"]
    assert action["side_effect"]["capability_id"] == "commons.text_artifact"
    assert action["external_identifiers"]["artifact_sha256"] == legacy.artifact_sha256
    assert legacy.action_receipt_id == action["receipt_id"]
