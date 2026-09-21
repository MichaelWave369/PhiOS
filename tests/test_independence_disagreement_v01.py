import hashlib
from pathlib import Path

import pytest

from phios.mandala import (
    AuthorityContext,
    DeliberationEvidenceAssessor,
    EvidencePathDeclaration,
    Gate,
    IndependenceAssertion,
    IndependenceContractError,
    MandalaPacket,
    OriginKind,
    OriginRef,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _packet() -> MandalaPacket:
    return MandalaPacket.create(
        task_id="independence-task",
        gate=Gate.DELIBERATION,
        origin=OriginRef(kind=OriginKind.SUBSYSTEM, identifier="genius-atlas"),
        payload={"claim_id": "claim-1"},
        authority=AuthorityContext(),
        claims=({"kind": "deliberation_evidence_assessment"},),
        allowed_destinations=(Gate.MEMORY,),
    )


def _path(
    path_id: str,
    *,
    actor: str,
    stance: str = "SUPPORTS",
    root: str | None = None,
    evidence: str | None = None,
    parents: tuple[str, ...] = (),
    context: str = "shared-prompt",
) -> EvidencePathDeclaration:
    return EvidencePathDeclaration(
        path_id=path_id,
        claim_id="claim-1",
        actor_id=actor,
        stance=stance,
        output_sha256=_sha(f"output:{path_id}"),
        evidence_refs=((evidence or f"evidence:{path_id}"),),
        root_source_refs=((root or f"root:{path_id}"),),
        parent_path_ids=parents,
        context_sha256=_sha(context),
        method="model_with_evidence",
    )


def _independent(left: str, right: str) -> IndependenceAssertion:
    return IndependenceAssertion(
        left_path_id=left,
        right_path_id=right,
        relation="INDEPENDENT",
        basis_refs=(f"attestation:{min(left, right)}:{max(left, right)}",),
        reason="separate_acquisition_paths",
    )


def test_three_agents_on_same_source_count_as_one_demonstrated_group() -> None:
    paths = (
        _path("a", actor="model-a", root="root:shared", evidence="evidence:shared"),
        _path("b", actor="model-b", root="root:shared", evidence="evidence:shared"),
        _path("c", actor="model-c", root="root:shared", evidence="evidence:shared"),
    )

    result = DeliberationEvidenceAssessor().assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=paths,
    )

    independence = result.independence_receipt
    disagreement = result.disagreement_receipt
    assert independence.independence_status == "DEPENDENT"
    assert independence.dependent_pair_count == 3
    assert independence.demonstrated_independent_group_count == 1
    assert independence.agreement_without_independence is True
    assert disagreement.disagreement_status == "UNANIMOUS_PARTICIPANTS"
    assert disagreement.independence_qualified_agreement is False
    assert disagreement.consensus_authority is False


def test_three_explicitly_independent_paths_can_earn_three_groups() -> None:
    paths = (
        _path("a", actor="sensor-a"),
        _path("b", actor="sensor-b"),
        _path("c", actor="sensor-c"),
    )
    assertions = (
        _independent("a", "b"),
        _independent("a", "c"),
        _independent("b", "c"),
    )

    result = DeliberationEvidenceAssessor().assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=paths,
        assertions=assertions,
    )

    independence = result.independence_receipt
    disagreement = result.disagreement_receipt
    assert independence.independence_status == "INDEPENDENT"
    assert independence.independent_pair_count == 3
    assert independence.demonstrated_independent_group_count == 3
    assert all(
        pair["shared_context"] is True
        for pair in independence.pairwise_relations
    )
    assert independence.agreement_without_independence is False
    assert disagreement.independence_qualified_agreement is True
    assert disagreement.independent_stance_group_counts["SUPPORTS"] == 3
    assert disagreement.operational_authority is False
    assert disagreement.action_authority is False
    assert disagreement.execution_authority is False


def test_unknown_relationship_does_not_earn_independence_credit() -> None:
    paths = (
        _path("a", actor="model-a"),
        _path("b", actor="model-b"),
    )

    result = DeliberationEvidenceAssessor().assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=paths,
    )

    receipt = result.independence_receipt
    assert receipt.independence_status == "UNRESOLVED"
    assert receipt.unknown_pair_count == 1
    assert receipt.demonstrated_independent_group_count == 1
    assert receipt.status.value == "DEGRADED"


def test_shared_source_cannot_be_laundered_by_independent_assertion() -> None:
    paths = (
        _path("a", actor="model-a", root="root:shared"),
        _path("b", actor="model-b", root="root:shared"),
    )

    with pytest.raises(IndependenceContractError, match="cannot be asserted"):
        DeliberationEvidenceAssessor().assess(
            packet=_packet(),
            claim_id="claim-1",
            paths=paths,
            assertions=(_independent("a", "b"),),
        )


