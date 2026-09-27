from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from phios.action_lease import ActionLease
from phios.authority_epoch import AuthorityEpoch
from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_action_binding import (
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_plan_adoption import GovernedPlanAdoptionGate
from phios.core.leased_execution_handoff import LeaseVerificationEvidence
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.macro_desktop_interaction import (
    DESKTOP_CLICK_CAPABILITY_ID,
    DesktopClickRequest,
    DesktopInteractionContractError,
    DesktopInteractionHeldError,
    DesktopInteractionOutcome,
    GovernedDesktopClickExecutor,
    MouseInjectionResult,
    OperatorInputSnapshot,
    WindowsDesktopFrameProvider,
    WindowsMouseInjector,
    WindowsOperatorInputProbe,
    install_desktop_click_capability,
)
from phios.macro_dispatcher import GovernedDoDispatcher
from phios.macro_ghostwalk import SemanticTarget
from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_interaction_guard import PixelAnchor, WindowFrame
from phios.macro_runner import MacroRunner, RunnerInputs, RunnerStatus
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.macro_uia_revalidation import SemanticReplayRevalidator
from phios.macro_windows_uia import UiaElementSnapshot
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.spine.executor import OutcomeUnknownError
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine

AUTHORIZATION = "a" * 64
VERIFICATION_RECEIPT = "b" * 64
ENFORCEMENT_EVIDENCE = "c" * 64
POLICY = "d" * 64
TITLE = "e" * 64


def _frame(
    *,
    captured_at: str = "2026-09-27T02:30:00+00:00",
    pid: int = 4242,
    title: str = TITLE,
    left: int = 100,
    top: int = 50,
    width: int = 800,
    height: int = 600,
    foreground: bool = True,
) -> WindowFrame:
    return WindowFrame(
        process_id=f"pid:{pid}",
        window_title_sha256=title,
        left_px=left,
        top_px=top,
        width_px=width,
        height_px=height,
        display_scale_percent=100,
        foreground=foreground,
        captured_at=captured_at,
    )


def _anchor(frame: WindowFrame | None = None) -> PixelAnchor:
    source = frame or _frame()
    return PixelAnchor.from_observed_click(
        anchor_id="anchor:desktop-click",
        frame=source,
        x_px=500,
        y_px=350,
        semantic_hint="Save",
    )


def _anchor_dict(anchor: PixelAnchor) -> dict[str, object]:
    payload = anchor.body_dict()
    payload["anchor_sha256"] = anchor.anchor_sha256
    return payload


def _semantic_target() -> SemanticTarget:
    return SemanticTarget(
        provider="windows.uia.v0.16",
        selector=json.dumps(
            {
                "automation_id": "save-button",
                "control_type": 50000,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        role="uia.control_type.50000",
        name_hint="Save",
    )


def _payload(
    *,
    strategy: str = "SEMANTIC",
    semantic: SemanticTarget | None = None,
    anchor: PixelAnchor | None = None,
) -> dict[str, object]:
    pixel = anchor or _anchor()
    target = semantic
    if strategy == "SEMANTIC" and target is None:
        target = _semantic_target()
    return {
        "observation_sha256": "f" * 64,
        "preferred_strategy": strategy,
        "process_id": pixel.process_id,
        "window_title_sha256": pixel.window_title_sha256,
        "pixel_anchor": _anchor_dict(pixel),
        "semantic_target": (
            None if target is None else target.to_dict()
        ),
        "absolute_pixel_is_evidence_only": True,
        "guard_required": True,
    }


def _candidate(
    *,
    pid: int = 4242,
    left: int = 450,
    top: int = 320,
    right: int = 550,
    bottom: int = 380,
) -> UiaElementSnapshot:
    return UiaElementSnapshot(
        process_id=pid,
        automation_id="save-button",
        name_hint="Save",
        control_type=50000,
        class_name="Button",
        framework_id="Win32",
        enabled=True,
        offscreen=False,
        is_password=False,
        bounding_left=left,
        bounding_top=top,
        bounding_right=right,
        bounding_bottom=bottom,
    )


class StaticReplayBackend:
    backend_id = "test.desktop-uia"

    def __init__(
        self,
        candidates: tuple[UiaElementSnapshot, ...] = (_candidate(),),
    ) -> None:
        self.candidates = candidates
        self.calls = 0

    def find_matches(
        self,
        *,
        frame: WindowFrame,
        selector,
    ) -> tuple[UiaElementSnapshot, ...]:
        self.calls += 1
        return self.candidates


class SequenceFrameProvider:
    provider_id = "test.desktop-frame"

    def __init__(
        self,
        *,
        current: tuple[WindowFrame | None, ...],
        point: tuple[WindowFrame | None, ...] = (),
    ) -> None:
        self._current = list(current)
        self._point = list(point)
        self.current_calls = 0
        self.point_calls = 0

    @staticmethod
    def _next(
        values: list[WindowFrame | None],
    ) -> WindowFrame | None:
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        return values.pop(0)

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None:
        self.current_calls += 1
        return self._next(self._current)

    def frame_at_point(
        self,
        *,
        x_px: int,
        y_px: int,
        observed_at: str,
    ) -> WindowFrame | None:
        self.point_calls += 1
        if self._point:
            return self._next(self._point)
        return self._next(self._current)


class SequenceInputProbe:
    probe_id = "test.input-probe"

    def __init__(
        self,
        *snapshots: OperatorInputSnapshot,
    ) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self) -> OperatorInputSnapshot:
        self.calls += 1
        if not self._snapshots:
            raise RuntimeError("input snapshot sequence exhausted")
        if len(self._snapshots) == 1:
            return self._snapshots[0]
        return self._snapshots.pop(0)


class StaticInjector:
    injector_id = "test.injector"

    def __init__(
        self,
        inserted_events: int = 3,
    ) -> None:
        self.inserted_events = inserted_events
        self.calls: list[tuple[int, int]] = []

    def click(
        self,
        *,
        x_px: int,
        y_px: int,
    ) -> MouseInjectionResult:
        self.calls.append((x_px, y_px))
        return MouseInjectionResult(
            inserted_events=self.inserted_events
        )


class SequenceClock:
    def __init__(self) -> None:
        self._counter = 0

    def __call__(self) -> str:
        self._counter += 1
        return f"2026-09-27T02:30:{self._counter:02d}+00:00"


def _probe(
    *,
    token: int = 100,
    x: int = 20,
    y: int = 20,
) -> OperatorInputSnapshot:
    return OperatorInputSnapshot(
        token=token,
        pointer_x_px=x,
        pointer_y_px=y,
    )


def _executor(
    tmp_path: Path,
    *,
    strategy: str = "SEMANTIC",
    current_frames: tuple[WindowFrame | None, ...] | None = None,
    point_frames: tuple[WindowFrame | None, ...] | None = None,
    probes: tuple[OperatorInputSnapshot, ...] | None = None,
    injector: StaticInjector | None = None,
    candidates: tuple[UiaElementSnapshot, ...] = (_candidate(),),
):
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["ui.interact"],
    )
    frames = current_frames or (
        _frame(captured_at="2026-09-27T02:30:01+00:00"),
        _frame(captured_at="2026-09-27T02:30:02+00:00"),
        _frame(captured_at="2026-09-27T02:30:03+00:00"),
    )
    points = point_frames or (
        _frame(captured_at="2026-09-27T02:30:02+00:00"),
        _frame(captured_at="2026-09-27T02:30:02+00:00"),
    )
    frame_provider = SequenceFrameProvider(
        current=frames,
        point=points,
    )
    input_probe = SequenceInputProbe(
        *(probes or (_probe(), _probe(), _probe()))
    )
    actual_injector = injector or StaticInjector()
    replay = SemanticReplayRevalidator(
        ledger=spine.ledger,
        backend=StaticReplayBackend(candidates),
    )
    executor = GovernedDesktopClickExecutor(
        spine=spine,
        frame_provider=frame_provider,
        input_probe=input_probe,
        injector=actual_injector,
        semantic_revalidator=replay,
        clock=SequenceClock(),
    )
    capability = install_desktop_click_capability(
        spine=spine,
        executor=executor,
    )
    return (
        spine,
        executor,
        capability,
        frame_provider,
        input_probe,
        actual_injector,
    )


def test_desktop_001_semantic_clear_performs_one_bounded_click(
    tmp_path: Path,
) -> None:
    spine, executor, _, _, _, injector = _executor(tmp_path)

    artifact = executor.execute(_payload())

    assert injector.calls == [(500, 350)]
    assert artifact.path.exists()
    row = spine.ledger.recent_desktop_interaction_receipts(1)[0]
    assert row["outcome"] == "SUCCEEDED"
    assert row["target_mode"] == "SEMANTIC"
    assert row["effect_performed"] is True
    assert row["resolved_x_px"] == 500
    assert row["resolved_y_px"] == 350
    assert row["inserted_events"] == 3


def test_desktop_002_pixel_guard_performs_window_relative_click(
    tmp_path: Path,
) -> None:
    spine, executor, _, _, _, injector = _executor(
        tmp_path,
        strategy="WINDOW_RELATIVE_PIXEL",
    )

    artifact = executor.execute(
        _payload(
            strategy="WINDOW_RELATIVE_PIXEL",
            semantic=None,
        )
    )

    assert artifact.path.exists()
    assert injector.calls == [(500, 350)]
    row = spine.ledger.recent_desktop_interaction_receipts(1)[0]
    assert row["outcome"] == "SUCCEEDED"
    assert row["target_mode"] == "WINDOW_RELATIVE_PIXEL"
    guards = spine.ledger.recent_interaction_guard_receipts(1)
    assert guards[0]["decision"] == "CLEAR"


def test_desktop_003_operator_input_change_holds_before_injection(
    tmp_path: Path,
) -> None:
    injector = StaticInjector()
    spine, executor, _, _, _, _ = _executor(
        tmp_path,
        probes=(
            _probe(token=100),
            _probe(token=101),
        ),
        injector=injector,
    )

    with pytest.raises(
        DesktopInteractionHeldError,
        match="operator_input_changed",
    ):
        executor.execute(_payload())

    assert injector.calls == []
    row = spine.ledger.recent_desktop_interaction_receipts(1)[0]
    assert row["outcome"] == "HELD"
    assert row["effect_performed"] is False


def test_desktop_004_foreground_geometry_drift_holds(
    tmp_path: Path,
) -> None:
    injector = StaticInjector()
    spine, executor, _, _, _, _ = _executor(
        tmp_path,
        current_frames=(
            _frame(
                captured_at="2026-09-27T02:30:01+00:00",
                width=800,
            ),
            _frame(
                captured_at="2026-09-27T02:30:02+00:00",
                width=801,
            ),
        ),
        probes=(_probe(), _probe()),
        injector=injector,
    )

    with pytest.raises(
        DesktopInteractionHeldError,
        match="foreground_frame_changed",
    ):
        executor.execute(_payload())

    assert injector.calls == []
    assert (
        spine.ledger.recent_desktop_interaction_receipts(1)[0][
            "reason"
        ]
        == "foreground_frame_changed_before_injection"
    )


def test_desktop_005_overlay_at_resolved_point_holds(
    tmp_path: Path,
) -> None:
    injector = StaticInjector()
    wrong = _frame(
        captured_at="2026-09-27T02:30:02+00:00",
        pid=9999,
        title="9" * 64,
    )
    spine, executor, _, _, _, _ = _executor(
        tmp_path,
        point_frames=(wrong,),
        probes=(_probe(), _probe()),
        injector=injector,
    )

    with pytest.raises(
        DesktopInteractionHeldError,
        match="unexpected_overlay",
    ):
        executor.execute(_payload())

    assert injector.calls == []
    assert (
        spine.ledger.recent_desktop_interaction_receipts(1)[0][
            "reason"
        ]
        == "unexpected_overlay_at_resolved_target"
    )


def test_desktop_006_semantic_ambiguity_holds(
    tmp_path: Path,
) -> None:
    injector = StaticInjector()
    spine, executor, _, _, _, _ = _executor(
        tmp_path,
        candidates=(_candidate(), _candidate()),
        probes=(_probe(), _probe()),
        injector=injector,
    )

    with pytest.raises(
        DesktopInteractionHeldError,
        match="semantic_revalidation_target_ambiguous",
    ):
        executor.execute(_payload())

    assert injector.calls == []
    semantic = spine.ledger.recent_semantic_revalidation_receipts(1)[0]
    assert semantic["decision"] == "HOLD"
    assert semantic["reason"] == "TARGET_AMBIGUOUS"


def test_desktop_007_partial_injection_is_outcome_unknown(
    tmp_path: Path,
) -> None:
    injector = StaticInjector(inserted_events=2)
    spine, executor, _, _, _, _ = _executor(
        tmp_path,
        injector=injector,
    )

    with pytest.raises(
        OutcomeUnknownError,
        match="partial input sequence",
    ):
        executor.execute(_payload())

    row = spine.ledger.recent_desktop_interaction_receipts(1)[0]
    assert row["outcome"] == "OUTCOME_UNKNOWN"
    assert row["effect_performed"] is None
    assert row["inserted_events"] == 2


def test_desktop_008_zero_injection_is_failed(
    tmp_path: Path,
) -> None:
    injector = StaticInjector(inserted_events=0)
    spine, executor, _, _, _, _ = _executor(
        tmp_path,
        injector=injector,
    )

    with pytest.raises(
        RuntimeError,
        match="inserted zero events",
    ):
        executor.execute(_payload())

    row = spine.ledger.recent_desktop_interaction_receipts(1)[0]
    assert row["outcome"] == "FAILED"
    assert row["effect_performed"] is False
    assert row["inserted_events"] == 0


def test_desktop_009_payload_cannot_disable_guard() -> None:
    payload = _payload()
    payload["guard_required"] = False

    with pytest.raises(
        DesktopInteractionContractError,
        match="requires guard",
    ):
        DesktopClickRequest.from_payload(payload)


def _route_receipt() -> FieldAwareRouteReceipt:
    body = {
        "schema": "phios.field_aware_route_receipt.v0.4",
        "status": "found",
        "field_law_sha256": "1" * 64,
        "field_state_sha256": "2" * 64,
        "field_revision": 0,
        "bindings": [],
        "path_receipt_sha256": "3" * 64,
        "path_ids": ["A", "B"],
        "total_cost": 1.0,
        "optimality_scope": (
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        "action_authority": False,
    }
    digest = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return FieldAwareRouteReceipt(
        schema="phios.field_aware_route_receipt.v0.4",
        status="found",
        field_law_sha256="1" * 64,
        field_state_sha256="2" * 64,
        field_revision=0,
        bindings=(),
        path_receipt_sha256="3" * 64,
        path_ids=("A", "B"),
        total_cost=1.0,
        optimality_scope=(
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        action_authority=False,
        receipt_sha256=digest,
    )


def _plan_state():
    return GovernedPlanAdoptionGate().initialize_plan(
        plan_id="desktop-click-plan",
        route_receipt=_route_receipt(),
    )


def _binding(
    plan,
    capability: Capability,
    payload: dict[str, object],
):
    binder = GovernedActionBinder()
    payload_sha = binder.payload_sha256(payload)
    grant = ActionBindingGrant(
        grant_id="bind-desktop-click-001",
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


def _authority_epoch() -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("ui.interact",),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-ui-interact",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="ui.interact",
                authority_source="operator-ledger",
                effective_at="2026-09-27T02:20:00+00:00",
                expires_at="2026-09-27T04:30:00+00:00",
            ),
        ),
        observed_at="2026-09-27T02:21:00+00:00",
    )


def _lease(binding) -> ActionLease:
    intent = EffectIntent.build(
        capability_id=binding.capability_id,
        capability_version=binding.capability_version,
        payload_sha256=binding.payload_sha256,
        declared_at="2026-09-27T02:22:00+00:00",
        effects_declared=binding.effects_declared,
    )
    rule = EnforcementRule.build(
        rule_id="desktop-click-bounded",
        effect_scope=("display.control", "filesystem.change"),
        constraint=(
            "one revalidated click plus its governed receipt artifact"
        ),
        layer="application_contract",
        boundary="process_boundary",
        status="enforced",
        mechanism="single-use leased desktop executor contract",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )
    profile = EnforcementProfile.build(
        intent=intent,
        rules=(rule,),
    )
    return ActionLease.issue(
        principal_id="operator:michael",
        issuer_id="authority-broker:test",
        authorization_receipt_sha256=AUTHORIZATION,
        intent=intent,
        enforcement=profile,
        authority_epoch=_authority_epoch(),
        permissions_authorized=binding.permissions_requested,
        accepted_unenforced_effects=(),
        issued_at="2026-09-27T02:22:00+00:00",
        valid_from="2026-09-27T02:22:00+00:00",
        valid_until="2026-09-27T04:00:00+00:00",
    )


def _verification(lease: ActionLease) -> LeaseVerificationEvidence:
    return LeaseVerificationEvidence(
        lease_sha256=lease.action_lease_sha256,
        issuer_id=lease.issuer_id,
        authorization_receipt_sha256=(
            lease.authorization_receipt_sha256
        ),
        verifier_id="test-authority-verifier",
        verification_receipt_sha256=VERIFICATION_RECEIPT,
        accepted=True,
    )


def _operation(payload: dict[str, object]) -> Operation:
    return Operation(
        operation_id="ghostwalk.click.0",
        operation_version="0.13.0",
        adapter_id="desktop.interaction",
        action="click",
        inputs=dict(payload),
        required_capabilities=("ui.interact",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.UNKNOWN,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.UNKNOWN,
    )


def test_desktop_010_full_macro_lease_spine_click_path(
    tmp_path: Path,
) -> None:
    (
        spine,
        _executor_instance,
        capability,
        _frames,
        _probe_instance,
        injector,
    ) = _executor(tmp_path)
    assert capability.id == DESKTOP_CLICK_CAPABILITY_ID

    payload = _payload()
    operation = _operation(payload)
    macro_plan = MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:desktop-click",
            macro_version="0.18.0",
            steps=(DoStep(operation),),
        )
    )
    runner = MacroRunner()
    waiting = runner.advance(
        macro_plan,
        runner.start(macro_plan),
    )
    assert waiting.status is RunnerStatus.WAITING_OPERATION

    plan = _plan_state()
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    dispatcher = GovernedDoDispatcher()
    package = dispatcher.package(
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
    )

    dispatched = dispatcher.dispatch(
        work_package=package,
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=(
            lease.authority_epoch_sha256
        ),
        checked_at="2026-09-27T02:23:00+00:00",
    )

    assert injector.calls == [(500, 350)]
    assert dispatched.macro_spine_receipt.status == "SUCCEEDED"
    assert dispatched.operation_resolution.status.value == "SUCCEEDED"
    completed = runner.advance(
        macro_plan,
        waiting,
        RunnerInputs(
            operations=(dispatched.operation_resolution,),
        ),
    )
    assert completed.status is RunnerStatus.COMPLETED

    execution = spine.ledger.recent(1)[0]
    assert execution["capability_id"] == DESKTOP_CLICK_CAPABILITY_ID
    assert execution["execution_status"] == "succeeded"
    assert execution["permission_status"] == "allowed"
    assert Path(str(execution["artifact_path"])).exists()

    desktop = spine.ledger.recent_desktop_interaction_receipts(1)[0]
    assert desktop["outcome"] == "SUCCEEDED"
    macro = spine.ledger.recent_macro_receipts(1)[0]
    assert macro["status"] == "SUCCEEDED"
    dispatch = spine.ledger.recent_macro_dispatch_receipts(1)[0]
    assert dispatch["resolution_status"] == "SUCCEEDED"


def test_desktop_011_windows_components_reject_non_windows(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract test")

    for factory in (
        WindowsDesktopFrameProvider,
        WindowsOperatorInputProbe,
        WindowsMouseInjector,
    ):
        with pytest.raises(
            DesktopInteractionContractError,
            match="requires Windows",
        ):
            factory()

    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["ui.interact"],
    )
    with pytest.raises(
        DesktopInteractionContractError,
        match="requires Windows",
    ):
        GovernedDesktopClickExecutor.from_windows(spine=spine)
