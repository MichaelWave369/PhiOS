from __future__ import annotations

from pathlib import Path

import pytest

from phios.phivid_operator_approval import (
    create_phivid_operator_approval,
    load_or_create_operator_key,
    PHIVidOperatorApproval,
    verify_phivid_operator_approval,
)


def test_wrong_key_fails_closed(tmp_path: Path) -> None:
    key_a = load_or_create_operator_key(tmp_path / "a.key")
    key_b = load_or_create_operator_key(tmp_path / "b.key")

    approval = create_phivid_operator_approval(
        envelope_sha256="1" * 64,
        admission_receipt_sha256="2" * 64,
        authority_epoch_sha256="3" * 64,
        operator_id="operator:local",
        approved_at="2026-10-05T04:15:00Z",
        key=key_a,
    )
    assert verify_phivid_operator_approval(approval, key=key_b) is False
