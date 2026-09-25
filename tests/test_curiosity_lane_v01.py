from __future__ import annotations

import copy

import pytest

from phios.curiosity import (
    CURIOSITY_ARTIFACT_SCHEMA_VERSION,
    CURIOSITY_PROMOTION_SCHEMA_VERSION,
    CuriosityArtifact,
    CuriosityContractError,
    CuriosityPromotionRequest,
)


EVIDENCE_A = "a" * 64
EVIDENCE_B = "b" * 64
PARENT_A = "c" * 64


def build_artifact() -> CuriosityArtifact:
    return CuriosityArtifact.build(
        artifact_kind="symbol",
        title="Nested bubble gear",
        content=(
            "Explore the nested bubble gear as a symbolic model. "
            "No physical claim is asserted."
        ),
        created_at="2026-09-25T15:40:00+00:00",
        created_by="operator:mikey",
        tags=("GEAR", "symbol", "gear"),
        evidence_ref_sha256s=(EVIDENCE_B, EVIDENCE_A),
        parent_artifact_sha256s=(PARENT_A,),
    )


def test_curiosity_artifact_is_deterministic_and_zero_authority() -> None:
    artifact = build_artifact()
    payload = artifact.to_dict()

    assert artifact.schema_version == CURIOSITY_ARTIFACT_SCHEMA_VERSION
    assert payload["lane"] == "curiosity"
    assert payload["claim_class"] == "non_claim"
    assert payload["tags"] == ["gear", "symbol"]
    assert payload["evidence_ref_sha256s"] == [
        EVIDENCE_A,
        EVIDENCE_B,
    ]
    assert payload["effect_performed"] is False
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert len(payload["curiosity_artifact_sha256"]) == 64

    rebuilt = build_artifact()
    assert rebuilt.curiosity_artifact_sha256 == (
        artifact.curiosity_artifact_sha256
    )
    assert rebuilt.to_dict() == payload


def test_curiosity_artifact_round_trips_exactly() -> None:
    artifact = build_artifact()

    parsed = CuriosityArtifact.from_dict(artifact.to_dict())

    assert parsed == artifact
    assert parsed.curiosity_artifact_sha256 == (
        artifact.curiosity_artifact_sha256
    )


@pytest.mark.parametrize(
    ("kind", "claim_class"),
    [
        ("symbol", "non_claim"),
        ("metaphor", "non_claim"),
        ("dream_fragment", "non_claim"),
        ("creative_seed", "non_claim"),
        ("question", "open_question"),
        ("hypothesis", "hypothesis"),
        ("association", "unverified_association"),
        ("pattern", "unverified_association"),
    ],
)
def test_artifact_kinds_have_explicit_claim_classes(
    kind: str,
    claim_class: str,
) -> None:
    artifact = CuriosityArtifact.build(
        artifact_kind=kind,
        title=f"{kind} example",
        content="Exploratory content.",
        created_at="2026-09-25T15:40:00+00:00",
        created_by="operator:mikey",
    )

    assert artifact.claim_class == claim_class


def test_curiosity_artifact_rejects_unknown_kind() -> None:
    with pytest.raises(CuriosityContractError, match="unsupported"):
        CuriosityArtifact.build(
            artifact_kind="verified_fact",
            title="Nope",
            content="This lane does not mint facts.",
            created_at="2026-09-25T15:40:00+00:00",
            created_by="operator:mikey",
        )


def test_curiosity_artifact_rejects_authority_carrying_payload() -> None:
    payload = build_artifact().to_dict()
    payload["action_authority"] = True

    with pytest.raises(CuriosityContractError, match="cannot carry"):
        CuriosityArtifact.from_dict(payload)


def test_curiosity_artifact_rejects_claimed_effect() -> None:
    payload = build_artifact().to_dict()
    payload["effect_performed"] = True

    with pytest.raises(CuriosityContractError, match="effect was performed"):
        CuriosityArtifact.from_dict(payload)


