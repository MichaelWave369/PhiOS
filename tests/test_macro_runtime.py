from __future__ import annotations

from phios.macro_runtime import (
    AuthorityDecisionKind,
    CapabilityGrant,
    ExecutionMode,
    IdempotencyClass,
    InMemoryStateAdapter,
    MacroRuntime,
    Operation,
    ReplayClass,
    RollbackClass,
    RuntimeResultStatus,
    SideEffectClass,
)


def _grant(capability: str = "state.write") -> CapabilityGrant:
    return CapabilityGrant(
        grant_id=f"grant:{capability}",
        principal_id="operator:test",
        capability=capability,
    )


def _operation(**overrides: object) -> Operation:
    values: dict[str, object] = {
        "operation_id": "state.set",
        "operation_version": "0.1.0",
        "adapter_id": "memory.state",
        "action": "set",
        "inputs": {"key": "alpha", "value": 1},
        "required_capabilities": ("state.write",),
        "execution_modes_supported": (
            ExecutionMode.LIVE,
            ExecutionMode.DRY_RUN,
            ExecutionMode.REPLAY,
        ),
        "idempotency_class": IdempotencyClass.IDEMPOTENT,
        "replay_class": ReplayClass.DETERMINISTIC,
        "rollback_class": RollbackClass.REVERSIBLE,
        "side_effect_class": SideEffectClass.LOCAL_REVERSIBLE,
        "idempotency_key": "state.set:alpha:1",
    }
    values.update(overrides)
    return Operation(**values)  # type: ignore[arg-type]


def _runtime() -> tuple[MacroRuntime, InMemoryStateAdapter]:
    runtime = MacroRuntime()
    adapter = InMemoryStateAdapter()
    runtime.register_adapter(adapter)
    return runtime, adapter


def test_auth_001_positive_authority() -> None:
    runtime, _ = _runtime()
    operation = _operation()

    decision = runtime.authorize(
        principal_id="operator:test",
        operation=operation,
        grants=(_grant(),),
    )

    assert decision.decision is AuthorityDecisionKind.GRANTED
    assert decision.missing_capabilities == ()
    assert decision.matched_grants == ("grant:state.write",)


def test_auth_002_negative_authority_never_enters_adapter() -> None:
    runtime, adapter = _runtime()

    result = runtime.execute(
        principal_id="operator:test",
        operation=_operation(),
        grants=(),
    )

    assert result.authority.decision is AuthorityDecisionKind.DENIED
    assert result.status is RuntimeResultStatus.DENIED
    assert adapter.state == {}
    assert adapter.committed_effects == 0


def test_dry_001_dry_run_commits_zero_external_effects() -> None:
    runtime, adapter = _runtime()

    result = runtime.execute(
        principal_id="operator:test",
        operation=_operation(),
        grants=(_grant(),),
        mode=ExecutionMode.DRY_RUN,
    )

    assert result.status is RuntimeResultStatus.DRY_RUN
    assert result.receipt.committed_side_effect_count == 0
    assert adapter.state == {}
    assert adapter.committed_effects == 0


def test_idem_001_reexecution_commits_once() -> None:
    runtime, adapter = _runtime()
    operation = _operation()

    first = runtime.execute(
        principal_id="operator:test",
        operation=operation,
        grants=(_grant(),),
    )
    second = runtime.execute(
        principal_id="operator:test",
        operation=operation,
        grants=(_grant(),),
    )

    assert first.status is RuntimeResultStatus.SUCCEEDED
    assert second.status is RuntimeResultStatus.ALREADY_APPLIED
    assert adapter.committed_effects == 1
    assert adapter.state == {"alpha": 1}


def test_roll_001_restores_checkpoint_state() -> None:
    runtime, adapter = _runtime()
    adapter.state = {"existing": 7}
    before = adapter.state_hash()

    executed = runtime.execute(
        principal_id="operator:test",
        operation=_operation(),
        grants=(_grant(),),
    )
    rollback = runtime.rollback(receipt_id=executed.receipt.receipt_id)

    assert rollback.result_status is RuntimeResultStatus.ROLLED_BACK
    assert rollback.post_state_hash == before
    assert adapter.state == {"existing": 7}


def test_replay_001_deterministic_replay_matches_result_hash_without_effect() -> None:
    runtime, adapter = _runtime()
    operation = _operation()

    original = runtime.execute(
        principal_id="operator:test",
        operation=operation,
        grants=(_grant(),),
    )
    effect_count = adapter.committed_effects
    replay = runtime.replay(
        principal_id="operator:test",
        operation=operation,
        original_receipt_id=original.receipt.receipt_id,
        grants=(_grant(),),
    )

    assert replay.receipt.result_hash == original.receipt.result_hash
    assert replay.receipt.committed_side_effect_count == 0
    assert adapter.committed_effects == effect_count


def test_receipt_001_binds_operation_input_and_result_hashes() -> None:
    runtime, _ = _runtime()
    operation = _operation()

    result = runtime.execute(
        principal_id="operator:test",
        operation=operation,
        grants=(_grant(),),
    )

    assert result.receipt.operation_hash == operation.operation_hash
    assert result.receipt.input_hash == operation.input_hash
    assert len(result.receipt.result_hash) == 64
    assert len(result.receipt.receipt_hash) == 64
    assert result.receipt.grant_ids == ("grant:state.write",)
