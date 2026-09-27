from __future__ import annotations

from types import SimpleNamespace

from phios.macro_action_lease_service import (
    GhostWalkLeaseReadiness,
    GhostWalkLeaseReadinessReason,
)
from phios.macro_authorization_console import (
    GhostWalkAuthorizationConsoleService,
)
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecision,
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationReadiness,
    GhostWalkAuthorizationReadinessReason,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadiness,
    GhostWalkBindingReadinessReason,
)

TARGET = "a" * 64
REQUEST = "b" * 64
DECISION = "c" * 64
MAPPING = "d" * 64
MAPPING_SET = "e" * 64
OBSERVATION = "f" * 64
BINDING = "1" * 64
PAYLOAD = "2" * 64
POLICY = "3" * 64
POLICY_SET = "4" * 64
PROFILE = "5" * 64
EPOCH = "6" * 64
LEASE = "7" * 64
LEASE_RECORD = "8" * 64


def _decision() -> GhostWalkAuthorizationDecision:
    return GhostWalkAuthorizationDecision(
        authority_request_sha256=REQUEST,
        target_inference_receipt_sha256=TARGET,
        admission_receipt_sha256="9" * 64,
        accepted_intent_revision_sha256="0" * 64,
        policy_profile_sha256="a" * 64,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        authorizer_id="operator:local",
        decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        decision_sequence=0,
        previous_decision_sha256=None,
        decided_at="2026-09-27T21:30:00+00:00",
        authorization_granted=True,
        request_resolved=True,
    )


class FakeAuthorization:
    def __init__(self) -> None:
        self.item: GhostWalkAuthorizationDecision | None = None
        self.recorded: list[GhostWalkAuthorizationDecisionKind] = []

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationReadiness:
        assert target_inference_receipt_sha256 == TARGET
        if self.item is None:
            return GhostWalkAuthorizationReadiness(
                target_inference_receipt_sha256=TARGET,
                authority_request_sha256=REQUEST,
                latest_decision_sha256=None,
                latest_decision=None,
                ready=True,
                reason=GhostWalkAuthorizationReadinessReason.READY,
                authorization_granted=False,
            )
        return GhostWalkAuthorizationReadiness(
            target_inference_receipt_sha256=TARGET,
            authority_request_sha256=REQUEST,
            latest_decision_sha256=(
                self.item.authorization_decision_sha256
            ),
            latest_decision=self.item.decision.value,
            ready=False,
            reason=GhostWalkAuthorizationReadinessReason.DECISION_FINAL,
            authorization_granted=self.item.authorization_granted,
        )

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationDecision | None:
        assert target_inference_receipt_sha256 == TARGET
        return self.item

    def record(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authority_request_sha256: str,
        expected_previous_decision_sha256: str | None,
        decision: GhostWalkAuthorizationDecisionKind,
        decision_note: str | None = None,
        decided_at: str | None = None,
    ) -> GhostWalkAuthorizationDecision:
        assert target_inference_receipt_sha256 == TARGET
        assert expected_authority_request_sha256 == REQUEST
        assert expected_previous_decision_sha256 is None
        assert decision_note == "human approved"
        assert decided_at is None
        self.recorded.append(decision)
        self.item = _decision()
        return self.item


class FakeBindings:
    def __init__(self) -> None:
        self.created = False

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkBindingReadiness:
        assert target_inference_receipt_sha256 == TARGET
        return GhostWalkBindingReadiness(
            target_inference_receipt_sha256=TARGET,
            authorization_decision_sha256=DECISION,
            mapping_set_sha256=MAPPING_SET,
            selected_mapping_sha256=MAPPING,
            action_observation_sha256=OBSERVATION,
            existing_binding_sha256=BINDING if self.created else None,
            ready=not self.created,
            reason=(
                GhostWalkBindingReadinessReason.BINDING_ALREADY_EXISTS
                if self.created
                else GhostWalkBindingReadinessReason.READY
            ),
        )

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> object | None:
        assert target_inference_receipt_sha256 == TARGET
        return _fake_binding() if self.created else None

    def create(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authorization_decision_sha256: str,
        expected_mapping_sha256: str,
        expected_mapping_set_sha256: str,
        bound_at: str,
    ) -> object:
        assert target_inference_receipt_sha256 == TARGET
        assert expected_authorization_decision_sha256 == DECISION
        assert expected_mapping_sha256 == MAPPING
        assert expected_mapping_set_sha256 == MAPPING_SET
        assert bound_at
        self.created = True
        return _fake_binding()


def _fake_binding() -> object:
    return SimpleNamespace(
        executable_binding_sha256=BINDING,
        authorization_decision_sha256=DECISION,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        mapping_id="ghostwalk.open-network-adapter.desktop-click.v1",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        payload_sha256=PAYLOAD,
        permissions_required=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        bound_at="2026-09-27T21:31:00+00:00",
    )


