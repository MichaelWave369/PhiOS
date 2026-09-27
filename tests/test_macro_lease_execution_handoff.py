from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from phios.action_lease import ActionLease
from phios.authority_epoch import AuthorityEpoch
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.macro_action_lease_service import (
    GhostWalkActionLeaseRecord,
    GhostWalkLeasePolicy,
    GhostWalkLeasePolicyRegistry,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadinessReason,
    GhostWalkExecutableBinding,
)
from phios.macro_lease_execution_handoff import (
    GhostWalkLeaseExecutionError,
    GhostWalkLeaseExecutionHandoff,
)
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.spine.executor import ArtifactResult, OutcomeUnknownError
from phios.spine.ledger import RealityLedger
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine

TARGET = "1" * 64
AUTH_DECISION = "2" * 64
AUTH_REQUEST = "3" * 64
ACTION_OBSERVATION = "4" * 64
MAPPING = "5" * 64
MAPPING_SET = "6" * 64
ENFORCEMENT_EVIDENCE = "7" * 64
AUTHORITY_POLICY = "8" * 64
NOW = datetime(2026, 9, 27, 19, 15, 0, tzinfo=UTC)


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload() -> dict[str, object]:
    return {
        "observation_sha256": ACTION_OBSERVATION,
        "preferred_strategy": "SEMANTIC",
        "process_id": "pid:4242",
        "guard_required": True,
    }


def _binding() -> GhostWalkExecutableBinding:
    payload = _payload()
    payload_sha256 = _sha(payload)
    intent = EffectIntent.build(
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        payload_sha256=payload_sha256,
        declared_at="2026-09-27T19:14:00+00:00",
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
        bound_at="2026-09-27T19:14:00+00:00",
    )


def _rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="desktop-click-runtime-boundary",
        effect_scope=("display.control", "filesystem.change"),
        constraint="one exact leased desktop click enters the governed executor",
        layer="application_contract",
        boundary="process_boundary",
        status="enforced",
        mechanism="lease-only Ghost-Walk execution handoff",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )


def _policy() -> GhostWalkLeasePolicy:
    return GhostWalkLeasePolicy(
        policy_id="ghostwalk.desktop-click.local.v1",
        principal_id="operator:local",
        issuer_id="phios:ghostwalk-lease-broker",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        permissions_authorized=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        enforcement_rules=(_rule(),),
        accepted_unenforced_effects=(),
        max_lease_seconds=30,
    )


def _epoch(
    *,
    policy_sha256: str = AUTHORITY_POLICY,
) -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id="operator:local",
        policy_sha256=policy_sha256,
        ceiling=("ui.interact",),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-ui-interact",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="ui.interact",
                authority_source="operator-ledger",
                effective_at="2026-09-27T19:10:00+00:00",
                expires_at="2026-09-27T19:20:00+00:00",
            ),
        ),
        observed_at="2026-09-27T19:14:30+00:00",
    )


def _record(
    binding: GhostWalkExecutableBinding,
    policy: GhostWalkLeasePolicy,
    epoch: AuthorityEpoch,
) -> GhostWalkActionLeaseRecord:
    profile = EnforcementProfile.build(
        intent=binding.effect_intent,
        rules=policy.enforcement_rules,
    )
    lease = ActionLease.issue(
        principal_id=policy.principal_id,
        issuer_id=policy.issuer_id,
        authorization_receipt_sha256=(
            binding.authorization_decision_sha256
        ),
        intent=binding.effect_intent,
        enforcement=profile,
        authority_epoch=epoch,
        permissions_authorized=policy.permissions_authorized,
        accepted_unenforced_effects=(),
        issued_at="2026-09-27T19:14:40+00:00",
        valid_from="2026-09-27T19:14:40+00:00",
        valid_until="2026-09-27T19:16:00+00:00",
    )
    return GhostWalkActionLeaseRecord(
        target_inference_receipt_sha256=TARGET,
        executable_binding_sha256=binding.executable_binding_sha256,
        policy_sha256=policy.policy_sha256,
        enforcement_profile=profile,
        authority_epoch=epoch,
        action_lease=lease,
        recorded_at="2026-09-27T19:14:40+00:00",
    )


class _Bindings:
    def __init__(
        self,
        binding: GhostWalkExecutableBinding | None,
        *,
        current: bool = True,
    ) -> None:
        self.binding = binding
        self.current = current

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkExecutableBinding | None:
        assert target_inference_receipt_sha256 == TARGET
        return self.binding

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ):
        assert target_inference_receipt_sha256 == TARGET
        if self.binding is None or not self.current:
            return SimpleNamespace(
                reason=GhostWalkBindingReadinessReason.AUTHORIZATION_STALE,
                existing_binding_sha256=(
                    None
                    if self.binding is None
                    else self.binding.executable_binding_sha256
                ),
            )
        return SimpleNamespace(
            reason=GhostWalkBindingReadinessReason.BINDING_ALREADY_EXISTS,
            existing_binding_sha256=(
                self.binding.executable_binding_sha256
            ),
        )


class _Epochs:
    def __init__(self, epoch: AuthorityEpoch | None) -> None:
        self.epoch = epoch

    def current(self) -> AuthorityEpoch | None:
        return self.epoch


