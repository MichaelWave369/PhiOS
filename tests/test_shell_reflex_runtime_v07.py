from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

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
    build_provider_manifest,
    grant_use_policy_signature_payload,
    provider_manifest_signature_payload,
)
from phios.reflex.models import ReflexDecision
from phios.reflex.root_attestation import (
    ReflexRootAttestationPlane,
    ReflexRootPin,
    activation_nonce_signature_payload,
    adapter_source_sha256,
    build_activation_nonce,
    build_provider_artifact,
    provider_artifact_signature_payload,
)
from phios.reflex.runtime_influence import (
    ROUTING_SURFACE,
    ReflexActivationGrant,
    ReflexActivationRequest,
)
from phios.shell.phi_router import route_command


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


def _artifacts():
    policy = _policy()
    request = _request()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    anchor = build_trust_anchor(
        issuer_id="operator",
        key_id="key-1",
        public_key_b64=base64.b64encode(public).decode("ascii"),
    )
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
        valid_until_epoch=500,
        grant=grant,
    )
    envelope = build_signed_activation_grant_envelope(
        issuer_id="operator",
        key_id="key-1",
        issued_at_epoch=100,
        valid_from_epoch=100,
        valid_until_epoch=500,
        grant=grant,
        signature_b64=_sign(private, gp),
    )
    up = grant_use_policy_signature_payload(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        max_activations=2,
        issued_at_epoch=100,
        effective_epoch=100,
    )
    use_policy = build_grant_use_policy(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        max_activations=2,
        issued_at_epoch=100,
        effective_epoch=100,
        signature_b64=_sign(private, up),
    )
    mp = provider_manifest_signature_payload(
        manifest_id="jev-runtime-001",
        issuer_id="operator",
        key_id="key-1",
        provider="jev",
        models=("jev-test",),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        issued_at_epoch=100,
        effective_epoch=100,
        valid_until_epoch=500,
    )
    manifest = build_provider_manifest(
        manifest_id="jev-runtime-001",
        issuer_id="operator",
        key_id="key-1",
        provider="jev",
        models=("jev-test",),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        issued_at_epoch=100,
        effective_epoch=100,
        valid_until_epoch=500,
        signature_b64=_sign(private, mp),
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
        issued_at_epoch=100,
        effective_epoch=100,
        valid_until_epoch=500,
    )
    artifact = build_provider_artifact(
        attestation_id="artifact-001",
        issuer_id="operator",
        key_id="key-1",
        provider_manifest_sha256=manifest.envelope_sha256,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        adapter_source_sha256=source_sha,
        issued_at_epoch=100,
        effective_epoch=100,
        valid_until_epoch=500,
        signature_b64=_sign(private, ap),
    )
    np = activation_nonce_signature_payload(
        nonce_id="nonce-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        activation_request_sha256=request.request_sha256,
        issued_at_epoch=100,
        valid_until_epoch=500,
    )
    nonce = build_activation_nonce(
        nonce_id="nonce-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        activation_request_sha256=request.request_sha256,
        issued_at_epoch=100,
        valid_until_epoch=500,
        signature_b64=_sign(private, np),
    )
    return {
        "policy": policy,
        "request": request,
        "anchor": anchor,
        "grant": grant,
        "envelope": envelope,
        "use_policy": use_policy,
        "manifest": manifest,
        "artifact": artifact,
        "nonce": nonce,
        "source_sha": source_sha,
    }


def _activate_root(tmp_path):
    values = _artifacts()
    control = ReflexRuntimeControlPlane(root=tmp_path)
    authority = ReflexAuthorityPlane(control=control)
    lifecycle = ReflexTrustLifecyclePlane(
        control=control,
        authority=authority,
    )
    anchor = values["anchor"]
    control.ingest_policy_payload(
        values["policy"].to_dict(),
        evaluation_epoch=100,
    )
    authority.ingest_trust_anchor(anchor.to_dict(), evaluation_epoch=100)
    authority.ingest_signed_grant(
        values["envelope"].to_dict(),
        evaluation_epoch=100,
    )
    lifecycle.ingest_grant_use_policy(
        values["use_policy"].to_dict(),
        evaluation_epoch=100,
    )
    lifecycle.ingest_provider_manifest(
        values["manifest"].to_dict(),
        evaluation_epoch=100,
    )
    root_plane = ReflexRootAttestationPlane(
        lifecycle=lifecycle,
        root_pin=ReflexRootPin(
            issuer_id="operator",
            key_id="key-1",
            anchor_sha256=anchor.anchor_sha256,
        ),
    )
    root_plane.ingest_provider_artifact(
        values["artifact"].to_dict(),
        evaluation_epoch=100,
    )
    root_plane.ingest_nonce(
        values["nonce"].to_dict(),
        evaluation_epoch=100,
    )
    result = root_plane.activate_verified(
        request=values["request"],
        grant_id=values["grant"].grant_id,
        nonce_id=values["nonce"].nonce_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        adapter_source_sha256=values["source_sha"],
        evaluation_epoch=101,
    )
    assert result["ok"] is True
    return values


