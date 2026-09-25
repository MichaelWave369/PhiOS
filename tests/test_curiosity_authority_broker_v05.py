from __future__ import annotations

import stat
from pathlib import Path

import pytest

from phios.curiosity_authority_broker import (
    BROKER_ID,
    CuriosityAuthorityBroker,
    CuriosityAuthorityBrokerError,
    OperatorApproval,
    create_operator_approval,
    load_or_create_local_key,
)


def _browser_payload() -> dict[str, object]:
    return {
        "artifact_kind": "creative_seed",
        "title": "Nested bubble gear rhythm",
        "content": (
            "Explore whether recursive gear timing is a useful "
            "musical metaphor without asserting a physical law."
        ),
        "created_at": "2026-09-25T21:10:00+00:00",
        "tags": ["gear", "music", "recursion"],
        "evidence_ref_sha256s": [],
        "parent_artifact_sha256s": [],
    }


def _broker(tmp_path: Path) -> CuriosityAuthorityBroker:
    return CuriosityAuthorityBroker(
        state_root=tmp_path / "state",
        principal_id="operator:test",
        key_path=tmp_path / "authority" / "broker.key",
    )


def _approval(
    broker: CuriosityAuthorityBroker,
    request_id: str,
    payload_sha256: str,
) -> OperatorApproval:
    return create_operator_approval(
        request_id=request_id,
        payload_sha256=payload_sha256,
        principal_id=broker.principal_id,
        approved_at="2026-09-25T21:10:30+00:00",
        key=broker.key,
    )


def test_local_key_is_created_private_and_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "authority" / "broker.key"
    first = load_or_create_local_key(path)
    second = load_or_create_local_key(path)

    assert first == second
    assert len(first) == 32
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_browser_request_cannot_choose_operator_principal(
    tmp_path: Path,
) -> None:
    broker = _broker(tmp_path)
    request = broker.create_request(_browser_payload())

    assert request.payload.created_by == "operator:test"
    assert request.status == "pending"
    public = request.public_dict()
    assert public["actionAuthority"] is False
    assert public["executionAuthority"] is False
    assert "ActionLease" not in str(public)
    assert "action_lease" not in str(public).lower()


def test_exact_operator_approval_persists_once_through_governed_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _broker(tmp_path)
    request = broker.create_request(_browser_payload())

    class _Clock:
        @staticmethod
        def now(_tz):
            from datetime import UTC, datetime

            return datetime.fromisoformat(
                "2026-09-25T21:10:31+00:00"
            ).astimezone(UTC)

    import phios.curiosity_authority_broker as module

    monkeypatch.setattr(module, "datetime", _Clock)

    approval = _approval(
        broker,
        request.request_id,
        request.payload_sha256,
    )
    result = broker.approve(approval)

    assert result.status == "succeeded"
    assert result.reason == "curiosity_persisted"
    assert result.artifact_sha256 is not None
    assert result.execution_receipt is not None
    assert result.execution_receipt["status"] == "SUCCEEDED"
    assert result.execution_receipt["action_authority"] is False
    assert result.execution_receipt["execution_authority"] is False
    assert result.execution_receipt["effect_performed"] is False

    stored = broker._service.store.artifacts()
    assert len(stored) == 1
    assert stored[0].title == "Nested bubble gear rhythm"
    assert stored[0].action_authority is False
    assert stored[0].execution_authority is False

    with pytest.raises(
        CuriosityAuthorityBrokerError,
        match="not pending",
    ):
        broker.approve(approval)

    assert len(broker._service.store.artifacts()) == 1


def test_forged_hmac_is_rejected_before_persistence(
    tmp_path: Path,
) -> None:
    broker = _broker(tmp_path)
    request = broker.create_request(_browser_payload())
    valid = _approval(
        broker,
        request.request_id,
        request.payload_sha256,
    )
    forged = OperatorApproval(
        request_id=valid.request_id,
        payload_sha256=valid.payload_sha256,
        principal_id=valid.principal_id,
        approved_at=valid.approved_at,
        broker_id=BROKER_ID,
        proof_hmac_sha256="0" * 64,
    )

    with pytest.raises(
        CuriosityAuthorityBrokerError,
        match="HMAC verification failed",
    ):
        broker.approve(forged)

    assert broker._service.store.artifacts() == []
    assert request.status == "pending"


def test_hmac_for_one_payload_cannot_approve_another(
    tmp_path: Path,
) -> None:
    broker = _broker(tmp_path)
    first = broker.create_request(_browser_payload())

    changed = _browser_payload()
    changed["title"] = "Different exact payload"
    second = broker.create_request(changed)

    approval = _approval(
        broker,
        first.request_id,
        first.payload_sha256,
    )
    forged_scope = OperatorApproval(
        request_id=second.request_id,
        payload_sha256=second.payload_sha256,
        principal_id=approval.principal_id,
        approved_at=approval.approved_at,
        broker_id=approval.broker_id,
        proof_hmac_sha256=approval.proof_hmac_sha256,
    )

    with pytest.raises(
        CuriosityAuthorityBrokerError,
        match="HMAC verification failed",
    ):
        broker.approve(forged_scope)

    assert broker._service.store.artifacts() == []


def test_wrong_principal_approval_is_rejected(
    tmp_path: Path,
) -> None:
    broker = _broker(tmp_path)
    request = broker.create_request(_browser_payload())
    approval = create_operator_approval(
        request_id=request.request_id,
        payload_sha256=request.payload_sha256,
        principal_id="operator:someone-else",
        approved_at="2026-09-25T21:10:30+00:00",
        key=broker.key,
    )

    with pytest.raises(
        CuriosityAuthorityBrokerError,
        match="principal mismatch",
    ):
        broker.approve(approval)

    assert broker._service.store.artifacts() == []


def test_browser_request_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    broker = _broker(tmp_path)
    payload = _browser_payload()
    payload["approved"] = True

    with pytest.raises(
        CuriosityAuthorityBrokerError,
        match="fields mismatch",
    ):
        broker.create_request(payload)
