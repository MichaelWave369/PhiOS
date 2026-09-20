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
    ReflexTrustLifecyclePlane,
    build_grant_use_policy,
    build_ledger_checkpoint,
    build_provider_manifest,
    grant_use_policy_signature_payload,
    ledger_checkpoint_signature_payload,
    provider_manifest_signature_payload,
)
from phios.reflex.root_attestation import (
    ReflexRootAttestationContractError,
    ReflexRootAttestationPlane,
    ReflexRootPin,
    activation_nonce_signature_payload,
    adapter_source_sha256,
    build_activation_nonce,
    build_provider_artifact,
    build_replication_snapshot,
    provider_artifact_signature_payload,
    replication_snapshot_signature_payload,
    verify_checkpoint_bundle,
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
        "max_influence_weight": 0.2,
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
        max_influence_weight=0.2,
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


def _setup(tmp_path, *, max_activations: int = 2):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    authority = ReflexAuthorityPlane(control=control)
    lifecycle = ReflexTrustLifecyclePlane(control=control, authority=authority)
    policy = _policy()
    request = ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role", "system2"),
        influence_weight=0.2,
    )
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
    gp = activation_grant_signature_payload(
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
        signature_b64=_sign(private, gp),
    )
    authority.ingest_signed_grant(envelope.to_dict(), evaluation_epoch=110)

    up = grant_use_policy_signature_payload(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        max_activations=max_activations,
        issued_at_epoch=120,
        effective_epoch=120,
    )
    use = build_grant_use_policy(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        max_activations=max_activations,
        issued_at_epoch=120,
        effective_epoch=120,
        signature_b64=_sign(private, up),
    )
    lifecycle.ingest_grant_use_policy(use.to_dict(), evaluation_epoch=120)

    mp = provider_manifest_signature_payload(
        manifest_id="jev-runtime-001",
        issuer_id="operator",
        key_id="key-1",
        provider="jev",
        models=("jev-test",),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        issued_at_epoch=120,
        effective_epoch=120,
        valid_until_epoch=800,
    )
    manifest = build_provider_manifest(
        manifest_id="jev-runtime-001",
        issuer_id="operator",
        key_id="key-1",
        provider="jev",
        models=("jev-test",),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        issued_at_epoch=120,
        effective_epoch=120,
        valid_until_epoch=800,
        signature_b64=_sign(private, mp),
    )
    lifecycle.ingest_provider_manifest(manifest.to_dict(), evaluation_epoch=120)

    pin = ReflexRootPin(
        issuer_id="operator",
        key_id="key-1",
        anchor_sha256=anchor.anchor_sha256,
    )
    root_plane = ReflexRootAttestationPlane(
        lifecycle=lifecycle,
        root_pin=pin,
    )
    source_sha = adapter_source_sha256(ADAPTER_ID)
    ap = provider_artifact_signature_payload(
        attestation_id="artifact-001",
        issuer_id="operator",
        key_id="key-1",
        provider_manifest_sha256=manifest.envelope_sha256,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        adapter_source_sha256=source_sha,
        issued_at_epoch=120,
        effective_epoch=120,
        valid_until_epoch=800,
    )
    artifact = build_provider_artifact(
        attestation_id="artifact-001",
        issuer_id="operator",
        key_id="key-1",
        provider_manifest_sha256=manifest.envelope_sha256,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        adapter_source_sha256=source_sha,
        issued_at_epoch=120,
        effective_epoch=120,
        valid_until_epoch=800,
        signature_b64=_sign(private, ap),
    )
    root_plane.ingest_provider_artifact(
        artifact.to_dict(),
        evaluation_epoch=120,
    )
    return (
        control,
        authority,
        lifecycle,
        root_plane,
        request,
        private,
        anchor,
        grant,
        manifest,
        source_sha,
    )


def _nonce(root_plane, private, grant, request, *, nonce_id="nonce-001"):
    payload = activation_nonce_signature_payload(
        nonce_id=nonce_id,
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        activation_request_sha256=request.request_sha256,
        issued_at_epoch=125,
        valid_until_epoch=500,
    )
    nonce = build_activation_nonce(
        nonce_id=nonce_id,
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        activation_request_sha256=request.request_sha256,
        issued_at_epoch=125,
        valid_until_epoch=500,
        signature_b64=_sign(private, payload),
    )
    root_plane.ingest_nonce(nonce.to_dict(), evaluation_epoch=125)
    return nonce


def test_exact_root_pin_artifact_and_nonce_allow_activation(tmp_path):
    (
        _,
        _,
        _,
        root_plane,
        request,
        private,
        _,
        grant,
        _,
        source_sha,
    ) = _setup(tmp_path)
    _nonce(root_plane, private, grant, request)

    result = root_plane.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        nonce_id="nonce-001",
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        adapter_source_sha256=source_sha,
        evaluation_epoch=130,
    )

    assert result["ok"] is True
    assert result["activation_nonce"]["consumed"] is True


