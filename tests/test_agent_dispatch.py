from __future__ import annotations

import json

from phios.services.agent_dispatch import (
    build_dispatch_context,
    cancel_agent_run,
    dispatch_agentception_run,
    get_agent_run_status,
    list_agent_runs,
    persist_dispatch_storyboard,
    run_agentception_plan,
    stream_agent_run_events,
)


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.55,
            "C_star": 0.93,
            "recommended_action": "stabilize",
            "field_band": "amber",
        }

    def capsule_list(self):
        return {"capsules": [1, 2, 3]}


def test_dispatch_dry_run_plan_and_field_guided_context(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    context = build_dispatch_context(
        task="test decomposition",
        adapter=DummyAdapter(),
        field_guided=True,
        arch="mesh",
        review_panel=True,
    )
    plan = run_agentception_plan(task="test decomposition", context=context)

    assert context["arch"] == "mesh"
    assert "field_state" in context
    assert plan["source"] == "local-fallback"
    assert isinstance(plan.get("plan_steps"), list)


def test_runs_status_kill_and_events(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    context = build_dispatch_context(
        task="agent run",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(task="agent run", context=context)
    run = dispatch_agentception_run(task="agent run", context=context, plan=plan, stream=False)
    run_id = str(run["run_id"])

    runs = list_agent_runs(active_only=True)
    assert any(str(item.get("run_id")) == run_id for item in runs)

    status = get_agent_run_status(run_id)
    assert status["run_id"] == run_id

    killed = cancel_agent_run(run_id)
    assert killed["ok"] is True

    events = stream_agent_run_events(run_id)
    assert len(events) >= 2


def test_storyboard_persistence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    context = build_dispatch_context(
        task="persist storyboard",
        adapter=DummyAdapter(),
        field_guided=True,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(task="persist storyboard", context=context)
    run = dispatch_agentception_run(task="persist storyboard", context=context, plan=plan, stream=False)
    run_id = str(run["run_id"])
    result = persist_dispatch_storyboard(run=run, plan=plan, events=stream_agent_run_events(run_id))

    sb_name = result["storyboard_name"]
    sb_path = tmp_path / ".phios" / "journal" / "visual_bloom" / "storyboards" / f"{sb_name}.json"
    assert sb_path.exists()
    payload = json.loads(sb_path.read_text(encoding="utf-8"))
    assert payload["storyboard_name"] == sb_name


def test_dispatch_run_persists_shadow_observations_without_planner_contamination(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    context = build_dispatch_context(
        task="shadow dispatch",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(task="shadow dispatch", context=context)
    shadow = {
        "phireflex_v0_2": {
            "schema": "phios.reflex_dispatch_shadow_receipt.v0.2",
            "receipt_sha256": "a" * 64,
        }
    }

    assert "reflex" not in json.dumps(context).lower()
    assert "reflex" not in json.dumps(plan).lower()

    run = dispatch_agentception_run(
        task="shadow dispatch",
        context=context,
        plan=plan,
        stream=False,
        shadow_observations=shadow,
    )

    assert run["shadow_observations"] == shadow
    assert "reflex" not in json.dumps(run["context"]).lower()
    assert "reflex" not in json.dumps(run["plan"]).lower()


def test_remote_dispatch_payload_excludes_reflex_shadow(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "true")
    captured = []

    def fake_http_json(url, *, method="GET", payload=None, timeout_s=10.0):
        captured.append({"url": url, "method": method, "payload": payload})
        return True, {"run_id": "remote-1", "status": "running"}

    monkeypatch.setattr(
        "phios.services.agent_dispatch._http_json",
        fake_http_json,
    )

    context = build_dispatch_context(
        task="remote shadow dispatch",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = {
        "source": "local-test",
        "planner_available": True,
        "plan_steps": [{"step": "work", "status": "pending"}],
    }
    shadow = {
        "phireflex_v0_2": {
            "schema": "phios.reflex_dispatch_shadow_receipt.v0.2",
            "receipt_sha256": "b" * 64,
        }
    }

    run = dispatch_agentception_run(
        task="remote shadow dispatch",
        context=context,
        plan=plan,
        stream=False,
        shadow_observations=shadow,
    )

    assert run["shadow_observations"] == shadow
    assert len(captured) == 1
    outbound = captured[0]["payload"]
    assert isinstance(outbound, dict)
    assert set(outbound) == {"task", "context", "plan", "stream"}
    assert "reflex" not in json.dumps(outbound).lower()


def test_dispatch_context_accepts_only_validated_v06_reflex_signal(monkeypatch):
    from phios.reflex.influence_adoption import ReflexInfluencePolicyState
    from phios.reflex.models import ReflexDecision, ReflexInput
    from phios.reflex.runtime_influence import (
        ROUTING_SURFACE,
        GovernedReflexRuntimeInfluence,
        ReflexActivationGrant,
        ReflexActivationRequest,
    )

    def digest(value):
        import hashlib
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    policy_payload = {
        "schema": "phios.reflex_influence_policy_state.v0.5",
        "policy_id": "phios.reflex.influence.jev",
        "revision": 0,
        "readiness_receipt_sha256": "a" * 64,
        "candidate_provider": "jev",
        "candidate_models": ["jev-test"],
        "allowed_dimensions": ["role"],
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
    policy = ReflexInfluencePolicyState(
        schema="phios.reflex_influence_policy_state.v0.5",
        policy_id="phios.reflex.influence.jev",
        revision=0,
        readiness_receipt_sha256="a" * 64,
        candidate_provider="jev",
        candidate_models=("jev-test",),
        allowed_dimensions=("role",),
        max_influence_weight=0.2,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=2,
        parent_policy_sha256=None,
        routing_influence_active=False,
        runtime_activation_authority=False,
        promotion_authority=False,
        action_authority=False,
        execution_authority=False,
        state_sha256=digest(policy_payload),
    )
    request = ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role",),
        influence_weight=0.2,
    )
    grant = ReflexActivationGrant(
        grant_id="g",
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )
    runtime = GovernedReflexRuntimeInfluence()
    state, _ = runtime.activate(
        policy=policy,
        request=request,
        grant=grant,
    )
    assert state is not None

    baseline = ReflexDecision(
        provider="rules",
        provider_version="test",
        model="rules",
        role="utility",
        role_probabilities=(
            ("utility", 0.8),
            ("builder", 0.05),
            ("synthesis", 0.05),
            ("translator", 0.05),
            ("ledger", 0.05),
        ),
        risk="low",
        risk_probabilities=(
            ("low", 0.8),
            ("elevated", 0.1),
            ("high", 0.1),
        ),
        needs_system2_probability=0.2,
        needs_verification_probability=0.2,
        confidence=0.8,
        latency_ms=0.0,
    )
    candidate = ReflexDecision(
        provider="jev",
        provider_version="test",
        model="jev-test",
        role="builder",
        role_probabilities=(
            ("utility", 0.05),
            ("builder", 0.85),
            ("synthesis", 0.04),
            ("translator", 0.03),
            ("ledger", 0.03),
        ),
        risk="low",
        risk_probabilities=(
            ("low", 0.8),
            ("elevated", 0.1),
            ("high", 0.1),
        ),
        needs_system2_probability=0.9,
        needs_verification_probability=0.9,
        confidence=0.85,
        latency_ms=1.0,
    )

    class Fixed:
        def __init__(self, decision):
            self.decision = decision

        def evaluate(self, reflex_input: ReflexInput):
            return self.decision

    _, signal, receipt = runtime.evaluate(
        policy=policy,
        state=state,
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=Fixed(baseline),
        influence_provider=Fixed(candidate),
    )
    assert receipt.status == "INFLUENCED"
    assert signal is not None

    context = build_dispatch_context(
        task="build adapter",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
        reflex_influence=signal,
    )

    assert context["reflex_influence"]["schema"] == (
        "phios.reflex_routing_influence_signal.v0.6"
    )
    assert context["reflex_influence"]["routing_influence_authority"] is True
    assert context["reflex_influence"]["action_authority"] is False
    assert context["reflex_influence"]["execution_authority"] is False


def test_remote_planner_receives_v06_reflex_signal_only_when_explicitly_attached(
    monkeypatch,
):
    from phios.reflex.runtime_influence import ReflexRoutingInfluenceSignal

    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "true")
    captured = []

    def fake_http_json(url, *, method="GET", payload=None, timeout_s=10.0):
        captured.append(payload)
        return True, {"plan_id": "p", "plan_steps": []}

    monkeypatch.setattr(
        "phios.services.agent_dispatch._http_json",
        fake_http_json,
    )

    base_signal_payload = {
        "schema": "phios.reflex_routing_influence_signal.v0.6",
        "activation_state_sha256": "a" * 64,
        "policy_state_sha256": "b" * 64,
        "routing_surface": "agentception.planner_context.v0.6",
        "provider": "jev",
        "model": "jev-test",
        "influence_weight": 0.2,
        "allowed_dimensions": ["role"],
        "role_probabilities": {
            "utility": 0.65,
            "builder": 0.21,
            "synthesis": 0.05,
            "translator": 0.045,
            "ledger": 0.045,
        },
        "risk_probabilities": None,
        "needs_system2_probability": None,
        "needs_verification_probability": None,
        "routing_influence_authority": True,
        "action_authority": False,
        "execution_authority": False,
    }
    base_signal_payload["signal_sha256"] = __import__("hashlib").sha256(
        json.dumps(
            base_signal_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    signal = ReflexRoutingInfluenceSignal(
        schema="phios.reflex_routing_influence_signal.v0.6",
        activation_state_sha256="a" * 64,
        policy_state_sha256="b" * 64,
        routing_surface="agentception.planner_context.v0.6",
        provider="jev",
        model="jev-test",
        influence_weight=0.2,
        allowed_dimensions=("role",),
        role_probabilities=(
            ("utility", 0.65),
            ("builder", 0.21),
            ("synthesis", 0.05),
            ("translator", 0.045),
            ("ledger", 0.045),
        ),
        risk_probabilities=None,
        needs_system2_probability=None,
        needs_verification_probability=None,
        routing_influence_authority=True,
        action_authority=False,
        execution_authority=False,
        signal_sha256=base_signal_payload["signal_sha256"],
    )

    plain = build_dispatch_context(
        task="plain",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    run_agentception_plan(task="plain", context=plain)
    assert "reflex_influence" not in captured[-1]["context"]

    influenced = build_dispatch_context(
        task="influenced",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
        reflex_influence=signal,
    )
    run_agentception_plan(task="influenced", context=influenced)
    assert captured[-1]["context"]["reflex_influence"]["provider"] == "jev"
