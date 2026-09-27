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
