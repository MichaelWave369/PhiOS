from __future__ import annotations

import json
from pathlib import Path

from phios.phivid_operator_approval import (
    PHIVidOperatorApproval,
    create_phivid_operator_approval,
    load_or_create_operator_key,
    verify_phivid_operator_approval,
)


def test_operator_approval_binds_exact_payload_and_verifies(tmp_path: Path) -> None:
    key_path = tmp_path / "phivid.key"
    key = load_or_create_operator_key(key_path)

    approval = create_phivid_operator_approval(
        envelope_sha256="1" * 64,
        admission_receipt_sha256="2" * 64,
        authority_epoch_sha256="3" * 64,
        operator_id="operator:local",
        approved_at="2026-10-05T04:15:00+00:00",
        key=key,
    )

    assert verify_phivid_operator_approval(approval, key=key) is True
    assert approval.operational_authority is False
    assert approval.action_authority is False
    assert approval.execution_authority is False
    assert len(approval.payload_sha256) == 64
    assert len(approval.proof_hmac_sha256) == 64


def test_tampering_breaks_operator_approval_verification(tmp_path: Path) -> None:
    key = load_or_create_operator_key(tmp_path / "phivid.key")
    approval = create_phivid_operator_approval(
        envelope_sha256="1" * 64,
        admission_receipt_sha256="2" * 64,
        authority_epoch_sha256="3" * 64,
        operator_id="operator:local",
        approved_at="2026-10-05T04:15:00+00:00",
        key=key,
    )
    payload = approval.to_dict()
    payload["operator_id"] = "operator:other"
    tampered = PHIVidOperatorApproval.from_dict(payload)

    assert verify_phivid_operator_approval(tampered, key=key) is False


def test_operator_key_is_created_private(tmp_path: Path) -> None:
    path = tmp_path / "authority" / "phivid.key"
    first = load_or_create_operator_key(path)
    second = load_or_create_operator_key(path)

    assert first == second
    assert len(first) == 32
    assert path.stat().st_mode & 0o077 == 0