class FakeLeases:
    def __init__(self) -> None:
        self.issued = False

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkLeaseReadiness:
        assert target_inference_receipt_sha256 == TARGET
        return GhostWalkLeaseReadiness(
            target_inference_receipt_sha256=TARGET,
            executable_binding_sha256=BINDING,
            policy_sha256=POLICY,
            policy_set_sha256=POLICY_SET,
            enforcement_profile_sha256=PROFILE,
            authority_epoch_sha256=EPOCH,
            required_permissions=("ui.interact",),
            missing_permissions=(),
            unenforced_effects=(),
            accepted_unenforced_effects=(),
            existing_action_lease_sha256=LEASE if self.issued else None,
            ready=not self.issued,
            reason=(
                GhostWalkLeaseReadinessReason.LEASE_ALREADY_EXISTS
                if self.issued
                else GhostWalkLeaseReadinessReason.READY
            ),
        )

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> object | None:
        assert target_inference_receipt_sha256 == TARGET
        return _fake_lease_record() if self.issued else None

    def issue(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_executable_binding_sha256: str,
        expected_policy_sha256: str,
        expected_policy_set_sha256: str,
        expected_enforcement_profile_sha256: str,
        expected_authority_epoch_sha256: str,
    ) -> object:
        assert target_inference_receipt_sha256 == TARGET
        assert expected_executable_binding_sha256 == BINDING
        assert expected_policy_sha256 == POLICY
        assert expected_policy_set_sha256 == POLICY_SET
        assert expected_enforcement_profile_sha256 == PROFILE
        assert expected_authority_epoch_sha256 == EPOCH
        self.issued = True
        return _fake_lease_record()


def _fake_lease_record() -> object:
    lease = SimpleNamespace(
        action_lease_sha256=LEASE,
        principal_id="operator:local",
        issuer_id="phios:ghostwalk-lease-broker",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        payload_sha256=PAYLOAD,
        effects_declared=("display.control", "filesystem.change"),
        permissions_authorized=("ui.interact",),
        valid_from="2026-09-27T21:32:00+00:00",
        valid_until="2026-09-27T21:32:30+00:00",
        max_uses=1,
        action_authority=True,
    )
    return SimpleNamespace(
        action_lease=lease,
        lease_record_sha256=LEASE_RECORD,
        executable_binding_sha256=BINDING,
    )


def test_console_can_authorize_without_execution_mount() -> None:
    authorization = FakeAuthorization()
    console = GhostWalkAuthorizationConsoleService(
        authorization_decisions=authorization,
    )

    before = console.snapshot(
        target_inference_receipt_sha256=TARGET
    )
    assert before.authorization_readiness.ready is True
    assert before.binding_available is False
    assert before.lease_available is False
    assert before.action_authority is False
    assert before.execution_authority is False

    item = console.record_decision(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=REQUEST,
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        decision_note="human approved",
    )
    assert item.authorization_granted is True
    assert item.action_authority is False
    assert authorization.recorded == [
        GhostWalkAuthorizationDecisionKind.APPROVE
    ]


def test_console_stages_binding_then_single_use_lease() -> None:
    authorization = FakeAuthorization()
    authorization.item = _decision()
    bindings = FakeBindings()
    leases = FakeLeases()
    console = GhostWalkAuthorizationConsoleService(
        authorization_decisions=authorization,
        capability_bindings=bindings,
        action_leases=leases,
    )

    initial = console.snapshot(
        target_inference_receipt_sha256=TARGET
    )
    assert initial.binding_readiness is not None
    assert initial.binding_readiness.ready is True
    assert initial.lease_readiness is not None
    assert initial.lease_readiness.ready is True

    binding = console.create_binding(
        target_inference_receipt_sha256=TARGET,
        expected_authorization_decision_sha256=DECISION,
        expected_mapping_sha256=MAPPING,
        expected_mapping_set_sha256=MAPPING_SET,
        bound_at="2026-09-27T21:31:00+00:00",
    )
    assert binding.executable_binding_sha256 == BINDING
    assert binding.action_authority is False
    assert binding.execution_authority is False

    lease = console.issue_lease(
        target_inference_receipt_sha256=TARGET,
        expected_executable_binding_sha256=BINDING,
        expected_policy_sha256=POLICY,
        expected_policy_set_sha256=POLICY_SET,
        expected_enforcement_profile_sha256=PROFILE,
        expected_authority_epoch_sha256=EPOCH,
    )
    assert lease.action_lease_sha256 == LEASE
    assert lease.lease_action_authority is True
    assert lease.execution_authority is False

    final = console.snapshot(
        target_inference_receipt_sha256=TARGET
    )
    assert final.binding is not None
    assert final.lease is not None
    assert final.action_authority is False
    assert final.execution_authority is False
