from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from phios.reflex.authority import (
    PURPOSE_ACTIVATION_GRANT,
    PURPOSE_GRANT_REVOCATION,
    ReflexAuthorityContractError,
    ReflexAuthorityPlane,
    activation_grant_signature_payload,
    build_grant_revocation,
    build_signed_activation_grant_envelope,
    build_trust_anchor,
    canonical_authority_bytes,
    grant_revocation_signature_payload,
)
from phios.reflex.control_plane import ReflexRuntimeControlPlane
from phios.reflex.influence_adoption import ReflexInfluencePolicyState
from phios.reflex.runtime_influence import (
    ROUTING_SURFACE,
    ReflexActivationGrant,
    ReflexActivationRequest,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _policy() -> ReflexInfluencePolicyState:
    payload = {
        "schema": "phios.reflex_influence_policy_state.v0.5",
        "policy_id": "phios.reflex.influence.jev",
        "revision": 0,
        "readiness_receipt_sha256": "a" * 64,
        "candidate_provider": "jev",
        "candidate_models": ["jev-test"],
        "allowed_dimensions": ["role", "system2"],
        "max_influence_weight": 0.20,
        "rollback_on_provider_unavailable": True,
        "max_consecutive_provider_errors": 2,
        "parent_policy_sha256": None,
        "routing_influence_active": False,
        "runtime_activation_authority": False,
        "promotion_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    return ReflexInfluencePolicyState(
        schema="phios.reflex_influence_policy_state.v0.5",
        policy_id="phios.reflex.influence.jev",
        revision=0,
        readiness_receipt_sha256="a" * 64,
        candidate_provider="jev",
        candidate_models=("jev-test",),
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=2,
        parent_policy_sha256=None,
        routing_influence_active=False,
        runtime_activation_authority=False,
        promotion_authority=False,
        action_authority=False,
        execution_authority=False,
        state_sha256=_digest(payload),
    )


def _request() -> ReflexActivationRequest:
    return ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role", "system2"),
        influence_weight=0.20,
    )


def _key_material():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, base64.b64encode(public).decode("ascii")


def _grant(
    policy: ReflexInfluencePolicyState,
    request: ReflexActivationRequest,
    *,
    authority_source: str = "operator",
):
    return ReflexActivationGrant(
        grant_id="grant-001",
        authority_source=authority_source,
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )


def _signed_envelope(
    private: Ed25519PrivateKey,
    grant: ReflexActivationGrant,
    *,
    issuer_id: str = "operator",
    key_id: str = "key-1",
    issued: int = 100,
    valid_from: int = 100,
    valid_until: int | None = 500,
):
    payload = activation_grant_signature_payload(
        issuer_id=issuer_id,
        key_id=key_id,
        issued_at_epoch=issued,
        valid_from_epoch=valid_from,
        valid_until_epoch=valid_until,
        grant=grant,
    )
    signature = private.sign(canonical_authority_bytes(payload))
    return build_signed_activation_grant_envelope(
        issuer_id=issuer_id,
        key_id=key_id,
        issued_at_epoch=issued,
        valid_from_epoch=valid_from,
        valid_until_epoch=valid_until,
        grant=grant,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )


def _setup(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    authority = ReflexAuthorityPlane(control=control)
    policy = _policy()
    request = _request()
    private, public_b64 = _key_material()
    anchor = build_trust_anchor(
        issuer_id="operator",
        key_id="key-1",
        public_key_b64=public_b64,
        allowed_purposes=(
            PURPOSE_ACTIVATION_GRANT,
            PURPOSE_GRANT_REVOCATION,
        ),
    )
    control.ingest_policy_payload(policy.to_dict(), evaluation_epoch=100)
    authority.ingest_trust_anchor(
        anchor.to_dict(),
        evaluation_epoch=100,
    )
    grant = _grant(policy, request)
    envelope = _signed_envelope(private, grant)
    return control, authority, policy, request, private, grant, envelope


def test_authenticated_grant_can_activate_and_survive_authority_status(tmp_path):
    _, authority, _, request, _, grant, envelope = _setup(tmp_path)

    ingested = authority.ingest_signed_grant(
        envelope.to_dict(),
        evaluation_epoch=110,
    )
    assert ingested["receipt"]["authenticated"] is True

    activated = authority.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        evaluation_epoch=120,
    )
    assert activated["ok"] is True
    assert activated["activation"]["routing_influence_active"] is True

    status = authority.status(evaluation_epoch=130)
    assert status["routing_influence_active"] is True
    assert len(status["control_sha256"]) == 64


def test_forged_signature_is_rejected(tmp_path):
    _, authority, _, _, _, _, envelope = _setup(tmp_path)
    other_private, _ = _key_material()
    forged_payload = envelope.signing_payload()
    forged = build_signed_activation_grant_envelope(
        issuer_id=envelope.issuer_id,
        key_id=envelope.key_id,
        issued_at_epoch=envelope.issued_at_epoch,
        valid_from_epoch=envelope.valid_from_epoch,
        valid_until_epoch=envelope.valid_until_epoch,
        grant=envelope.grant,
        signature_b64=base64.b64encode(
            other_private.sign(canonical_authority_bytes(forged_payload))
        ).decode("ascii"),
    )

    with pytest.raises(ReflexAuthorityContractError):
        authority.ingest_signed_grant(
            forged.to_dict(),
            evaluation_epoch=110,
        )


