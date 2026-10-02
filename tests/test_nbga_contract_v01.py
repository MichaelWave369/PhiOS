from __future__ import annotations

import pytest

from phios.adapters.nbga import (
    BUBBLE_ZERO_STATUS_SCHEMA,
    MEMORY_RECEIPT_SCHEMA,
    BubbleZeroStatus,
    MemoryReceipt,
    NBGContractError,
)


def memory_payload() -> dict[str, object]:
    return {
        "schema_version": MEMORY_RECEIPT_SCHEMA,
        "bubble_id": "bubble:phios:vm-qualification",
        "bubble_version": 3,
        "observable": "The qualified candidate completed the VirtualBox compatibility path.",
        "trust_state": "verified",
        "confidence": 1.0,
        "evidence": ["event:qualification:36916494462", "artifact:iso:33bfb342"],
        "gear_path": [
            {
                "gear_id": "gear:project-to-qualification",
                "transform": "evidence",
                "source": "bubble:phios",
                "destination": "bubble:phios:vm-qualification",
            }
        ],
        "event_head": "event:qualification:36916494462",
        "provenance_root": "sha256:receipt-root",
    }


def bubble_zero_payload() -> dict[str, object]:
    return {
        "schema_version": BUBBLE_ZERO_STATUS_SCHEMA,
        "system_id": "phios",
        "epoch": 7,
        "verified": True,
        "governance_root": "sha256:governance",
        "event_log_head": "sha256:event-head",
        "topology_root": "sha256:topology",
        "anchor_root": "sha256:anchor",
        "commitment_root": "sha256:commitments",
        "last_checkpoint": "checkpoint:7",
    }


def test_memory_receipt_accepts_only_normalized_observable_state() -> None:
    receipt = MemoryReceipt.from_payload(memory_payload())

    assert receipt.bubble_id == "bubble:phios:vm-qualification"
    assert receipt.bubble_version == 3
    assert receipt.trust_state == "verified"
    assert receipt.gear_path[0].transform == "evidence"
    assert receipt.gear_path[0].source == "bubble:phios"
    assert receipt.gear_path[0].destination == "bubble:phios:vm-qualification"


@pytest.mark.parametrize(
    "field",
    ["payload", "payload_ref", "internal_state", "raw_state", "private_state", "secret"],
)
def test_memory_receipt_rejects_private_or_internal_state(field: str) -> None:
    payload = memory_payload()
    payload[field] = "must-not-cross-boundary"

    with pytest.raises(NBGContractError, match="forbidden"):
        MemoryReceipt.from_payload(payload)


@pytest.mark.parametrize("field", ["authority", "authority_grant", "capability_grant"])
def test_memory_receipt_cannot_smuggle_authority(field: str) -> None:
    payload = memory_payload()
    payload[field] = "elevated"

    with pytest.raises(NBGContractError, match="forbidden"):
        MemoryReceipt.from_payload(payload)


def test_memory_receipt_fails_closed_on_unknown_contract_fields() -> None:
    payload = memory_payload()
    payload["implementation_hint"] = "private-routing-algorithm"

    with pytest.raises(NBGContractError, match="unknown"):
        MemoryReceipt.from_payload(payload)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("inf"), float("nan"), True])
def test_memory_receipt_rejects_invalid_confidence(confidence: object) -> None:
    payload = memory_payload()
    payload["confidence"] = confidence

    with pytest.raises(NBGContractError, match="confidence"):
        MemoryReceipt.from_payload(payload)


def test_bubble_zero_status_is_minimal_continuity_projection() -> None:
    status = BubbleZeroStatus.from_payload(bubble_zero_payload())

    assert status.system_id == "phios"
    assert status.epoch == 7
    assert status.verified is True
    assert status.last_checkpoint == "checkpoint:7"


def test_bubble_zero_rejects_raw_state_and_authority() -> None:
    for field in ("raw_state", "authority"):
        payload = bubble_zero_payload()
        payload[field] = "not-public"
        with pytest.raises(NBGContractError, match="forbidden"):
            BubbleZeroStatus.from_payload(payload)


def test_contract_schema_versions_are_explicit_and_fail_closed() -> None:
    receipt = memory_payload()
    receipt["schema_version"] = "phikernel.nbga.memory-receipt.v2"
    with pytest.raises(NBGContractError, match="schema_version"):
        MemoryReceipt.from_payload(receipt)

    status = bubble_zero_payload()
    status["schema_version"] = "phikernel.nbga.bubble-zero-status.v2"
    with pytest.raises(NBGContractError, match="schema_version"):
        BubbleZeroStatus.from_payload(status)
