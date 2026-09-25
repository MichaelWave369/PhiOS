from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_action_binding import (
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_execution_handoff import (
    ExecutionHandoffContractError,
    GovernedExecutionHandoff,
)
from phios.core.governed_plan_adoption import GovernedPlanAdoptionGate
from phios.spine.executor import ArtifactResult
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine


def _route_receipt() -> FieldAwareRouteReceipt:
    payload = {
        "schema": "phios.field_aware_route_receipt.v0.4",
        "status": "found",
        "field_law_sha256": "a" * 64,
        "field_state_sha256": "b" * 64,
        "field_revision": 0,
        "bindings": [],
        "path_receipt_sha256": "c" * 64,
        "path_ids": ["A", "B", "D"],
        "total_cost": 2.0,
        "optimality_scope": (
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        "action_authority": False,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return FieldAwareRouteReceipt(
        schema="phios.field_aware_route_receipt.v0.4",
        status="found",
        field_law_sha256="a" * 64,
        field_state_sha256="b" * 64,
        field_revision=0,
        bindings=(),
        path_receipt_sha256="c" * 64,
        path_ids=("A", "B", "D"),
        total_cost=2.0,
        optimality_scope=(
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        action_authority=False,
        receipt_sha256=digest,
    )


def _plan(plan_id: str = "primary-plan"):
    return GovernedPlanAdoptionGate().initialize_plan(
        plan_id=plan_id,
        route_receipt=_route_receipt(),
    )


def _binding(plan, capability: Capability, payload: dict[str, object]):
    binder = GovernedActionBinder()
    payload_sha = binder.payload_sha256(payload)
    grant = ActionBindingGrant(
        grant_id="bind-001",
        authority_source="operator",
        plan_id=plan.plan_id,
        plan_state_sha256=plan.state_sha256,
        transition_index=0,
        source_state_id="A",
        target_state_id="B",
        capability_id=capability.id,
        payload_sha256=payload_sha,
    )
    binding, receipt = binder.bind(
        plan=plan,
        transition_index=0,
        capability=capability,
        payload=payload,
        grant=grant,
    )
    assert receipt.status == "BOUND"
    assert binding is not None
    return binding


def test_authorized_bound_action_executes_through_existing_spine(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "proof", "text": "PhiOS governed execution"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)

    receipt = GovernedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert receipt.status == "SUCCEEDED"
    assert receipt.binding_consumed is True
    assert receipt.spine_permission_status == "allowed"
    assert receipt.spine_execution_status == "succeeded"
    assert receipt.artifact_path is not None
    assert Path(receipt.artifact_path).read_text(encoding="utf-8") == (
        "PhiOS governed execution"
    )
    ledger_entry = spine.ledger.recent(1)[0]
    provenance = ledger_entry["governed_provenance"]
    assert isinstance(provenance, dict)
    assert provenance["schema_version"] == "phios.execution_provenance.v0.8"
    assert provenance["action_binding_sha256"] == binding.binding_sha256
    assert provenance["action_lease_sha256"] is None


def test_permission_denial_does_not_consume_binding_and_retry_can_succeed(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "retry", "text": "later"}
    denied_spine = PhiOSSpine(state_root=tmp_path)
    capability = denied_spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    handoff = GovernedExecutionHandoff()

    denied = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=denied_spine,
    )

    assert denied.status == "DENIED"
    assert denied.binding_consumed is False
    assert denied_spine.ledger.has_consumed_binding(binding.binding_sha256) is False

    allowed_spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    succeeded = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=allowed_spine,
    )

    assert succeeded.status == "SUCCEEDED"
    assert succeeded.binding_consumed is True


def test_successful_binding_replay_is_held(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "once", "text": "one shot"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    handoff = GovernedExecutionHandoff()

    first = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )
    second = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert first.status == "SUCCEEDED"
    assert second.status == "HELD"
    assert second.reason == "binding_already_consumed"
    assert second.replay_blocked is True
    assert len(spine.ledger.recent(10)) == 1


def test_payload_drift_is_held_before_spine_execution(tmp_path: Path) -> None:
    plan = _plan()
    bound_payload = {"name": "bound", "text": "original"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        bound_payload,
    )

    receipt = GovernedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload={"name": "bound", "text": "changed"},
        spine=spine,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "payload_digest_mismatch"
    assert spine.ledger.recent(10) == []


def test_binding_for_another_valid_plan_is_held(tmp_path: Path) -> None:
    original = _plan("plan-a")
    current = _plan("plan-b")
    payload = {"name": "scope", "text": "test"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        original,
        spine.registry.get("commons.text_artifact"),
        payload,
    )

    receipt = GovernedExecutionHandoff().execute(
        plan=current,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "binding_plan_scope_mismatch"


def test_capability_contract_drift_is_held(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "drift", "text": "test"}
    bound_capability = Capability(
        id="custom.capability",
        name="Custom",
        description="bound version",
        permissions=("custom.write",),
        effects=("filesystem.change",),
        risk="low",
        version="1.0.0",
    )
    binding = _binding(plan, bound_capability, payload)

    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["custom.write"],
    )
    spine.registry.register(
        Capability(
            id="custom.capability",
            name="Custom",
            description="runtime version",
            permissions=("custom.write",),
            effects=("filesystem.change",),
            risk="low",
            version="2.0.0",
        )
    )

    receipt = GovernedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "capability_contract_drift"


def test_failed_executor_consumes_binding_to_prevent_blind_retry(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"value": "danger"}
    capability = Capability(
        id="custom.failure",
        name="Failure",
        description="always fails",
        permissions=("custom.execute",),
        effects=("external_state.change",),
        risk="medium",
        version="1.0.0",
    )
    binding = _binding(plan, capability, payload)
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["custom.execute"],
    )
    spine.registry.register(capability)

    def fail_handler(data: dict[str, object]) -> ArtifactResult:
        raise RuntimeError("simulated executor failure")

    spine.executors.register(
        capability.id,
        fail_handler,
        effects=("external_state.change",),
    )
    handoff = GovernedExecutionHandoff()

    failed = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )
    replay = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert failed.status == "FAILED"
    assert failed.binding_consumed is True
    assert replay.status == "HELD"
    assert replay.reason == "binding_already_consumed"


