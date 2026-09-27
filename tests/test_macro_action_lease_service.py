from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from phios.authority_epoch import AuthorityEpoch
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementRule
from phios.macro_action_lease_service import (
    GhostWalkActionLeaseError,
    GhostWalkActionLeaseService,
    GhostWalkLeasePolicy,
    GhostWalkLeasePolicyRegistry,
    GhostWalkLeaseReadinessReason,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadinessReason,
    GhostWalkExecutableBinding,
)
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.spine.ledger import RealityLedger

TARGET = "1" * 64
AUTH_DECISION = "2" * 64
AUTH_REQUEST = "3" * 64
ACTION_OBSERVATION = "4" * 64
MAPPING = "5" * 64
MAPPING_SET = "6" * 64
ENFORCEMENT_EVIDENCE = "7" * 64
AUTHORITY_POLICY = "8" * 64
NOW = datetime(2026, 9, 27, 18, 45, 0, tzinfo=UTC)


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _binding() -> GhostWalkExecutableBinding:
    payload = {
        "observation_sha256": ACTION_OBSERVATION,
        "preferred_strategy": "SEMANTIC",
        "guard_required": True,
    }
    payload_sha256 = _sha(payload)
    intent = EffectIntent.build(
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        payload_sha256=payload_sha256,
        declared_at="2026-09-27T18:44:00+00:00",
        effects_declared=("display.control", "filesystem.change"),
    )
    return GhostWalkExecutableBinding(
        authorization_decision_sha256=AUTH_DECISION,
        authority_request_sha256=AUTH_REQUEST,
        target_inference_receipt_sha256=TARGET,
        action_observation_sha256=ACTION_OBSERVATION,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        mapping_id="ghostwalk.open-network-adapter.desktop-click.v1",
        mapping_sha256=MAPPING,
        mapping_set_sha256=MAPPING_SET,
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        payload=payload,
        payload_sha256=payload_sha256,
        permissions_required=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        effect_intent=intent,
        bound_at="2026-09-27T18:44:00+00:00",
    )


def _display_rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="desktop-click-display-guard",
        effect_scope=("display.control",),
        constraint="desktop click remains inside the guarded click contract",
        layer="application_contract",
        boundary="process_boundary",
        status="enforced",
        mechanism="DesktopClickRequest plus interaction guard",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )


def _filesystem_gap() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="desktop-click-filesystem-effect-gap",
        effect_scope=("filesystem.change",),
        constraint="downstream application response may mutate filesystem state",
        layer="none",
        boundary="none",
        status="not_enforced",
        mechanism="no PhiOS filesystem boundary covers application-internal side effects",
    )


def _policy(
    *,
    rules: tuple[EnforcementRule, ...] | None = None,
    accepted_unenforced: tuple[str, ...] = ("filesystem.change",),
    principal_id: str = "operator:local",
) -> GhostWalkLeasePolicy:
    return GhostWalkLeasePolicy(
        policy_id="ghostwalk.desktop-click.local.v1",
        principal_id=principal_id,
        issuer_id="phios:ghostwalk-lease-broker",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        permissions_authorized=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        enforcement_rules=rules if rules is not None else (_display_rule(), _filesystem_gap()),
        accepted_unenforced_effects=accepted_unenforced,
        max_lease_seconds=30,
    )


def _epoch(
    *,
    principal_id: str = "operator:local",
    include_grant: bool = True,
    expires_at: str = "2026-09-27T18:50:00+00:00",
) -> AuthorityEpoch:
    events = ()
    if include_grant:
        events = (
            AuthoritativeAuthorityEvent(
                event_id="grant-ui-interact",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="ui.interact",
                authority_source="operator-ledger",
                effective_at="2026-09-27T18:40:00+00:00",
                expires_at=expires_at,
            ),
        )
    return AuthorityEpoch.build(
        principal_id=principal_id,
        policy_sha256=AUTHORITY_POLICY,
        ceiling=("ui.interact",),
        events=events,
        observed_at="2026-09-27T18:44:30+00:00",
    )


