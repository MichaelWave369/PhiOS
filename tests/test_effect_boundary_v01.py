from pathlib import Path

from phios.spine.effects import EffectBoundaryPolicy
from phios.spine.executor import ArtifactResult
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine


def _artifact_handler(root: Path, calls: list[str]):
    def handler(payload: dict[str, object]) -> ArtifactResult:
        calls.append(str(payload.get("value", "")))
        root.mkdir(parents=True, exist_ok=True)
        path = root / "result.txt"
        path.write_text("effect-test", encoding="utf-8")
        import hashlib

        return ArtifactResult(
            path=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    return handler


def test_builtin_effect_receipt_precedes_permission_and_action_receipts(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("artifact.write",),
        task_id="effect-built-in",
    )

    receipt = spine.run(
        "commons.text_artifact",
        {"name": "proof", "text": "effects"},
    )

    assert receipt.execution_status == "succeeded"
    rows = spine.mandala_ledger.recent(3)
    assert [row["receipt_type"] for row in rows] == [
        "EffectBoundaryReceipt",
        "GateReceipt",
        "ActionReceipt",
    ]
    effect, gate, action = rows
    assert effect["status"] == "ACCEPTED"
    assert effect["capability_effects"] == ["filesystem.change"]
    assert effect["executor_effects"] == ["filesystem.change"]
    assert effect["active_effects"] == ["filesystem.change"]
    assert effect["effect_contract_match"] is True
    assert effect["classification_complete"] is True
    assert effect["action_authority"] is False
    assert effect["execution_authority"] is False
    assert len(effect["receipt_sha256"]) == 64
    assert gate["parent_receipt_id"] == effect["receipt_id"]
    assert action["parent_receipt_id"] == gate["receipt_id"]


def test_missing_effect_classification_blocks_before_executor(tmp_path: Path) -> None:
    calls: list[str] = []
    capability = Capability(
        id="custom.missing-effects",
        name="Missing Effects",
        description="Intentionally unclassified",
        permissions=("custom.execute",),
        effects=(),
        risk="low",
        version="1.0.0",
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("custom.execute",),
    )
    spine.registry.register(capability)
    spine.executors.register(
        capability.id,
        _artifact_handler(tmp_path / "custom", calls),
        effects=(),
    )

    receipt = spine.run(capability.id, {"value": "should-not-run"})

    assert receipt.permission_status == "denied"
    assert receipt.execution_status == "not_executed"
    assert receipt.error == "effect_boundary:capability_effect_classification_missing"
    assert calls == []
    effect = spine.mandala_ledger.recent(3)[0]
    assert effect["receipt_type"] == "EffectBoundaryReceipt"
    assert effect["status"] == "BLOCKED"


def test_capability_executor_effect_mismatch_blocks_before_executor(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    capability = Capability(
        id="custom.effect-mismatch",
        name="Effect Mismatch",
        description="Capability says read while executor can change state",
        permissions=("custom.execute",),
        effects=("external_state.read",),
        risk="low",
        version="1.0.0",
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("custom.execute",),
    )
    spine.registry.register(capability)
    spine.executors.register(
        capability.id,
        _artifact_handler(tmp_path / "custom", calls),
        effects=("external_state.change",),
    )

    receipt = spine.run(capability.id, {"value": "mismatch"})

    assert receipt.execution_status == "not_executed"
    assert receipt.error == (
        "effect_boundary:capability_executor_effect_contract_mismatch"
    )
    assert calls == []


def test_read_risk_label_cannot_hide_active_network_effect(tmp_path: Path) -> None:
    calls: list[str] = []
    capability = Capability(
        id="custom.read-labelled-network",
        name="Read Status",
        description="A method label is not an effect proof",
        permissions=("custom.execute",),
        effects=("network.request",),
        risk="read",
        version="1.0.0",
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("custom.execute",),
    )
    spine.registry.register(capability)
    spine.executors.register(
        capability.id,
        _artifact_handler(tmp_path / "custom", calls),
        effects=("network.request",),
    )

    receipt = spine.run(capability.id, {"value": "get-looking-action"})

    assert receipt.execution_status == "not_executed"
    assert receipt.error == (
        "effect_boundary:read_risk_label_conflicts_with_active_effects"
    )
    assert calls == []
    effect = spine.mandala_ledger.recent(3)[0]
    assert effect["semantic_read_label_conflict"] is True
    assert effect["active_effects"] == ["network.request"]


def test_effect_policy_treats_external_change_as_active_even_with_read_name() -> None:
    capability = Capability(
        id="custom.get",
        name="GET Account",
        description="Name resembles a read operation",
        permissions=("custom.execute",),
        effects=("external_state.change", "network.request"),
        risk="low",
        version="1.0.0",
    )

    decision = EffectBoundaryPolicy().evaluate(
        capability,
        executor_effects=("network.request", "external_state.change"),
    )

    assert decision.allowed is True
    assert decision.status == "CLASSIFIED"
    assert decision.active_effects == (
        "external_state.change",
        "network.request",
    )
    assert decision.semantic_read_label_conflict is False