def test_unicode_payload_hash_matches_spine_execution_hash(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "unicode", "text": "PhiOS π café"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )

    receipt = GovernedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert receipt.status == "SUCCEEDED"
    ledger_entry = spine.ledger.recent(1)[0]
    assert ledger_entry["input_sha256"] == binding.payload_sha256


def test_effect_contract_drift_is_held_before_binding_claim(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"value": "effect-drift"}
    bound_capability = Capability(
        id="custom.effect-drift",
        name="Effect Drift",
        description="bound",
        permissions=("custom.execute",),
        effects=("external_state.read",),
        risk="low",
        version="1.0.0",
    )
    binding = _binding(plan, bound_capability, payload)

    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["custom.execute"],
    )
    runtime_capability = Capability(
        id="custom.effect-drift",
        name="Effect Drift",
        description="runtime",
        permissions=("custom.execute",),
        effects=("external_state.change",),
        risk="low",
        version="1.0.0",
    )
    spine.registry.register(runtime_capability)

    receipt = GovernedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "capability_contract_drift"
    assert spine.ledger.has_consumed_binding(binding.binding_sha256) is False


def test_executor_effect_mismatch_is_held_before_binding_claim(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"value": "executor-mismatch"}
    capability = Capability(
        id="custom.executor-effect-mismatch",
        name="Executor Effect Mismatch",
        description="test",
        permissions=("custom.execute",),
        effects=("external_state.read",),
        risk="low",
        version="1.0.0",
    )
    binding = _binding(plan, capability, payload)
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["custom.execute"],
    )
    spine.registry.register(capability)

    def handler(data: dict[str, object]) -> ArtifactResult:
        raise AssertionError(f"executor must not be entered: {data}")

    spine.executors.register(
        capability.id,
        handler,
        effects=("external_state.change",),
    )

    receipt = GovernedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == (
        "effect_boundary_capability_executor_effect_contract_mismatch"
    )
    assert spine.ledger.has_consumed_binding(binding.binding_sha256) is False


def test_partial_lease_provenance_is_rejected_before_binding_claim(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "partial-lease", "text": "must fail closed"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    handoff = GovernedExecutionHandoff()

    with pytest.raises(
        ExecutionHandoffContractError,
        match="lease provenance must provide all four SHA-256 digests",
    ):
        handoff.execute(
            plan=plan,
            binding=binding,
            payload=payload,
            spine=spine,
            action_lease_sha256="a" * 64,
        )

    retry = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )
    assert retry.status == "SUCCEEDED"


def test_malformed_complete_lease_provenance_is_rejected_before_binding_claim(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "bad-lease", "text": "digest validation"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    handoff = GovernedExecutionHandoff()

    with pytest.raises(
        ExecutionHandoffContractError,
        match="action_lease_sha256 must be a lowercase SHA-256 digest",
    ):
        handoff.execute(
            plan=plan,
            binding=binding,
            payload=payload,
            spine=spine,
            action_lease_sha256="A" * 64,
            authority_epoch_sha256="b" * 64,
            authorization_receipt_sha256="c" * 64,
            lease_verification_sha256="d" * 64,
        )

    retry = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
    )
    assert retry.status == "SUCCEEDED"