def _spine(
    tmp_path: Path,
    *,
    allow: bool = True,
    handler=None,
) -> tuple[PhiOSSpine, list[dict[str, object]]]:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["ui.interact"] if allow else [],
    )
    capability = Capability(
        id="desktop.interaction.click",
        name="Desktop click",
        description="Bounded desktop click test capability",
        permissions=("ui.interact",),
        effects=("display.control", "filesystem.change"),
        risk="medium",
        version="0.19.0",
    )
    spine.registry.register(capability)
    calls: list[dict[str, object]] = []

    def succeed(payload: dict[str, object]) -> ArtifactResult:
        calls.append(dict(payload))
        path = tmp_path / "artifacts" / "click.receipt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("clicked", encoding="utf-8")
        return ArtifactResult(
            path=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    spine.executors.register(
        capability.id,
        handler or succeed,
        effects=("display.control", "filesystem.change"),
    )
    return spine, calls


def _handoff(
    tmp_path: Path,
    *,
    allow: bool = True,
    binding_current: bool = True,
    epoch: AuthorityEpoch | None = None,
    policy: GhostWalkLeasePolicy | None = None,
    handler=None,
):
    binding = _binding()
    active_policy = policy or _policy()
    issued_epoch = _epoch()
    record = _record(binding, _policy(), issued_epoch)
    spine, calls = _spine(
        tmp_path,
        allow=allow,
        handler=handler,
    )
    spine.ledger.append_ghostwalk_action_lease_record(record)
    epochs = _Epochs(epoch if epoch is not None else issued_epoch)
    service = GhostWalkLeaseExecutionHandoff(
        ledger=spine.ledger,
        capability_bindings=_Bindings(
            binding,
            current=binding_current,
        ),
        policies=GhostWalkLeasePolicyRegistry((active_policy,)),
        authority_epochs=epochs,
        spine=spine,
        clock=lambda: NOW,
    )
    return service, record, spine, calls, epochs


def test_execute_accepts_only_lease_identity_and_replays_exact_custody(
    tmp_path: Path,
) -> None:
    service, record, spine, calls, _ = _handoff(tmp_path)

    receipt = service.execute(
        action_lease_sha256=(
            record.action_lease.action_lease_sha256
        )
    )

    assert receipt.status == "SUCCEEDED"
    assert receipt.lease_claimed is True
    assert receipt.lease_consumed is True
    assert receipt.effect_performed is True
    assert receipt.execution_authority is False
    assert calls == [_payload()]
    assert spine.ledger.has_consumed_action_lease(
        record.action_lease.action_lease_sha256
    ) is True

    execution = spine.ledger.recent(1)[0]
    provenance = execution["governed_provenance"]
    assert isinstance(provenance, dict)
    assert provenance["schema_version"] == (
        "phios.ghostwalk_execution_provenance.v0.35"
    )
    assert provenance["action_lease_sha256"] == (
        record.action_lease.action_lease_sha256
    )
    assert provenance["executable_binding_sha256"] == (
        record.executable_binding_sha256
    )
    assert provenance["lease_record_sha256"] == (
        record.lease_record_sha256
    )


def test_public_execute_rejects_caller_payload_override(
    tmp_path: Path,
) -> None:
    service, record, _, _, _ = _handoff(tmp_path)

    with pytest.raises(TypeError):
        service.execute(
            action_lease_sha256=(
                record.action_lease.action_lease_sha256
            ),
            payload={"trust_me": True},  # type: ignore[call-arg]
        )


def test_consumed_lease_blocks_replay_without_second_executor_entry(
    tmp_path: Path,
) -> None:
    service, record, _, calls, _ = _handoff(tmp_path)
    lease_sha = record.action_lease.action_lease_sha256

    first = service.execute(action_lease_sha256=lease_sha)
    replay = service.execute(action_lease_sha256=lease_sha)

    assert first.status == "SUCCEEDED"
    assert replay.status == "HELD"
    assert replay.reason == "lease_consumed"
    assert replay.replay_blocked is True
    assert calls == [_payload()]


def test_permission_denial_releases_lease_for_safe_retry(
    tmp_path: Path,
) -> None:
    denied, record, denied_spine, denied_calls, _ = _handoff(
        tmp_path,
        allow=False,
    )
    lease_sha = record.action_lease.action_lease_sha256

    receipt = denied.execute(action_lease_sha256=lease_sha)

    assert receipt.status == "DENIED"
    assert receipt.lease_claimed is True
    assert receipt.lease_consumed is False
    assert receipt.executor_entered is False
    assert denied_calls == []
    assert denied_spine.ledger.has_consumed_action_lease(
        lease_sha
    ) is False
    assert denied_spine.ledger.claim_action_lease(lease_sha) is True
    denied_spine.ledger.release_action_lease_claim(lease_sha)


def test_changed_authority_epoch_holds_before_claim(
    tmp_path: Path,
) -> None:
    changed = _epoch(policy_sha256="9" * 64)
    service, record, spine, calls, _ = _handoff(
        tmp_path,
        epoch=changed,
    )

    receipt = service.execute(
        action_lease_sha256=record.action_lease.action_lease_sha256
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "authority_epoch_changed"
    assert receipt.lease_claimed is False
    assert calls == []
    assert spine.ledger.recent(10) == []


def test_stale_executable_binding_holds_before_claim(
    tmp_path: Path,
) -> None:
    service, record, _, calls, _ = _handoff(
        tmp_path,
        binding_current=False,
    )

    receipt = service.execute(
        action_lease_sha256=record.action_lease.action_lease_sha256
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "executable_binding_stale"
    assert calls == []


def test_changed_lease_policy_holds_before_claim(
    tmp_path: Path,
) -> None:
    changed_policy = GhostWalkLeasePolicy(
        policy_id="ghostwalk.desktop-click.local.v2",
        principal_id="operator:local",
        issuer_id="phios:ghostwalk-lease-broker",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        permissions_authorized=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        enforcement_rules=(_rule(),),
        accepted_unenforced_effects=(),
        max_lease_seconds=15,
    )
    service, record, _, calls, _ = _handoff(
        tmp_path,
        policy=changed_policy,
    )

    receipt = service.execute(
        action_lease_sha256=record.action_lease.action_lease_sha256
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "lease_policy_or_enforcement_changed"
    assert calls == []
