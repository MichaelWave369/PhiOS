from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_runner import RunnerStatus
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.macro_start import (
    MacroRunStartGate,
    RunStartAdmissionPolicy,
    RunStartRequest,
    StartStatus,
    TriggerObservation,
)
from phios.spine.ledger import RealityLedger


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _operation(text: str = "triggered") -> Operation:
    return Operation(
        operation_id="macro.start.write",
        operation_version="0.8.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "trigger-test", "text": text},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _plan(text: str = "triggered"):
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:start-test",
            macro_version="0.8.0",
            steps=(DoStep(_operation(text)),),
        )
    )


def _observation(
    *,
    event_id: str = "event:001",
    source_id: str = "source:test-scheduler",
    trigger_type: str = "schedule",
) -> TriggerObservation:
    return TriggerObservation(
        observation_id=f"observation:{event_id}",
        trigger_type=trigger_type,
        source_id=source_id,
        source_event_id=event_id,
        observed_at="2026-09-26T23:00:00+00:00",
        payload_sha256=_sha(
            {
                "event_id": event_id,
                "source_id": source_id,
                "trigger_type": trigger_type,
            }
        ),
        evidence_ref_sha256s=("a" * 64,),
    )


def _request(
    *,
    run_id: str,
    plan,
    observation: TriggerObservation,
    request_id: str = "request:001",
) -> RunStartRequest:
    return RunStartRequest.build(
        request_id=request_id,
        run_id=run_id,
        plan=plan,
        observation=observation,
        requested_at="2026-09-26T23:00:01+00:00",
    )


def _policy(
    *,
    enabled: bool = True,
    source_ids: tuple[str, ...] = ("source:test-scheduler",),
    trigger_types: tuple[str, ...] = ("schedule",),
) -> RunStartAdmissionPolicy:
    return RunStartAdmissionPolicy(
        policy_id="policy:test-start",
        allowed_trigger_types=trigger_types,
        allowed_source_ids=source_ids,
        enabled=enabled,
    )


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def test_start_001_allowed_trigger_starts_zero_authority_run(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    plan = _plan()
    observation = _observation()
    request = _request(
        run_id="run:start-allowed",
        plan=plan,
        observation=observation,
    )

    admitted = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(),
        plan=plan,
    )

    assert admitted.receipt.status is StartStatus.STARTED
    assert admitted.receipt.reason == "start_request_admitted"
    assert admitted.run is not None
    assert admitted.run.state.status is RunnerStatus.WAITING_OPERATION
    assert admitted.receipt.run_state_sha256 == admitted.run.state.state_sha256
    assert admitted.receipt.journal_head_sha256 == (
        admitted.run.head_entry_sha256
    )
    assert admitted.receipt.operational_authority is False
    assert admitted.receipt.action_authority is False
    assert admitted.receipt.execution_authority is False

    assert ledger.recent() == []
    rows = ledger.recent_macro_run_start_receipts(1)
    assert rows[0]["status"] == "STARTED"
    assert rows[0]["run_status"] == "WAITING_OPERATION"