def test_curiosity_artifact_rejects_lane_tampering() -> None:
    payload = build_artifact().to_dict()
    payload["lane"] = "reality"

    with pytest.raises(CuriosityContractError, match="remain curiosity"):
        CuriosityArtifact.from_dict(payload)


def test_curiosity_artifact_rejects_claim_class_tampering() -> None:
    payload = build_artifact().to_dict()
    payload["claim_class"] = "verified_fact"

    with pytest.raises(CuriosityContractError, match="claim_class"):
        CuriosityArtifact.from_dict(payload)


def test_curiosity_artifact_rejects_digest_tampering() -> None:
    payload = build_artifact().to_dict()
    payload["content"] = "Changed after sealing."

    with pytest.raises(CuriosityContractError, match="canonical artifact"):
        CuriosityArtifact.from_dict(payload)


def test_curiosity_artifact_requires_timezone_aware_time() -> None:
    with pytest.raises(CuriosityContractError, match="timezone"):
        CuriosityArtifact.build(
            artifact_kind="question",
            title="Question",
            content="What if?",
            created_at="2026-09-25T15:40:00",
            created_by="operator:mikey",
        )


def build_promotion() -> CuriosityPromotionRequest:
    artifact = build_artifact()
    return CuriosityPromotionRequest.build(
        artifact_sha256=artifact.curiosity_artifact_sha256,
        target_lane="research",
        requested_at="2026-09-25T15:45:00+00:00",
        requested_by="operator:mikey",
        rationale=(
            "Turn the symbolic model into a falsifiable research question."
        ),
        evidence_ref_sha256s=(EVIDENCE_B, EVIDENCE_A),
    )


def test_promotion_request_is_proposal_only_and_zero_authority() -> None:
    request = build_promotion()
    payload = request.to_dict()

    assert request.schema_version == CURIOSITY_PROMOTION_SCHEMA_VERSION
    assert payload["target_lane"] == "research"
    assert payload["request_status"] == "proposal_only"
    assert payload["effect_performed"] is False
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert len(payload["promotion_request_sha256"]) == 64


def test_promotion_request_round_trips_exactly() -> None:
    request = build_promotion()

    parsed = CuriosityPromotionRequest.from_dict(request.to_dict())

    assert parsed == request
    assert parsed.promotion_request_sha256 == (
        request.promotion_request_sha256
    )


@pytest.mark.parametrize("target", ["research", "build", "ledger_review"])
def test_explicit_supported_promotion_targets(target: str) -> None:
    artifact = build_artifact()
    request = CuriosityPromotionRequest.build(
        artifact_sha256=artifact.curiosity_artifact_sha256,
        target_lane=target,
        requested_at="2026-09-25T15:45:00+00:00",
        requested_by="operator:mikey",
        rationale="Explicit handoff for destination-lane evaluation.",
    )

    assert request.target_lane == target


def test_promotion_request_rejects_direct_action_target() -> None:
    artifact = build_artifact()

    with pytest.raises(CuriosityContractError, match="unsupported"):
        CuriosityPromotionRequest.build(
            artifact_sha256=artifact.curiosity_artifact_sha256,
            target_lane="execute",
            requested_at="2026-09-25T15:45:00+00:00",
            requested_by="operator:mikey",
            rationale="Curiosity cannot jump directly to execution.",
        )


def test_promotion_request_rejects_authority_tampering() -> None:
    payload = copy.deepcopy(build_promotion().to_dict())
    payload["execution_authority"] = True

    with pytest.raises(CuriosityContractError, match="cannot carry"):
        CuriosityPromotionRequest.from_dict(payload)


def test_promotion_request_rejects_status_tampering() -> None:
    payload = build_promotion().to_dict()
    payload["request_status"] = "approved"

    with pytest.raises(CuriosityContractError, match="proposal_only"):
        CuriosityPromotionRequest.from_dict(payload)


def test_promotion_request_rejects_digest_tampering() -> None:
    payload = build_promotion().to_dict()
    payload["rationale"] = "Altered after sealing."

    with pytest.raises(CuriosityContractError, match="canonical request"):
        CuriosityPromotionRequest.from_dict(payload)