def test_nonce_is_one_use_even_when_grant_allows_multiple_activations(tmp_path):
    (
        _,
        authority,
        _,
        root_plane,
        request,
        private,
        _,
        grant,
        _,
        source_sha,
    ) = _setup(tmp_path, max_activations=3)
    _nonce(root_plane, private, grant, request)
    root_plane.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        nonce_id="nonce-001",
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        adapter_source_sha256=source_sha,
        evaluation_epoch=130,
    )
    authority.deactivate(reason="test reset", evaluation_epoch=131)

    with pytest.raises(
        ReflexRootAttestationContractError,
        match="already been consumed",
    ):
        root_plane.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            nonce_id="nonce-001",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            adapter_source_sha256=source_sha,
            evaluation_epoch=132,
        )


def test_missing_external_root_pin_collapses_live_authority(tmp_path):
    (
        control,
        authority,
        lifecycle,
        _,
        request,
        _,
        _,
        grant,
        _,
        _,
    ) = _setup(tmp_path)
    lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=130,
    )
    assert control.status(evaluation_epoch=131)["routing_influence_active"] is True

    unpinned = ReflexRootAttestationPlane(lifecycle=lifecycle, root_pin=None)
    status = unpinned.status(evaluation_epoch=132)

    assert status["root_pin_valid"] is False
    assert authority.status(evaluation_epoch=133)["routing_influence_active"] is False


def test_wrong_installed_adapter_digest_cannot_activate(tmp_path):
    (
        _,
        _,
        _,
        root_plane,
        request,
        private,
        _,
        grant,
        _,
        _,
    ) = _setup(tmp_path)
    _nonce(root_plane, private, grant, request)

    with pytest.raises(
        ReflexRootAttestationContractError,
        match="no effective authenticated provider-artifact",
    ):
        root_plane.activate_verified(
            request=request,
            grant_id=grant.grant_id,
            nonce_id="nonce-001",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            adapter_source_sha256="f" * 64,
            evaluation_epoch=130,
        )


def test_checkpoint_bundle_verifies_offline_and_tamper_fails(tmp_path):
    (
        control,
        authority,
        lifecycle,
        root_plane,
        _,
        private,
        _,
        _,
        _,
        _,
    ) = _setup(tmp_path)
    status = authority.status(evaluation_epoch=130)
    ledger = control.ledger()
    head = ledger[-1]["entry_sha256"] if ledger else None
    cp = ledger_checkpoint_signature_payload(
        checkpoint_id="cp-001",
        issuer_id="operator",
        key_id="key-1",
        created_at_epoch=130,
        ledger_entry_count=len(ledger),
        ledger_head_sha256=head,
        control_sha256=status["control_sha256"],
    )
    checkpoint = build_ledger_checkpoint(
        checkpoint_id="cp-001",
        issuer_id="operator",
        key_id="key-1",
        created_at_epoch=130,
        ledger_entry_count=len(ledger),
        ledger_head_sha256=head,
        control_sha256=status["control_sha256"],
        signature_b64=_sign(private, cp),
    )
    lifecycle.ingest_checkpoint(
        checkpoint.to_dict(),
        evaluation_epoch=130,
    )
    bundle = root_plane.export_checkpoint_bundle(checkpoint_id="cp-001")
    verified = verify_checkpoint_bundle(bundle)
    assert verified["ok"] is True

    tampered = json.loads(json.dumps(bundle))
    tampered["checkpoint"]["control_sha256"] = "f" * 64
    with pytest.raises(Exception):
        verify_checkpoint_bundle(tampered)


def test_replication_conflict_is_receipted_without_overwriting_activation(tmp_path):
    (
        control,
        _,
        _,
        root_plane,
        _,
        private,
        anchor,
        _,
        _,
        _,
    ) = _setup(tmp_path)
    before = control.status(evaluation_epoch=130)
    before_activation = before["activation"]

    payload = replication_snapshot_signature_payload(
        snapshot_id="remote-001",
        issuer_id="operator",
        key_id="key-1",
        exported_at_epoch=130,
        control_sha256="f" * 64,
        root_anchor_sha256=anchor.anchor_sha256,
        checkpoint_envelope_sha256=None,
    )
    snapshot = build_replication_snapshot(
        snapshot_id="remote-001",
        issuer_id="operator",
        key_id="key-1",
        exported_at_epoch=130,
        control_sha256="f" * 64,
        root_anchor_sha256=anchor.anchor_sha256,
        checkpoint_envelope_sha256=None,
        signature_b64=_sign(private, payload),
    )
    result = root_plane.ingest_replication_snapshot(
        snapshot.to_dict(),
        evaluation_epoch=130,
    )

    assert result["aligned"] is False
    assert result["receipt"]["status"] == "REPLICATION_CONFLICT"
    after = control.status(evaluation_epoch=131)
    assert after["activation"] == before_activation


def test_adapter_source_digest_is_stable_sha256():
    digest = adapter_source_sha256(ADAPTER_ID)
    assert len(digest) == 64
    int(digest, 16)
