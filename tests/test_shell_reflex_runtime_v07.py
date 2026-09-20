from __future__ import annotations

import hashlib
import json

from phios.reflex.control_plane import ReflexRuntimeControlPlane
from phios.reflex.influence_adoption import ReflexInfluencePolicyState
from phios.reflex.models import ReflexDecision
from phios.reflex.runtime_influence import (
    ROUTING_SURFACE,
    ReflexActivationGrant,
    ReflexActivationRequest,
)
from phios.shell.phi_router import route_command


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


def _activate(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    policy = _policy()
    request = ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role", "system2"),
        influence_weight=0.20,
    )
    grant = ReflexActivationGrant(
        grant_id="grant-001",
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )
    control.ingest_policy_payload(
        policy.to_dict(),
        evaluation_epoch=100,
    )
    control.ingest_grant_payload(
        grant.to_payload(),
        evaluation_epoch=100,
    )
    result = control.activate(
        request=request,
        grant_id="grant-001",
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


def test_dispatch_restores_persisted_runtime_influence(
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
    _activate(tmp_path)

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


def test_live_influence_refuses_shadow_contamination(
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
    _activate(tmp_path)

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


def test_reflex_runtime_status_and_deactivate_commands(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)
    _activate(tmp_path)

    out, code = route_command(["agents", "reflex-runtime", "status"])
    assert code == 0
    status = json.loads(out)
    assert status["routing_influence_active"] is True

    out, code = route_command(
        [
            "agents",
            "reflex-runtime",
            "deactivate",
            "--reason",
            "operator-test",
        ]
    )
    assert code == 0
    stopped = json.loads(out)
    assert stopped["activation"]["routing_influence_active"] is False

    out, _ = route_command(["agents", "reflex-runtime", "status"])
    assert json.loads(out)["routing_influence_active"] is False


def test_reflex_runtime_policy_and_grant_ingest_files(
    monkeypatch,
    tmp_path,
):
    home = tmp_path / "runtime"
    monkeypatch.setenv("PHIOS_REFLEX_HOME", str(home))
    monkeypatch.setattr("phios.shell.phi_commands.time.time", lambda: 200)

    policy = _policy()
    request = ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role", "system2"),
        influence_weight=0.20,
    )
    grant = ReflexActivationGrant(
        grant_id="grant-file",
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )
    policy_path = tmp_path / "policy.json"
    grant_path = tmp_path / "grant.json"
    request_path = tmp_path / "request.json"
    policy_path.write_text(json.dumps(policy.to_dict()), encoding="utf-8")
    grant_path.write_text(json.dumps(grant.to_payload()), encoding="utf-8")
    request_path.write_text(
        json.dumps(request.to_payload()),
        encoding="utf-8",
    )

    out, code = route_command(
        [
            "agents",
            "reflex-runtime",
            "policy-ingest",
            str(policy_path),
        ]
    )
    assert code == 0
    assert json.loads(out)["ok"] is True

    out, code = route_command(
        [
            "agents",
            "reflex-runtime",
            "grant-ingest",
            str(grant_path),
        ]
    )
    assert code == 0
    assert json.loads(out)["ok"] is True

    out, code = route_command(
        [
            "agents",
            "reflex-runtime",
            "activate",
            "--request",
            str(request_path),
            "--grant-id",
            "grant-file",
            "--lease-until-epoch",
            "500",
        ]
    )
    assert code == 0
    activated = json.loads(out)
    assert activated["ok"] is True
    assert activated["lease"]["valid_through_epoch"] == 500
