from __future__ import annotations

import pytest

from phios.covenant.models import BoundaryContext, BoundaryTransitionRequest
from phios.covenant.zones import (
    TrustZone,
    actor_zones,
    allowed_transitions,
    require_transition,
)


def test_zone_names_are_strictly_enumerated() -> None:
    assert actor_zones() == (
        TrustZone.EXTERNAL,
        TrustZone.INTAKE,
        TrustZone.IDENTIFIED,
        TrustZone.BOUNDED,
        TrustZone.GOVERNED_EXECUTION,
        TrustZone.OBSERVED,
        TrustZone.VERIFIED_OUTPUT,
    )


@pytest.mark.parametrize("source,target", allowed_transitions())
def test_legal_actor_transitions_are_exact(
    source: TrustZone,
    target: TrustZone,
) -> None:
    require_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TrustZone.EXTERNAL, TrustZone.IDENTIFIED),
        (TrustZone.INTAKE, TrustZone.BOUNDED),
        (TrustZone.IDENTIFIED, TrustZone.OBSERVED),
        (TrustZone.BOUNDED, TrustZone.INTAKE),
        (TrustZone.OBSERVED, TrustZone.GOVERNED_EXECUTION),
        (TrustZone.VERIFIED_OUTPUT, TrustZone.EXTERNAL),
    ],
)
def test_illegal_transitions_reject(
    source: TrustZone,
    target: TrustZone,
) -> None:
    with pytest.raises(ValueError, match="illegal Covenant boundary transition"):
        require_transition(source, target)


def test_root_cannot_be_actor_context_or_transition_destination() -> None:
    with pytest.raises(ValueError, match="ROOT authority plane"):
        BoundaryContext(
            zone=TrustZone.ROOT,
            identity_seal_sha256="1" * 64,
        )

    with pytest.raises(ValueError, match="ROOT authority plane"):
        BoundaryTransitionRequest(
            source_zone=TrustZone.IDENTIFIED,
            target_zone=TrustZone.ROOT,
            subject_seal_sha256="1" * 64,
        )


def test_boundary_context_is_deterministic_and_zero_authority() -> None:
    context = BoundaryContext(
        zone=TrustZone.BOUNDED,
        identity_seal_sha256="1" * 64,
        execution_circle_sha256="2" * 64,
        previous_transition_receipt_sha256="3" * 64,
    )

    assert BoundaryContext.from_dict(context.to_dict()) == context
    assert context.action_authority is False
    assert context.execution_authority is False
    assert context.sha256() == BoundaryContext.from_dict(context.to_dict()).sha256()


def test_boundary_context_unknown_fields_fail_closed() -> None:
    payload = BoundaryContext(
        zone=TrustZone.IDENTIFIED,
        identity_seal_sha256="1" * 64,
    ).to_dict()
    payload["memory_authority"] = "retrieved-context"

    with pytest.raises(ValueError, match="unknown=memory_authority"):
        BoundaryContext.from_dict(payload)


def test_transition_request_hash_is_deterministic() -> None:
    request = BoundaryTransitionRequest(
        source_zone=TrustZone.IDENTIFIED,
        target_zone=TrustZone.BOUNDED,
        subject_seal_sha256="1" * 64,
        evidence_refs=("sandbox-policy:2", "sandbox-preflight:3"),
    )

    restored = BoundaryTransitionRequest.from_dict(request.to_dict())

    assert restored == request
    assert restored.sha256() == request.sha256()
    assert request.action_authority is False
    assert request.execution_authority is False


def test_transition_request_rejects_unsorted_or_duplicate_evidence() -> None:
    with pytest.raises(ValueError, match="evidence_refs must be sorted"):
        BoundaryTransitionRequest(
            source_zone=TrustZone.IDENTIFIED,
            target_zone=TrustZone.BOUNDED,
            subject_seal_sha256="1" * 64,
            evidence_refs=("z", "a"),
        )

    with pytest.raises(ValueError, match="must not contain duplicates"):
        BoundaryTransitionRequest(
            source_zone=TrustZone.IDENTIFIED,
            target_zone=TrustZone.BOUNDED,
            subject_seal_sha256="1" * 64,
            evidence_refs=("a", "a"),
        )