class FakeAdapter:
    def status(self):
        return {
            "heart_state": "running",
            "anchor_verification_state": "verified",
        }

    def field(self):
        return {
            "C_current": 0.9,
            "field_band": "green",
            "recommended_action": "maintain",
        }

    def capsule_list(self):
        return {"capsules": [1]}


class FakeJevProvider:
    name = "jev"
    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def evaluate(self, reflex_input):
        return ReflexDecision(
            provider="jev",
            provider_version="test",
            model="jev-test",
            role="builder",
            role_probabilities=(
                ("utility", 0.01),
                ("builder", 0.95),
                ("synthesis", 0.01),
                ("translator", 0.01),
                ("ledger", 0.02),
            ),
            risk="elevated",
            risk_probabilities=(
                ("low", 0.05),
                ("elevated", 0.90),
                ("high", 0.05),
            ),
            needs_system2_probability=0.90,
            needs_verification_probability=0.90,
            confidence=0.90,
            latency_ms=1.0,
        )


def _configure_shell(monkeypatch, tmp_path, anchor_sha):
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    monkeypatch.setenv(
        "PHIOS_REFLEX_ROOT_PIN",
        f"operator:key-1:{anchor_sha}",
    )
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        FakeAdapter,
    )
    monkeypatch.setattr(
        "phios.shell.phi_commands.JevReflexProvider",
        FakeJevProvider,
    )


def test_dispatch_restores_persisted_v010_root_governed_influence(
    monkeypatch,
    tmp_path,
):
    values = _activate_root(tmp_path)
    _configure_shell(monkeypatch, tmp_path, values["anchor"].anchor_sha256)

    out, code = route_command(
        ["dispatch", "build", "adapter", "--dry-run"]
    )

    assert code == 0
    payload = json.loads(out)
    influence = payload["context"]["reflex_influence"]
    assert influence["provider"] == "jev"
    assert influence["routing_influence_authority"] is True
    assert influence["action_authority"] is False
    assert influence["execution_authority"] is False
    assert payload["reflex_runtime"]["status"] == "INFLUENCED"


def test_live_root_governed_influence_refuses_shadow_contamination(
    monkeypatch,
    tmp_path,
):
    values = _activate_root(tmp_path)
    _configure_shell(monkeypatch, tmp_path, values["anchor"].anchor_sha256)

    out, code = route_command(
        [
            "dispatch",
            "build",
            "adapter",
            "--dry-run",
            "--reflex-shadow",
        ]
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error_code"] == "REFLEX_LIVE_SHADOW_CONFLICT"


def test_v09_direct_activation_cli_is_disabled_by_v010(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)

    out, code = route_command(
        [
            "agents",
            "reflex-lifecycle",
            "activate",
            "--request",
            "request.json",
            "--grant-id",
            "grant-001",
            "--yes",
        ]
    )

    assert code == 0
    assert "disabled by PhiReflex v0.10" in out
    assert "reflex-root activate" in out


def test_reflex_root_status_reports_exact_pin_and_adapter_digest(
    monkeypatch,
    tmp_path,
):
    values = _activate_root(tmp_path)
    _configure_shell(monkeypatch, tmp_path, values["anchor"].anchor_sha256)

    out, code = route_command(["agents", "reflex-root", "status"])
    assert code == 0
    status = json.loads(out)
    assert status["root_pin_valid"] is True
    assert status["provider_artifact_valid"] is True
    assert status["routing_influence_active"] is True

    out, code = route_command(
        ["agents", "reflex-root", "adapter-digest"]
    )
    assert code == 0
    digest = json.loads(out)
    assert digest["adapter_source_sha256"] == values["source_sha"]
