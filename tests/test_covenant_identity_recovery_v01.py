from dataclasses import replace

import pytest

from phios.covenant import (
    EpochBoundIdentity,
    FunctionalEquivalenceStatus,
    IdentityInvariantField,
    IdentityInvariantSet,
    IdentitySeal,
    IdentitySubjectKind,
    RecoveryEvaluator,
    RecoveryStatus,
    evaluate_functional_equivalence,
)


def _seal(
    *,
    implementation: str = "1",
    manifest: str = "2",
    source: str = "3",
    issuer_id: str = "phios.local",
    issuer_key_id: str = "operator-root-1",
) -> IdentitySeal:
    return IdentitySeal(
        subject_id="phi.agent.builder",
        subject_kind=IdentitySubjectKind.AGENT,
        implementation_sha256=implementation * 64,
        manifest_sha256=manifest * 64,
        source_sha256=source * 64,
        issuer_id=issuer_id,
        issuer_key_id=issuer_key_id,
    )


def _epoch0(
    seal: IdentitySeal,
    invariants: IdentityInvariantSet,
    *,
    topology: str = "a",
    state: str = "b",
) -> EpochBoundIdentity:
    return EpochBoundIdentity(
        subject_id=seal.subject_id,
        subject_kind=seal.subject_kind,
        epoch=0,
        identity_seal_sha256=seal.sha256(),
        invariant_set_sha256=invariants.sha256(),
        topology_sha256=topology * 64,
        recovery_state_sha256=state * 64,
    )


def _recovered(
    previous: EpochBoundIdentity,
    seal: IdentitySeal,
    invariants: IdentityInvariantSet,
    *,
    epoch: int = 1,
    topology: str = "c",
    state: str = "b",
    checkpoint: str = "d",
    previous_sha: str | None = None,
) -> EpochBoundIdentity:
    return EpochBoundIdentity(
        subject_id=seal.subject_id,
        subject_kind=seal.subject_kind,
        epoch=epoch,
        identity_seal_sha256=seal.sha256(),
        invariant_set_sha256=invariants.sha256(),
        topology_sha256=topology * 64,
        recovery_state_sha256=state * 64,
        previous_epoch_identity_sha256=previous_sha or previous.sha256(),
        recovery_checkpoint_sha256=checkpoint * 64,
    )


def test_strict_invariant_set_covers_cr01_identity_fields() -> None:
    invariants = IdentityInvariantSet.strict_cr01()

    assert set(invariants.required_fields) == set(IdentityInvariantField)
    assert IdentityInvariantField.SUBJECT_ID in invariants.required_fields
    assert IdentityInvariantField.SUBJECT_KIND in invariants.required_fields
    assert invariants.topology_is_identity_evidence is False
    assert invariants.action_authority is False
    assert invariants.execution_authority is False


def test_topology_change_can_preserve_identity_when_invariants_and_state_match() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants, topology="a", state="b")
    recovered = _recovered(
        previous,
        seal,
        invariants,
        topology="c",
        state="b",
        checkpoint="d",
    )

    equivalence, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    assert equivalence.status is FunctionalEquivalenceStatus.EQUIVALENT
    assert equivalence.topology_evidence_used is False
    assert receipt.status is RecoveryStatus.RECOVERED
    assert receipt.topology_changed is True
    assert receipt.epoch_advanced is True
    assert receipt.identity_equivalent is True
    assert receipt.state_recovered_exactly is True
    assert receipt.authority_inherited is False
    assert receipt.authority_revalidation_required is True
    assert receipt.trusted_identity is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False


def test_same_topology_cannot_launder_changed_implementation_identity() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    previous_seal = _seal(implementation="1")
    recovered_seal = _seal(implementation="9")
    previous = _epoch0(previous_seal, invariants, topology="a", state="b")
    recovered = _recovered(
        previous,
        recovered_seal,
        invariants,
        topology="a",
        state="b",
    )

    equivalence, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=previous_seal,
        recovered_seal=recovered_seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    assert equivalence.status is FunctionalEquivalenceStatus.CHANGED
    assert "implementation_sha256" in equivalence.mismatched_fields
    assert receipt.status is RecoveryStatus.BLOCKED
    assert receipt.topology_changed is False
    assert receipt.reason == "identity_invariants_changed"


def test_changed_recovery_state_blocks_identity_continuity() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants, state="b")
    recovered = _recovered(previous, seal, invariants, state="e")

    _, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    assert receipt.status is RecoveryStatus.BLOCKED
    assert receipt.identity_equivalent is True
    assert receipt.state_recovered_exactly is False
    assert receipt.reason == "recovery_state_digest_changed"


