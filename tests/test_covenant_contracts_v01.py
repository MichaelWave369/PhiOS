from __future__ import annotations

import copy

import pytest

import phios.covenant as covenant
from phios.core.governed_action_binding import ActionBindingGrant
from phios.covenant.models import BoundaryTransitionRequest
from phios.covenant.receipts import (
    BoundaryTransitionReceipt,
    TransitionStatus,
    transition_receipt,
)
from phios.covenant.zones import TrustZone


def _request() -> BoundaryTransitionRequest:
    return BoundaryTransitionRequest(
        source_zone=TrustZone.IDENTIFIED,
        target_zone=TrustZone.BOUNDED,
        subject_seal_sha256="1" * 64,
        evidence_refs=("sandbox-policy:abc", "sandbox-preflight:def"),
    )


def test_transition_receipt_digest_is_deterministic() -> None:
    request = _request()
    first = transition_receipt(
        request,
        status=TransitionStatus.ACCEPTED,
        requirements_satisfied=True,
        reason="bounded prerequisites satisfied",
    )
    second = transition_receipt(
        request,
        status=TransitionStatus.ACCEPTED,
        requirements_satisfied=True,
        reason="bounded prerequisites satisfied",
    )

    assert first.sha256() == second.sha256()
    assert first.to_dict() == second.to_dict()
    assert first.action_authority is False
    assert first.execution_authority is False


def test_transition_receipt_round_trip_is_strict() -> None:
    receipt = transition_receipt(
        _request(),
        status=TransitionStatus.HELD,
        requirements_satisfied=False,
        reason="preflight evidence incomplete",
    )

    assert BoundaryTransitionReceipt.from_dict(receipt.to_dict()) == receipt


def test_transition_receipt_tampering_fails_closed() -> None:
    receipt = transition_receipt(
        _request(),
        status=TransitionStatus.ACCEPTED,
        requirements_satisfied=True,
        reason="requirements satisfied",
    )
    payload = copy.deepcopy(receipt.to_dict())
    payload["reason"] = "different reason"

    with pytest.raises(ValueError, match="digest does not match"):
        BoundaryTransitionReceipt.from_dict(payload)


def test_transition_receipt_cannot_carry_authority() -> None:
    request = _request()

    with pytest.raises(ValueError, match="cannot carry authority"):
        BoundaryTransitionReceipt(
            status=TransitionStatus.ACCEPTED,
            source_zone=request.source_zone,
            target_zone=request.target_zone,
            subject_seal_sha256=request.subject_seal_sha256,
            boundary_transition_request_sha256=request.sha256(),
            evidence_refs=request.evidence_refs,
            requirements_satisfied=True,
            reason="requirements satisfied",
            action_authority=True,
        )


def test_receipt_status_and_requirements_must_agree() -> None:
    request = _request()

    with pytest.raises(ValueError, match="ACCEPTED transition requires"):
        transition_receipt(
            request,
            status=TransitionStatus.ACCEPTED,
            requirements_satisfied=False,
            reason="contradictory receipt",
        )

    with pytest.raises(ValueError, match="HELD transition requires"):
        transition_receipt(
            request,
            status=TransitionStatus.HELD,
            requirements_satisfied=True,
            reason="contradictory receipt",
        )


def test_covenant_exports_no_action_binding_grant() -> None:
    assert not hasattr(covenant, "ActionBindingGrant")


def test_covenant_receipt_is_not_an_action_binding_grant() -> None:
    receipt = transition_receipt(
        _request(),
        status=TransitionStatus.ACCEPTED,
        requirements_satisfied=True,
        reason="requirements satisfied",
    )

    assert not isinstance(receipt, ActionBindingGrant)


def test_memory_or_analytics_authority_fields_cannot_be_smuggled_into_receipt() -> None:
    receipt = transition_receipt(
        _request(),
        status=TransitionStatus.ACCEPTED,
        requirements_satisfied=True,
        reason="requirements satisfied",
    )
    payload = receipt.to_dict()
    payload["authority_source"] = "memory:prior-success"

    with pytest.raises(ValueError, match="unknown=authority_source"):
        BoundaryTransitionReceipt.from_dict(payload)


def test_receipt_requires_exact_request_binding() -> None:
    first = _request()
    second = BoundaryTransitionRequest(
        source_zone=TrustZone.BOUNDED,
        target_zone=TrustZone.GOVERNED_EXECUTION,
        subject_seal_sha256=first.subject_seal_sha256,
        evidence_refs=first.evidence_refs,
    )
    receipt = transition_receipt(
        first,
        status=TransitionStatus.ACCEPTED,
        requirements_satisfied=True,
        reason="requirements satisfied",
    )

    assert receipt.boundary_transition_request_sha256 != second.sha256()