def test_independent_assertion_requires_explicit_basis() -> None:
    paths = (
        _path("a", actor="model-a"),
        _path("b", actor="model-b"),
    )
    assertion = IndependenceAssertion(
        left_path_id="a",
        right_path_id="b",
        relation="INDEPENDENT",
    )

    with pytest.raises(IndependenceContractError, match="basis_refs"):
        DeliberationEvidenceAssessor().assess(
            packet=_packet(),
            claim_id="claim-1",
            paths=paths,
            assertions=(assertion,),
        )


def test_disagreement_is_preserved_instead_of_collapsed_to_vote() -> None:
    paths = (
        _path("a", actor="sensor-a", stance="SUPPORTS"),
        _path("b", actor="sensor-b", stance="CONTRADICTS"),
        _path("c", actor="sensor-c", stance="UNCERTAIN"),
    )
    assertions = (
        _independent("a", "b"),
        _independent("a", "c"),
        _independent("b", "c"),
    )

    result = DeliberationEvidenceAssessor().assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=paths,
        assertions=assertions,
    )

    receipt = result.disagreement_receipt
    assert receipt.disagreement_status == "DISAGREEMENT"
    assert receipt.stance_counts == {
        "SUPPORTS": 1,
        "CONTRADICTS": 1,
        "UNCERTAIN": 1,
    }
    assert receipt.independent_stance_group_counts == {
        "SUPPORTS": 1,
        "CONTRADICTS": 1,
        "UNCERTAIN": 1,
    }
    assert receipt.promotion_status == "not_promoted"
    assert receipt.consensus_authority is False


def test_direct_derivation_forces_dependency() -> None:
    paths = (
        _path("a", actor="model-a"),
        _path("b", actor="model-b", parents=("a",)),
    )

    result = DeliberationEvidenceAssessor().assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=paths,
    )

    pair = result.independence_receipt.pairwise_relations[0]
    assert pair["relation"] == "DEPENDENT"
    assert "direct_path_derivation" in pair["reasons"]


def test_assessor_persists_parent_linked_zero_authority_receipts(
    tmp_path: Path,
) -> None:
    from phios.mandala import MandalaReceiptLedger

    ledger = MandalaReceiptLedger(tmp_path / "mandala.jsonl")
    result = DeliberationEvidenceAssessor(ledger).assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=(_path("a", actor="model-a"),),
    )

    rows = ledger.recent(2)
    assert [row["receipt_type"] for row in rows] == [
        "IndependenceReceipt",
        "DisagreementDecompositionReceipt",
    ]
    assert rows[1]["parent_receipt_id"] == rows[0]["receipt_id"]
    assert rows[0]["action_authority"] is False
    assert rows[1]["consensus_authority"] is False
    assert result.disagreement_receipt.independence_receipt_sha256 == (
        result.independence_receipt.receipt_sha256
    )


def test_spine_exposes_deliberation_assessment_without_authority_gain(
    tmp_path: Path,
) -> None:
    from phios.spine.runtime import PhiOSSpine

    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("artifact.write",),
        task_id="spine-deliberation",
    )
    authority_before = spine.core.authority
    result = spine.assess_deliberation_evidence(
        claim_id="claim-1",
        paths=(
            _path("a", actor="model-a"),
            _path("b", actor="model-b"),
        ),
        assertions=(_independent("a", "b"),),
    )

    assert spine.core.authority == authority_before
    assert result.independence_receipt.action_authority is False
    assert result.disagreement_receipt.execution_authority is False
    rows = spine.mandala_ledger.recent(2)
    assert rows[0]["receipt_type"] == "IndependenceReceipt"
    assert rows[1]["receipt_type"] == "DisagreementDecompositionReceipt"


def test_cyclic_path_ancestry_is_rejected() -> None:
    paths = (
        _path("a", actor="model-a", parents=("b",)),
        _path("b", actor="model-b", parents=("a",)),
    )

    with pytest.raises(IndependenceContractError, match="acyclic"):
        DeliberationEvidenceAssessor().assess(
            packet=_packet(),
            claim_id="claim-1",
            paths=paths,
        )


def test_same_actor_does_not_receive_independence_credit_from_repeat_runs() -> None:
    paths = (
        _path("a", actor="model-a", root="root:first"),
        _path("b", actor="model-a", root="root:second"),
    )

    result = DeliberationEvidenceAssessor().assess(
        packet=_packet(),
        claim_id="claim-1",
        paths=paths,
    )

    pair = result.independence_receipt.pairwise_relations[0]
    assert pair["relation"] == "DEPENDENT"
    assert "same_actor" in pair["reasons"]
    assert result.independence_receipt.demonstrated_independent_group_count == 1