class _Bindings:
    def __init__(self, binding: GhostWalkExecutableBinding | None, *, current: bool = True) -> None:
        self.binding = binding
        self.current = current

    def latest(self, *, target_inference_receipt_sha256: str):
        assert target_inference_receipt_sha256 == TARGET
        return self.binding

    def readiness(self, *, target_inference_receipt_sha256: str):
        assert target_inference_receipt_sha256 == TARGET
        if self.binding is None:
            return SimpleNamespace(
                reason=GhostWalkBindingReadinessReason.AUTHORIZATION_DECISION_REQUIRED,
                existing_binding_sha256=None,
            )
        if self.current:
            return SimpleNamespace(
                reason=GhostWalkBindingReadinessReason.BINDING_ALREADY_EXISTS,
                existing_binding_sha256=self.binding.executable_binding_sha256,
            )
        return SimpleNamespace(
            reason=GhostWalkBindingReadinessReason.AUTHORIZATION_STALE,
            existing_binding_sha256=self.binding.executable_binding_sha256,
        )


class _Epochs:
    def __init__(self, epoch: AuthorityEpoch | None) -> None:
        self.epoch = epoch

    def current(self) -> AuthorityEpoch | None:
        return self.epoch


def _service(
    tmp_path,
    *,
    binding: GhostWalkExecutableBinding | None = None,
    current_binding: bool = True,
    policies: tuple[GhostWalkLeasePolicy, ...] | None = None,
    epoch: AuthorityEpoch | None = None,
) -> GhostWalkActionLeaseService:
    ledger = RealityLedger(tmp_path / "ledger" / "receipts.jsonl")
    return GhostWalkActionLeaseService(
        ledger=ledger,
        capability_bindings=_Bindings(
            binding if binding is not None else _binding(),
            current=current_binding,
        ),
        policies=GhostWalkLeasePolicyRegistry(policies if policies is not None else (_policy(),)),
        authority_epochs=_Epochs(epoch if epoch is not None else _epoch()),
        clock=lambda: NOW,
    )


def test_ready_state_binds_exact_prelease_trust_state(tmp_path) -> None:
    service = _service(tmp_path)

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.ready is True
    assert readiness.reason is GhostWalkLeaseReadinessReason.READY
    assert readiness.executable_binding_sha256 == _binding().executable_binding_sha256
    assert readiness.required_permissions == ("ui.interact",)
    assert readiness.missing_permissions == ()
    assert readiness.unenforced_effects == ("filesystem.change",)
    assert readiness.accepted_unenforced_effects == ("filesystem.change",)
    assert readiness.action_authority is False
    assert readiness.execution_authority is False


def test_issue_creates_single_use_action_authority_not_execution_authority(tmp_path) -> None:
    service = _service(tmp_path)
    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    record = service.issue(
        target_inference_receipt_sha256=TARGET,
        expected_executable_binding_sha256=readiness.executable_binding_sha256 or "",
        expected_policy_sha256=readiness.policy_sha256 or "",
        expected_policy_set_sha256=readiness.policy_set_sha256,
        expected_enforcement_profile_sha256=readiness.enforcement_profile_sha256 or "",
        expected_authority_epoch_sha256=readiness.authority_epoch_sha256 or "",
    )

    lease = record.action_lease
    assert lease.authorization_receipt_sha256 == AUTH_DECISION
    assert lease.permissions_authorized == ("ui.interact",)
    assert lease.max_uses == 1
    assert lease.action_authority is True
    assert lease.execution_authority is False
    assert lease.effect_performed is False
    assert record.executable_binding_sha256 == _binding().executable_binding_sha256
    assert record.execution_authority is False
    assert service.latest(target_inference_receipt_sha256=TARGET) == record

    later = service.readiness(target_inference_receipt_sha256=TARGET)
    assert later.ready is False
    assert later.reason is GhostWalkLeaseReadinessReason.LEASE_ALREADY_EXISTS
    assert later.existing_action_lease_sha256 == lease.action_lease_sha256


def test_no_server_owned_policy_holds(tmp_path) -> None:
    service = _service(tmp_path, policies=())

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.LEASE_POLICY_MISSING
    assert readiness.ready is False


def test_unmapped_effect_holds(tmp_path) -> None:
    policy = _policy(rules=(_display_rule(),), accepted_unenforced=())
    service = _service(tmp_path, policies=(policy,))

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.ENFORCEMENT_PROFILE_INCOMPLETE
    assert readiness.ready is False


def test_unenforced_effect_requires_exact_policy_acknowledgement(tmp_path) -> None:
    policy = _policy(accepted_unenforced=())
    service = _service(tmp_path, policies=(policy,))

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.UNENFORCED_EFFECT_ACK_REQUIRED
    assert readiness.unenforced_effects == ("filesystem.change",)


