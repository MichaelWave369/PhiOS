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


def _signed_artifacts(
    policy: ReflexInfluencePolicyState,
    request: ReflexActivationRequest,
    grant_id: str = "grant-001",
):
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
        grant_id=grant_id,
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )
    signing_payload = activation_grant_signature_payload(
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
        signature_b64=_sign(private, signing_payload),
    )
    return private, anchor, grant, envelope


def _lifecycle_artifacts(private, grant):
    use_payload = grant_use_policy_signature_payload(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        max_activations=1,
        issued_at_epoch=100,
        effective_epoch=100,
    )
    use_policy = build_grant_use_policy(
        policy_id="use-001",
        issuer_id="operator",
        key_id="key-1",
        target_grant_sha256=grant.grant_sha256,
        max_activations=1,
        issued_at_epoch=100,
        effective_epoch=100,
        signature_b64=_sign(private, use_payload),
    )
    manifest_payload = provider_manifest_signature_payload(
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
        signature_b64=_sign(private, manifest_payload),
    )
    return use_policy, manifest


def _activate_lifecycle(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    authority = ReflexAuthorityPlane(control=control)
    lifecycle = ReflexTrustLifecyclePlane(
        control=control,
        authority=authority,
    )
    policy = _policy()
    request = _request()
    private, anchor, grant, envelope = _signed_artifacts(policy, request)
    use_policy, manifest = _lifecycle_artifacts(private, grant)
    control.ingest_policy_payload(policy.to_dict(), evaluation_epoch=100)
    authority.ingest_trust_anchor(anchor.to_dict(), evaluation_epoch=100)
    authority.ingest_signed_grant(envelope.to_dict(), evaluation_epoch=100)
    lifecycle.ingest_grant_use_policy(
        use_policy.to_dict(),
        evaluation_epoch=100,
    )
    lifecycle.ingest_provider_manifest(
        manifest.to_dict(),
        evaluation_epoch=100,
    )
    result = lifecycle.activate_verified(
        request=request,
        grant_id=grant.grant_id,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        evaluation_epoch=101,
    )
    assert result["ok"] is True


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


def test_dispatch_restores_persisted_v09_lifecycle_influence(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        FakeAdapter,
    )
    monkeypatch.setattr(
        "phios.shell.phi_commands.JevReflexProvider",
        FakeJevProvider,
    )
    _activate_lifecycle(tmp_path)

    out, code = route_command(
        ["dispatch", "build", "adapter", "--dry-run"]
    )

    assert code == 0
    payload = json.loads(out)
    influence = payload["context"]["reflex_influence"]
    assert influence["provider"] == "jev"
    assert influence["model"] == "jev-test"
    assert influence["routing_influence_authority"] is True
    assert influence["action_authority"] is False
    assert influence["execution_authority"] is False
    assert payload["reflex_runtime"]["status"] == "INFLUENCED"


def test_live_lifecycle_influence_refuses_shadow_contamination(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        FakeAdapter,
    )
    monkeypatch.setattr(
        "phios.shell.phi_commands.JevReflexProvider",
        FakeJevProvider,
    )
    _activate_lifecycle(tmp_path)

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


def test_v08_direct_activation_cli_is_disabled_by_v09(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)

    out, code = route_command(
        [
            "agents",
            "reflex-authority",
            "activate",
            "--request",
            "request.json",
            "--grant-id",
            "grant",
            "--yes",
        ]
    )
    assert code == 0
    assert "Direct v0.8 activation is disabled" in out


def test_reflex_lifecycle_file_ingest_and_activation(
    monkeypatch,
    tmp_path,
):
    home = tmp_path / "runtime"
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(home))
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)

    policy = _policy()
    request = _request()
    private, anchor, grant, envelope = _signed_artifacts(
        policy,
        request,
        grant_id="grant-file",
    )
    use_policy, manifest = _lifecycle_artifacts(private, grant)

    paths = {}
    for name, payload in {
        "policy": policy.to_dict(),
        "anchor": anchor.to_dict(),
        "grant": envelope.to_dict(),
        "request": request.to_payload(),
        "use": use_policy.to_dict(),
        "manifest": manifest.to_dict(),
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path

    commands = [
        ["agents", "reflex-runtime", "policy-ingest", str(paths["policy"])],
        [
            "agents",
            "reflex-authority",
            "trust-ingest",
            str(paths["anchor"]),
            "--yes",
        ],
        [
            "agents",
            "reflex-authority",
            "grant-ingest",
            str(paths["grant"]),
        ],
        [
            "agents",
            "reflex-lifecycle",
            "use-policy",
            str(paths["use"]),
        ],
        [
            "agents",
            "reflex-lifecycle",
            "provider-manifest",
            str(paths["manifest"]),
        ],
    ]
    for command in commands:
        out, code = route_command(command)
        assert code == 0
        assert json.loads(out)["ok"] is True

    out, code = route_command(
        [
            "agents",
            "reflex-lifecycle",
            "activate",
            "--request",
            str(paths["request"]),
            "--grant-id",
            grant.grant_id,
            "--lease-until-epoch",
            "400",
            "--yes",
        ]
    )
    assert code == 0
    activated = json.loads(out)
    assert activated["ok"] is True
    assert activated["grant_use"]["remaining"] == 0
    assert activated["lease"]["valid_through_epoch"] == 400

    out, code = route_command(
        ["agents", "reflex-lifecycle", "status"]
    )
    assert code == 0
    status = json.loads(out)
    assert status["routing_influence_active"] is True
