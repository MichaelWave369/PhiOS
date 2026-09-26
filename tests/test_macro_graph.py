from __future__ import annotations

import pytest

from phios.macro_graph import (
    ApproveStep,
    CallStep,
    CheckpointStep,
    DoStep,
    ForEachStep,
    IfStep,
    LoopStep,
    MacroDefinition,
    MacroGraphContractError,
    MacroGraphPlanner,
    PlanOpcode,
)
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)


def _operation(value: str = "one") -> Operation:
    return Operation(
        operation_id="macro.test.write",
        operation_version="0.3.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "graph-test", "text": value},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _definition() -> MacroDefinition:
    return MacroDefinition(
        macro_id="macro:graph-test",
        macro_version="0.3.0",
        parameters=("items", "should_continue"),
        steps=(
            DoStep(_operation()),
            IfStep(
                condition_id="condition:continue",
                then_steps=(CheckpointStep(label="after-first-write"),),
                else_steps=(
                    CallStep(
                        macro_id="macro:fallback",
                        macro_version="1.0.0",
                        arguments={"reason": "condition-false"},
                    ),
                ),
            ),
            LoopStep(
                loop_id="retry-analysis",
                max_iterations=3,
                body=(DoStep(_operation("loop")),),
            ),
            ForEachStep(
                item_name="item",
                collection_ref="param:items",
                max_items=8,
                body=(
                    ApproveStep(
                        barrier_id="approve-item-write",
                        required_capabilities=("artifact.write",),
                        reason="Each real item write still requires authority.",
                    ),
                ),
            ),
        ),
    )


def test_graph_001_same_definition_produces_same_plan_hash() -> None:
    planner = MacroGraphPlanner()
    first = planner.plan(_definition())
    second = planner.plan(_definition())

    assert first.definition_sha256 == second.definition_sha256
    assert first.plan_sha256 == second.plan_sha256
    assert first.to_dict() == second.to_dict()


def test_graph_002_plan_contains_all_structured_primitives_in_order() -> None:
    plan = MacroGraphPlanner().plan(_definition())

    assert [instruction.opcode for instruction in plan.instructions] == [
        PlanOpcode.DO,
        PlanOpcode.IF_BEGIN,
        PlanOpcode.CHECKPOINT,
        PlanOpcode.ELSE,
        PlanOpcode.CALL,
        PlanOpcode.IF_END,
        PlanOpcode.LOOP_BEGIN,
        PlanOpcode.DO,
        PlanOpcode.LOOP_END,
        PlanOpcode.FOREACH_BEGIN,
        PlanOpcode.APPROVE,
        PlanOpcode.FOREACH_END,
    ]
    assert [instruction.index for instruction in plan.instructions] == list(
        range(len(plan.instructions))
    )


def test_graph_003_planning_and_approval_barriers_carry_zero_authority() -> None:
    definition = _definition()
    plan = MacroGraphPlanner().plan(definition)

    assert definition.operational_authority is False
    assert definition.action_authority is False
    assert definition.execution_authority is False
    assert plan.operational_authority is False
    assert plan.action_authority is False
    assert plan.execution_authority is False

    for instruction in plan.instructions:
        assert instruction.operational_authority is False
        assert instruction.action_authority is False
        assert instruction.execution_authority is False

    approval = next(
        item
        for item in plan.instructions
        if item.opcode is PlanOpcode.APPROVE
    )
    assert approval.payload["grants_authority"] is False
    assert approval.payload["required_capabilities"] == ["artifact.write"]


def test_graph_004_do_step_pins_exact_operation_hash() -> None:
    planner = MacroGraphPlanner()
    first = planner.plan(
        MacroDefinition(
            macro_id="macro:pin",
            macro_version="0.3.0",
            steps=(DoStep(_operation("one")),),
        )
    )
    second = planner.plan(
        MacroDefinition(
            macro_id="macro:pin",
            macro_version="0.3.0",
            steps=(DoStep(_operation("two")),),
        )
    )

    first_do = first.instructions[0]
    second_do = second.instructions[0]
    assert first_do.payload["operation_hash"] == _operation("one").operation_hash
    assert second_do.payload["operation_hash"] == _operation("two").operation_hash
    assert first.plan_sha256 != second.plan_sha256


def test_graph_005_loop_requires_explicit_finite_bound() -> None:
    definition = MacroDefinition(
        macro_id="macro:bad-loop",
        macro_version="0.3.0",
        steps=(
            LoopStep(
                loop_id="forever",
                max_iterations=0,
                body=(DoStep(_operation()),),
            ),
        ),
    )

    with pytest.raises(
        MacroGraphContractError,
        match="max_iterations must be between",
    ):
        MacroGraphPlanner().plan(definition)


def test_graph_006_foreach_requires_explicit_bounded_collection() -> None:
    definition = MacroDefinition(
        macro_id="macro:bad-foreach",
        macro_version="0.3.0",
        steps=(
            ForEachStep(
                item_name="item",
                collection_ref="param:items",
                max_items=10_001,
                body=(DoStep(_operation()),),
            ),
        ),
    )

    with pytest.raises(
        MacroGraphContractError,
        match="max_items must be between",
    ):
        MacroGraphPlanner().plan(definition)


def test_graph_007_call_arguments_are_canonical_across_dict_order() -> None:
    planner = MacroGraphPlanner()
    first = MacroDefinition(
        macro_id="macro:call",
        macro_version="0.3.0",
        steps=(
            CallStep(
                macro_id="macro:child",
                macro_version="1.0.0",
                arguments={"a": 1, "b": 2},
            ),
        ),
    )
    second = MacroDefinition(
        macro_id="macro:call",
        macro_version="0.3.0",
        steps=(
            CallStep(
                macro_id="macro:child",
                macro_version="1.0.0",
                arguments={"b": 2, "a": 1},
            ),
        ),
    )

    assert first.definition_sha256 == second.definition_sha256
    assert planner.plan(first).plan_sha256 == planner.plan(second).plan_sha256


def test_graph_008_empty_macro_is_rejected() -> None:
    definition = MacroDefinition(
        macro_id="macro:empty",
        macro_version="0.3.0",
        steps=(),
    )

    with pytest.raises(
        MacroGraphContractError,
        match="requires at least one step",
    ):
        MacroGraphPlanner().plan(definition)
