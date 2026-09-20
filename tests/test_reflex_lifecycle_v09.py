from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phios.reflex.authority import (
    ReflexAuthorityPlane,
    activation_grant_signature_payload,
    build_signed_activation_grant_envelope,
    build_trust_anchor,
    canonical_authority_bytes,
)
from phios.reflex.control_plane import ReflexRuntimeControlPlane
from phios.reflex.influence_adoption import ReflexInfluencePolicyState
from phios.reflex.lifecycle import (
    ReflexLifecycleContractError,
    ReflexTrustLifecyclePlane,
    build_grant_use_policy,
    build_lease_renewal,
    build_ledger_checkpoint,
    build_provider_manifest,
    build_trust_transition,
    grant_use_policy_signature_payload,
    lease_renewal_signature_payload,
    ledger_checkpoint_signature_payload,
    provider_manifest_signature_payload,
    trust_transition_signature_payload,
)
from phios.reflex.runtime_influence import (
    ROUTING_SURFACE,
    ReflexActivationGrant,
    ReflexActivationRequest,
)


ADAPTER_ID = "phios.reflex.providers.jev:JevReflexProvider"
ADAPTER_VERSION = "0.9"


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


def _key():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, base64.b64encode(public).decode("ascii")


def _sign(private: Ed25519PrivateKey, payload: object) -> str:
    return base64.b64encode(
        private.sign(canonical_authority_bytes(payload))
    ).decode("ascii")


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


def _setup(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    authority = ReflexAuthorityPlane(control=control)
    lifecycle = ReflexTrustLifecyclePlane(
        control=control,
        authority=authority,
    )
    policy = _policy()
    request = _request()
    private, public_b64 = _key()
    anchor = build_trust_anchor(
        issuer_id="operator",
        key_id="key-1",
        public_key_b64=public_b64,
    )
    control.ingest_policy_payload(policy.to_dict(), evaluation_epoch=100)
    authority.ingest_trust_anchor(anchor.to_dict(), evaluation_epoch=100)

    grant = ReflexActivationGrant(
        grant_id="grant-001",
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )
    grant_payload = activation_grant_signature_payload(
        issuer_id="operator",
        key_id="key-1",
        issued_at_epoch=100,
        valid_from_epoch=100,
        valid_until_epoch=900,
        grant=grant,
    )
    envelope = build_signed_activation_grant_envelope(
        issuer_id="operator",
        key_id="key-1",
        issued_at_epoch=100,
        valid_from_epoch=100,
        valid_until_epoch=900,
        grant=grant,
        signature_b64=_sign(private, grant_payload),
    )
    authority.ingest_signed_grant(envelope.to_dict(), evaluation_epoch=110)
    return (
        control,
        authority,
        lifecycle,
        policy,
        request,
        private,
        anchor,
        grant,
        envelope,
    )


def _ingest_use_policy(
    lifecycle: ReflexTrustLifecyclePlane,
    private: Ed25519PrivateKey,
    grant_sha: str,
    *,
    max_activations: int = 1,
    epoch: int = 120,
):
    payload = grant_use_policy_signature_payload(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant_sha,
        max_activations=max_activations,
        issued_at_epoch=epoch,
        effective_epoch=epoch,
    )
    policy = build_grant_use_policy(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant_sha,
        max_activations=max_activations,
        issued_at_epoch=epoch,
        effective_epoch=epoch,
        signature_b64=_sign(private, payload),
    )
    return lifecycle.ingest_grant_use_policy(
        policy.to_dict(),
        evaluation_epoch=epoch,
    )


def _ingest_manifest(
    lifecycle: ReflexTrustLifecyclePlane,
    private: Ed25519PrivateKey,
    *,
    epoch: int = 120,
    valid_until: int | None = 800,
):
    payload = provider_manifest_signature_payload(
        manifest_id="jev-runtime-001",
        issuer_id="operator",
        key_id="key-1",
        provider="jev",
        models=("jev-test",),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        issued_at_epoch=epoch,
        effective_epoch=epoch,
        valid_until_epoch=valid_until,
    )
    manifest = build_provider_manifest(
        manifest_id="jev-runtime-001",
        issuer_id="operator",
        key_id="key-1",
        provider="jev",
        models=("jev-test",),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        issued_at_epoch=epoch,
        effective_epoch=epoch,
        valid_until_epoch=valid_until,
        signature_b64=_sign(private, payload),
    )
    return lifecycle.ingest_provider_manifest(
        manifest.to_dict(),
        evaluation_epoch=epoch,
    )


def _ready(tmp_path):
    values = _setup(tmp_path)
    (
        _,
        _,
        lifecycle,
        _,
        _,
        private,
        _,
        grant,
        _,
    ) = values
    _ingest_use_policy(lifecycle, private, grant.grant_sha256)
    _ingest_manifest(lifecycle, private)
    return values


def test_v09_activation_requires_authenticated_manifest_and_use_policy(tmp_path):
    (
        _,
        _,
        lifecycle,
        _,
        request,
        private,
        _,
        grant,
        _,
    ) = _setup(tmp_path)

    with pytest.raises(ReflexLifecycleContractError):
        lifecycle.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            evaluation_epoch=130,
        )

    _ingest_use_policy(lifecycle, private, grant.grant_sha256)

    with pytest.raises(ReflexLifecycleContractError):
        lifecycle.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            evaluation_epoch=130,
        )

    _ingest_manifest(lifecycle, private)
    result = lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=130,
    )
    assert result["ok"] is True
    assert result["grant_use"] == {
        "used": 1,
        "max_activations": 1,
        "remaining": 0,
    }