def test_signed_grant_must_bind_authenticated_issuer_to_authority_source(
    tmp_path,
):
    _, authority, policy, request, private, _, _ = _setup(tmp_path)
    grant = _grant(policy, request, authority_source="someone-else")
    envelope = _signed_envelope(private, grant)

    with pytest.raises(ReflexAuthorityContractError):
        authority.ingest_signed_grant(
            envelope.to_dict(),
            evaluation_epoch=110,
        )


def test_expired_signed_grant_cannot_activate(tmp_path):
    _, authority, _, request, private, grant, _ = _setup(tmp_path)
    envelope = _signed_envelope(
        private,
        grant,
        valid_until=150,
    )
    authority.ingest_signed_grant(
        envelope.to_dict(),
        evaluation_epoch=120,
    )

    with pytest.raises(ReflexAuthorityContractError):
        authority.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            evaluation_epoch=150,
        )


def test_effective_authenticated_revocation_collapses_live_influence(tmp_path):
    _, authority, _, request, private, grant, envelope = _setup(tmp_path)
    authority.ingest_signed_grant(
        envelope.to_dict(),
        evaluation_epoch=110,
    )
    authority.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        evaluation_epoch=120,
    )

    payload = grant_revocation_signature_payload(
        revocation_id="revoke-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        effective_epoch=130,
        reason="operator revoked",
    )
    signature = private.sign(canonical_authority_bytes(payload))
    revocation = build_grant_revocation(
        revocation_id="revoke-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        effective_epoch=130,
        reason="operator revoked",
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )
    result = authority.ingest_revocation(
        revocation.to_dict(),
        evaluation_epoch=130,
    )

    assert result["collapse"] is not None
    assert (
        result["collapse"]["activation"]["routing_influence_active"]
        is False
    )
    assert authority.status(evaluation_epoch=131)[
        "routing_influence_active"
    ] is False


def test_future_revocation_collapses_when_it_becomes_effective(tmp_path):
    _, authority, _, request, private, grant, envelope = _setup(tmp_path)
    authority.ingest_signed_grant(
        envelope.to_dict(),
        evaluation_epoch=110,
    )
    authority.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        evaluation_epoch=120,
    )

    payload = grant_revocation_signature_payload(
        revocation_id="revoke-future",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        effective_epoch=200,
        reason="scheduled revoke",
    )
    revocation = build_grant_revocation(
        revocation_id="revoke-future",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        effective_epoch=200,
        reason="scheduled revoke",
        signature_b64=base64.b64encode(
            private.sign(canonical_authority_bytes(payload))
        ).decode("ascii"),
    )
    authority.ingest_revocation(
        revocation.to_dict(),
        evaluation_epoch=130,
    )

    assert authority.status(evaluation_epoch=199)[
        "routing_influence_active"
    ] is True
    assert authority.status(evaluation_epoch=200)[
        "routing_influence_active"
    ] is False


def test_unsigned_legacy_activation_is_collapsed_by_v08_enforcement(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    authority = ReflexAuthorityPlane(control=control)
    policy = _policy()
    request = _request()
    grant = _grant(policy, request)

    control.ingest_policy_payload(policy.to_dict(), evaluation_epoch=100)
    control.ingest_grant_payload(grant.to_payload(), evaluation_epoch=100)
    legacy = control.activate(
        request=request,
        grant_id=grant.grant_id,
        evaluation_epoch=110,
    )
    assert legacy["activation"]["routing_influence_active"] is True

    status = authority.status(evaluation_epoch=120)
    assert status["routing_influence_active"] is False
    assert status["authenticated_authority_enforcement"] is not None


def test_stale_control_fingerprint_rejects_privilege_path_mutation(tmp_path):
    _, authority, _, _, _, _, envelope = _setup(tmp_path)
    snapshot = authority.status(evaluation_epoch=105)["control_sha256"]

    authority.ingest_signed_grant(
        envelope.to_dict(),
        evaluation_epoch=110,
        expected_control_sha256=snapshot,
    )

    with pytest.raises(ReflexAuthorityContractError):
        authority.ingest_signed_grant(
            envelope.to_dict(),
            evaluation_epoch=111,
            expected_control_sha256=snapshot,
        )


def test_trust_anchor_conflict_is_rejected(tmp_path):
    _, authority, _, _, _, _, _ = _setup(tmp_path)
    _, different_public = _key_material()
    conflicting = build_trust_anchor(
        issuer_id="operator",
        key_id="key-1",
        public_key_b64=different_public,
    )

    with pytest.raises(ReflexAuthorityContractError):
        authority.ingest_trust_anchor(
            conflicting.to_dict(),
            evaluation_epoch=110,
        )


def test_corrupt_authenticated_envelope_collapses_persisted_live_state(
    tmp_path,
):
    control, authority, _, request, _, grant, envelope = _setup(tmp_path)
    authority.ingest_signed_grant(
        envelope.to_dict(),
        evaluation_epoch=110,
    )
    authority.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        evaluation_epoch=120,
    )
    envelope_path = (
        authority.signed_grants_dir / f"{grant.grant_id}.json"
    )
    envelope_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ReflexAuthorityContractError):
        authority.status(evaluation_epoch=130)

    control_status = control.status(evaluation_epoch=131)
    assert control_status["routing_influence_active"] is False