def test_skipped_epoch_blocks_recovery() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants)
    recovered = _recovered(previous, seal, invariants, epoch=2)

    _, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    assert receipt.status is RecoveryStatus.BLOCKED
    assert receipt.epoch_advanced is False
    assert receipt.reason == "recovery_epoch_not_exactly_next"


def test_broken_epoch_hash_chain_blocks_recovery() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants)
    recovered = _recovered(
        previous,
        seal,
        invariants,
        previous_sha="f" * 64,
    )

    _, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    assert receipt.status is RecoveryStatus.BLOCKED
    assert receipt.reason == "recovery_epoch_chain_mismatch"


def test_checkpoint_mismatch_blocks_recovery() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants)
    recovered = _recovered(previous, seal, invariants, checkpoint="d")

    _, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="e" * 64,
    )

    assert receipt.status is RecoveryStatus.BLOCKED
    assert receipt.reason == "recovery_checkpoint_mismatch"


def test_issuer_change_is_identity_change_under_strict_policy() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    previous = _seal(issuer_id="phios.local")
    candidate = _seal(issuer_id="other.issuer")

    receipt = evaluate_functional_equivalence(
        previous,
        candidate,
        invariants,
    )

    assert receipt.status is FunctionalEquivalenceStatus.CHANGED
    assert receipt.mismatched_fields == ("issuer_id",)
    assert receipt.trusted_identity is False


def test_identity_policy_cannot_use_topology_as_identity_evidence() -> None:
    fields = tuple(
        sorted(
            (
                IdentityInvariantField.SUBJECT_ID,
                IdentityInvariantField.SUBJECT_KIND,
            ),
            key=lambda item: item.value,
        )
    )

    with pytest.raises(ValueError, match="topology cannot"):
        IdentityInvariantSet(
            invariant_set_id="bad-topology-policy",
            version="0.1",
            required_fields=fields,
            topology_is_identity_evidence=True,
        )


def test_epoch_zero_cannot_claim_recovery_ancestry() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()

    with pytest.raises(ValueError, match="epoch 0"):
        EpochBoundIdentity(
            subject_id=seal.subject_id,
            subject_kind=seal.subject_kind,
            epoch=0,
            identity_seal_sha256=seal.sha256(),
            invariant_set_sha256=invariants.sha256(),
            topology_sha256="a" * 64,
            recovery_state_sha256="b" * 64,
            previous_epoch_identity_sha256="c" * 64,
            recovery_checkpoint_sha256="d" * 64,
        )


def test_recovery_receipt_cannot_be_upgraded_into_authority() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants)
    recovered = _recovered(previous, seal, invariants)
    _, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    with pytest.raises(ValueError, match="cannot inherit authority"):
        replace(receipt, authority_inherited=True)

    with pytest.raises(ValueError, match="require downstream authority revalidation"):
        replace(receipt, authority_revalidation_required=False)

    with pytest.raises(ValueError, match="cannot carry authority"):
        replace(receipt, action_authority=True)


def test_invariant_set_round_trip_is_strict() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    assert IdentityInvariantSet.from_dict(invariants.to_dict()) == invariants

    payload = invariants.to_dict()
    payload["topology_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="unknown=topology_sha256"):
        IdentityInvariantSet.from_dict(payload)


def test_equivalence_epoch_and_recovery_round_trip_strict() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants)
    recovered = _recovered(previous, seal, invariants)
    equivalence, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )

    assert type(equivalence).from_dict(equivalence.to_dict()) == equivalence
    assert EpochBoundIdentity.from_dict(previous.to_dict()) == previous
    assert EpochBoundIdentity.from_dict(recovered.to_dict()) == recovered
    assert type(receipt).from_dict(receipt.to_dict()) == receipt


def test_recovery_receipt_digest_tampering_fails_closed() -> None:
    invariants = IdentityInvariantSet.strict_cr01()
    seal = _seal()
    previous = _epoch0(seal, invariants)
    recovered = _recovered(previous, seal, invariants)
    _, receipt = RecoveryEvaluator(invariants).assess(
        previous_identity=previous,
        recovered_identity=recovered,
        previous_seal=seal,
        recovered_seal=seal,
        recovery_checkpoint_sha256="d" * 64,
    )
    payload = receipt.to_dict()
    payload["recovered_state_sha256"] = "e" * 64

    with pytest.raises(ValueError):
        type(receipt).from_dict(payload)