def test_one_shot_use_limit_blocks_second_attempt_before_lower_layer(tmp_path):
    (
        _,
        authority,
        lifecycle,
        _,
        request,
        _,
        _,
        grant,
        _,
    ) = _ready(tmp_path)

    first = lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=130,
    )
    assert first["ok"] is True
    authority.deactivate(reason="test reset", evaluation_epoch=131)

    with pytest.raises(
        ReflexLifecycleContractError,
        match="use limit exhausted",
    ):
        lifecycle.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            evaluation_epoch=132,
        )


def test_effective_key_rotation_collapses_old_key_live_authority(tmp_path):
    (
        _,
        authority,
        lifecycle,
        _,
        request,
        private,
        _,
        grant,
        _,
    ) = _ready(tmp_path)
    activated = lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=130,
    )
    assert activated["ok"] is True

    _, public2 = _key()
    replacement = build_trust_anchor(
        issuer_id="operator",
        key_id="key-2",
        public_key_b64=public2,
    )
    transition_payload = trust_transition_signature_payload(
        transition_id="rotate-001",
        issuer_id="operator",
        key_id="key-1",
        action="ROTATE",
        issued_at_epoch=140,
        effective_epoch=200,
        reason="scheduled rotation",
        replacement_anchor=replacement,
    )
    transition = build_trust_transition(
        transition_id="rotate-001",
        issuer_id="operator",
        key_id="key-1",
        action="ROTATE",
        issued_at_epoch=140,
        effective_epoch=200,
        reason="scheduled rotation",
        replacement_anchor=replacement,
        signature_b64=_sign(private, transition_payload),
    )
    lifecycle.ingest_trust_transition(
        transition.to_dict(),
        evaluation_epoch=150,
    )

    assert lifecycle.status(
        evaluation_epoch=199,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
    )["routing_influence_active"] is True

    at_rotation = lifecycle.status(
        evaluation_epoch=200,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
    )
    assert at_rotation["routing_influence_active"] is False
    materialized = authority.require_trust_anchor(
        issuer_id="operator",
        key_id="key-2",
    )
    assert materialized.anchor_sha256 == replacement.anchor_sha256


def test_expired_provider_manifest_collapses_live_influence(tmp_path):
    (
        _,
        _,
        lifecycle,
        _,
        request,
        private,
        _,
        grant,
        _,
    ) = _setup(tmp_path)
    _ingest_use_policy(lifecycle, private, grant.grant_sha256)
    _ingest_manifest(lifecycle, private, valid_until=160)
    lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=130,
    )

    status = lifecycle.status(
        evaluation_epoch=160,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
    )
    assert status["routing_influence_active"] is False