def test_start_002_same_trigger_cannot_start_same_macro_twice(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    gate = MacroRunStartGate(ledger)
    plan = _plan()
    observation = _observation()

    first = gate.admit(
        observation=observation,
        request=_request(
            run_id="run:dedupe-one",
            plan=plan,
            observation=observation,
            request_id="request:dedupe-one",
        ),
        policy=_policy(),
        plan=plan,
    )
    second = gate.admit(
        observation=observation,
        request=_request(
            run_id="run:dedupe-two",
            plan=plan,
            observation=observation,
            request_id="request:dedupe-two",
        ),
        policy=_policy(),
        plan=plan,
    )

    assert first.receipt.status is StartStatus.STARTED
    assert second.receipt.status is StartStatus.HELD
    assert second.receipt.reason == "trigger_already_admitted"
    assert second.run is None
    assert ledger.macro_run_journal_entries(run_id="run:dedupe-two") == []


def test_start_003_existing_run_id_blocks_different_trigger(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    gate = MacroRunStartGate(ledger)
    plan = _plan()
    first_observation = _observation(event_id="event:first")
    second_observation = _observation(event_id="event:second")

    first = gate.admit(
        observation=first_observation,
        request=_request(
            run_id="run:shared",
            plan=plan,
            observation=first_observation,
            request_id="request:first",
        ),
        policy=_policy(),
        plan=plan,
    )
    second = gate.admit(
        observation=second_observation,
        request=_request(
            run_id="run:shared",
            plan=plan,
            observation=second_observation,
            request_id="request:second",
        ),
        policy=_policy(),
        plan=plan,
    )

    assert first.receipt.status is StartStatus.STARTED
    assert second.receipt.status is StartStatus.HELD
    assert second.receipt.reason == "run_id_exists"
    assert second.run is None


def test_start_004_disallowed_source_is_rejected_without_run(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    plan = _plan()
    observation = _observation(source_id="source:not-allowed")
    request = _request(
        run_id="run:source-rejected",
        plan=plan,
        observation=observation,
    )

    result = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(),
        plan=plan,
    )

    assert result.receipt.status is StartStatus.REJECTED
    assert result.receipt.reason == "trigger_source_not_allowed"
    assert result.run is None
    assert ledger.macro_run_journal_entries(
        run_id="run:source-rejected"
    ) == []


def test_start_005_request_scope_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_plan = _plan("one")
    second_plan = _plan("two")
    observation = _observation()
    request = _request(
        run_id="run:scope-rejected",
        plan=first_plan,
        observation=observation,
    )

    result = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(),
        plan=second_plan,
    )

    assert result.receipt.status is StartStatus.REJECTED
    assert result.receipt.reason == "macro_plan_scope_mismatch"
    assert result.run is None


def test_start_006_disabled_policy_holds_without_claiming_start(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    plan = _plan()
    observation = _observation()
    request = _request(
        run_id="run:policy-held",
        plan=plan,
        observation=observation,
    )

    held = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(enabled=False),
        plan=plan,
    )
    assert held.receipt.status is StartStatus.HELD
    assert held.receipt.reason == "start_policy_disabled"

    retried = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(enabled=True),
        plan=plan,
    )
    assert retried.receipt.status is StartStatus.STARTED


def test_start_007_run_id_claim_failure_releases_trigger_dedupe(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    plan = _plan()
    observation = _observation()
    request = _request(
        run_id="run:preclaimed",
        plan=plan,
        observation=observation,
    )

    assert ledger.claim_macro_run_id(request.run_id_sha256) is True
    held = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(),
        plan=plan,
    )

    assert held.receipt.status is StartStatus.HELD
    assert held.receipt.reason == "run_id_claimed"
    assert held.run is None

    ledger.release_macro_run_id_claim(request.run_id_sha256)
    retried = MacroRunStartGate(ledger).admit(
        observation=observation,
        request=request,
        policy=_policy(),
        plan=plan,
    )
    assert retried.receipt.status is StartStatus.STARTED


def test_start_008_observation_request_and_policy_are_all_zero_authority(
    tmp_path: Path,
) -> None:
    plan = _plan()
    observation = _observation()
    request = _request(
        run_id="run:zero-authority",
        plan=plan,
        observation=observation,
    )
    policy = _policy()

    assert observation.operational_authority is False
    assert observation.action_authority is False
    assert observation.execution_authority is False
    assert request.operational_authority is False
    assert request.action_authority is False
    assert request.execution_authority is False
    assert policy.operational_authority is False
    assert policy.action_authority is False
    assert policy.execution_authority is False

    result = MacroRunStartGate(_ledger(tmp_path)).admit(
        observation=observation,
        request=request,
        policy=policy,
        plan=plan,
    )
    assert result.run is not None
    assert result.run.state.status is RunnerStatus.WAITING_OPERATION
