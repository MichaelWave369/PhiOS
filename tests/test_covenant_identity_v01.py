from __future__ import annotations

import copy

import pytest

from phios.covenant.identity import IdentitySeal, IdentitySubjectKind


def _seal() -> IdentitySeal:
    return IdentitySeal(
        subject_id="phi.agent.builder",
        subject_kind=IdentitySubjectKind.AGENT,
        implementation_sha256="1" * 64,
        manifest_sha256="2" * 64,
        source_sha256="3" * 64,
        issuer_id="phios.local",
        issuer_key_id="operator-root-1",
    )


def test_identity_seal_canonical_hash_is_deterministic() -> None:
    first = _seal()
    second = _seal()

    assert first.sha256() == second.sha256()
    assert first.to_dict() == second.to_dict()
    assert first.trusted_identity is False
    assert first.action_authority is False
    assert first.execution_authority is False


def test_identity_seal_round_trip_is_strict() -> None:
    seal = _seal()

    assert IdentitySeal.from_dict(seal.to_dict()) == seal


def test_identity_seal_tampering_rejects_original_digest() -> None:
    seal = _seal()
    payload = copy.deepcopy(seal.to_dict())
    payload["source_sha256"] = "4" * 64

    with pytest.raises(ValueError, match="digest does not match"):
        IdentitySeal.from_dict(payload)


def test_identity_seal_unknown_fields_fail_closed() -> None:
    payload = _seal().to_dict()
    payload["authority_source"] = "memory:retrieved-text"

    with pytest.raises(ValueError, match="unknown=authority_source"):
        IdentitySeal.from_dict(payload)


def test_identity_seal_cannot_assert_trust_or_authority() -> None:
    base = _seal()

    with pytest.raises(ValueError, match="does not establish trusted identity"):
        IdentitySeal(
            subject_id=base.subject_id,
            subject_kind=base.subject_kind,
            implementation_sha256=base.implementation_sha256,
            manifest_sha256=base.manifest_sha256,
            source_sha256=base.source_sha256,
            issuer_id=base.issuer_id,
            issuer_key_id=base.issuer_key_id,
            trusted_identity=True,
        )

    with pytest.raises(ValueError, match="cannot carry action or execution authority"):
        IdentitySeal(
            subject_id=base.subject_id,
            subject_kind=base.subject_kind,
            implementation_sha256=base.implementation_sha256,
            manifest_sha256=base.manifest_sha256,
            source_sha256=base.source_sha256,
            issuer_id=base.issuer_id,
            issuer_key_id=base.issuer_key_id,
            action_authority=True,
        )


def test_identity_seal_rejects_unknown_subject_kind() -> None:
    payload = _seal().to_dict()
    payload["subject_kind"] = "deity"

    with pytest.raises(ValueError, match="Unsupported identity subject kind"):
        IdentitySeal.from_dict(payload)