def test_signed_checkpoint_must_match_exact_current_ledger_and_control(tmp_path):
    (
        control,
        authority,
        lifecycle,
        _,
        _,
        private,
        _,
        _,
        _,
    ) = _setup(tmp_path)
    authority_status = authority.status(evaluation_epoch=120)
    ledger = control.ledger()
    head = ledger[-1]["entry_sha256"] if ledger else None
    payload = ledger_checkpoint_signature_payload(
        checkpoint_id="checkpoint-001",
        issuer_id="operator",
        key_id="key-1",
        created_at_epoch=120,
        ledger_entry_count=len(ledger),
        ledger_head_sha256=head,
        control_sha256=authority_status["control_sha256"],
    )
    checkpoint = build_ledger_checkpoint(
        checkpoint_id="checkpoint-001",
        issuer_id="operator",
        key_id="key-1",
        created_at_epoch=120,
        ledger_entry_count=len(ledger),
        ledger_head_sha256=head,
        control_sha256=authority_status["control_sha256"],
        signature_b64=_sign(private, payload),
    )
    result = lifecycle.ingest_checkpoint(
        checkpoint.to_dict(),
        evaluation_epoch=120,
    )
    assert result["ok"] is True

    bad_payload = ledger_checkpoint_signature_payload(
        checkpoint_id="checkpoint-bad",
        issuer_id="operator",
        key_id="key-1",
        created_at_epoch=121,
        ledger_entry_count=0,
        ledger_head_sha256=None,
        control_sha256="f" * 64,
    )
    bad = build_ledger_checkpoint(
        checkpoint_id="checkpoint-bad",
        issuer_id="operator",
        key_id="key-1",
        created_at_epoch=121,
        ledger_entry_count=0,
        ledger_head_sha256=None,
        control_sha256="f" * 64,
        signature_b64=_sign(private, bad_payload),
    )
    with pytest.raises(ReflexLifecycleContractError):
        lifecycle.ingest_checkpoint(
            bad.to_dict(),
            evaluation_epoch=121,
        )


def test_signed_lease_renewal_binds_exact_current_activation_and_lease(tmp_path):
    (
        _,
        _,
        lifecycle,
        _,
        request,
        private,
        _,
        grant,
        _,
    ) = _ready(tmp_path)
    lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=130,
        lease_until_epoch=300,
    )
    status = lifecycle.status(
        evaluation_epoch=150,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
    )
    control = status["authority"]["control"]
    activation_sha = control["activation"]["state_sha256"]
    lease_sha = control["lease"]["lease_sha256"]
    payload = lease_renewal_signature_payload(
        renewal_id="renew-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        activation_state_sha256=activation_sha,
        current_lease_sha256=lease_sha,
        new_valid_through_epoch=500,
        issued_at_epoch=150,
    )
    renewal = build_lease_renewal(
        renewal_id="renew-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        activation_state_sha256=activation_sha,
        current_lease_sha256=lease_sha,
        new_valid_through_epoch=500,
        issued_at_epoch=150,
        signature_b64=_sign(private, payload),
    )
    result = lifecycle.renew_lease(
        renewal.to_dict(),
        evaluation_epoch=150,
    )
    assert result["control"]["lease"]["valid_through_epoch"] == 500

    with pytest.raises(ReflexLifecycleContractError):
        lifecycle.renew_lease(
            renewal.to_dict(),
            evaluation_epoch=151,
        )


def test_provider_manifest_wrong_adapter_never_authorizes_activation(tmp_path):
    (
        _,
        _,
        lifecycle,
        _,
        request,
        private,
        _,
        grant,
        _,
    ) = _setup(tmp_path)
    _ingest_use_policy(lifecycle, private, grant.grant_sha256)
    _ingest_manifest(lifecycle, private)

    with pytest.raises(ReflexLifecycleContractError):
        lifecycle.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            adapter_id="wrong.adapter",
            adapter_version=ADAPTER_VERSION,
            evaluation_epoch=130,
        )