def test_missing_authority_permission_holds(tmp_path) -> None:
    service = _service(tmp_path, epoch=_epoch(include_grant=False))

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.AUTHORITY_PERMISSION_MISSING
    assert readiness.missing_permissions == ("ui.interact",)


def test_authority_principal_must_match_server_policy(tmp_path) -> None:
    service = _service(tmp_path, epoch=_epoch(principal_id="service:other"))

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.AUTHORITY_PRINCIPAL_MISMATCH


def test_stale_executable_binding_holds(tmp_path) -> None:
    service = _service(tmp_path, current_binding=False)

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.EXECUTABLE_BINDING_STALE


def test_expired_known_authority_transition_holds(tmp_path) -> None:
    epoch = _epoch(expires_at="2026-09-27T18:44:59+00:00")
    service = _service(tmp_path, epoch=epoch)

    readiness = service.readiness(target_inference_receipt_sha256=TARGET)

    assert readiness.reason is GhostWalkLeaseReadinessReason.AUTHORITY_EPOCH_STALE


def test_optimistic_concurrency_rejects_changed_epoch(tmp_path) -> None:
    epochs = _Epochs(_epoch())
    service = GhostWalkActionLeaseService(
        ledger=RealityLedger(tmp_path / "ledger" / "receipts.jsonl"),
        capability_bindings=_Bindings(_binding()),
        policies=GhostWalkLeasePolicyRegistry((_policy(),)),
        authority_epochs=epochs,
        clock=lambda: NOW,
    )
    readiness = service.readiness(target_inference_receipt_sha256=TARGET)
    epochs.epoch = AuthorityEpoch.build(
        principal_id="operator:local",
        policy_sha256="9" * 64,
        ceiling=("ui.interact",),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-ui-interact",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="ui.interact",
                authority_source="operator-ledger",
                effective_at="2026-09-27T18:40:00+00:00",
                expires_at="2026-09-27T18:50:00+00:00",
            ),
        ),
        observed_at="2026-09-27T18:44:40+00:00",
    )

    with pytest.raises(GhostWalkActionLeaseError, match="AuthorityEpoch changed"):
        service.issue(
            target_inference_receipt_sha256=TARGET,
            expected_executable_binding_sha256=readiness.executable_binding_sha256 or "",
            expected_policy_sha256=readiness.policy_sha256 or "",
            expected_policy_set_sha256=readiness.policy_set_sha256,
            expected_enforcement_profile_sha256=readiness.enforcement_profile_sha256 or "",
            expected_authority_epoch_sha256=readiness.authority_epoch_sha256 or "",
        )


def test_tampered_persisted_lease_record_fails_closed(tmp_path) -> None:
    service = _service(tmp_path)
    readiness = service.readiness(target_inference_receipt_sha256=TARGET)
    record = service.issue(
        target_inference_receipt_sha256=TARGET,
        expected_executable_binding_sha256=readiness.executable_binding_sha256 or "",
        expected_policy_sha256=readiness.policy_sha256 or "",
        expected_policy_set_sha256=readiness.policy_set_sha256,
        expected_enforcement_profile_sha256=readiness.enforcement_profile_sha256 or "",
        expected_authority_epoch_sha256=readiness.authority_epoch_sha256 or "",
    )
    path = service._ledger.path.parent / "ghostwalk-action-lease-records.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["action_lease"]["issuer_id"] = "phios:tampered"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(GhostWalkActionLeaseError, match="persisted Ghost-Walk ActionLease"):
        service.latest(target_inference_receipt_sha256=record.target_inference_receipt_sha256)


def test_serialized_record_cannot_claim_execution(tmp_path) -> None:
    service = _service(tmp_path)
    readiness = service.readiness(target_inference_receipt_sha256=TARGET)
    record = service.issue(
        target_inference_receipt_sha256=TARGET,
        expected_executable_binding_sha256=readiness.executable_binding_sha256 or "",
        expected_policy_sha256=readiness.policy_sha256 or "",
        expected_policy_set_sha256=readiness.policy_set_sha256,
        expected_enforcement_profile_sha256=readiness.enforcement_profile_sha256 or "",
        expected_authority_epoch_sha256=readiness.authority_epoch_sha256 or "",
    )
    payload = copy.deepcopy(record.to_dict())
    payload["execution_authority"] = True
    path = service._ledger.path.parent / "ghostwalk-action-lease-records.jsonl"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(GhostWalkActionLeaseError, match="persisted Ghost-Walk ActionLease"):
        service.latest(target_inference_receipt_sha256=TARGET)
