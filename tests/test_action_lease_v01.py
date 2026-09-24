from __future__ import annotations

import copy

import pytest

from phios.action_lease import (
    ACTION_LEASE_SCHEMA_VERSION,
    ActionLease,
    ActionLeaseContractError,
    evaluate_action_lease,
)
from phios.authority_epoch import AuthorityEpoch
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind


AUTHORIZATION = "a" * 64
ENFORCEMENT_EVIDENCE = "b" * 64
POLICY = "c" * 64


def _intent(
    effects: tuple[str, ...] = ("filesystem.change",),
) -> EffectIntent:
    return EffectIntent.build(
        capability_id="commons.text_artifact",
        capability_version="0.1.0",
        payload_sha256="d" * 64,
        declared_at="2026-09-24T02:02:00+00:00",
        effects_declared=effects,
    )


def _filesystem_rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="workspace-write-confinement",
        effect_scope=("filesystem.change",),
        constraint="filesystem writes remain inside the governed workspace",
        layer="linux_namespaces",
        boundary="kernel_boundary",
        status="enforced",
        mechanism="mount namespace confinement",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )


def _network_gap_rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="network-boundary-gap",
        effect_scope=("network.request",),
        constraint="network requests are not isolated",
        layer="none",
        boundary="none",
        status="not_enforced",
        mechanism="host network is inherited",
    )


def _enforcement(
    intent: EffectIntent | None = None,
    *,
    include_network_gap: bool = False,
) -> EnforcementProfile:
    bound = intent or _intent(
        (
            "filesystem.change",
            "network.request",
        )
        if include_network_gap
        else ("filesystem.change",)
    )
    rules = [_filesystem_rule()]
    if include_network_gap:
        rules.append(_network_gap_rule())
    return EnforcementProfile.build(
        intent=bound,
        rules=tuple(rules),
    )


def _authority_epoch(
    *,
    principal_id: str = "operator:michael",
) -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id=principal_id,
        policy_sha256=POLICY,
        ceiling=("artifact.write", "memory.read"),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-artifact-write",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="artifact.write",
                authority_source="operator-ledger",
                effective_at="2026-09-24T02:00:00+00:00",
                expires_at="2026-09-24T02:10:00+00:00",
            ),
        ),
        observed_at="2026-09-24T02:03:00+00:00",
    )


def _lease() -> ActionLease:
    intent = _intent()
    return ActionLease.issue(
        principal_id="operator:michael",
        issuer_id="authority-broker:test",
        authorization_receipt_sha256=AUTHORIZATION,
        intent=intent,
        enforcement=_enforcement(intent),
        authority_epoch=_authority_epoch(),
        permissions_authorized=("artifact.write",),
        accepted_unenforced_effects=(),
        issued_at="2026-09-24T02:03:00+00:00",
        valid_from="2026-09-24T02:03:00+00:00",
        valid_until="2026-09-24T02:05:00+00:00",
    )


def test_action_lease_is_bounded_single_use_action_authority() -> None:
    lease = _lease()
    payload = lease.to_dict()

    assert lease.schema_version == ACTION_LEASE_SCHEMA_VERSION
    assert lease.principal_id == "operator:michael"
    assert lease.permissions_authorized == ("artifact.write",)
    assert lease.effects_declared == ("filesystem.change",)
    assert lease.max_uses == 1
    assert payload["effect_performed"] is False
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is True
    assert payload["execution_authority"] is False
    assert len(payload["action_lease_sha256"]) == 64

    rebuilt = _lease()
    assert rebuilt == lease
    assert rebuilt.action_lease_sha256 == lease.action_lease_sha256


def test_action_lease_round_trips_exactly() -> None:
    lease = _lease()

    parsed = ActionLease.from_dict(lease.to_dict())

    assert parsed == lease
    assert parsed.action_lease_sha256 == lease.action_lease_sha256


def test_lease_principal_must_match_authority_epoch() -> None:
    intent = _intent()

    with pytest.raises(
        ActionLeaseContractError,
        match="principal does not match",
    ):
        ActionLease.issue(
            principal_id="service:other",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=_enforcement(intent),
            authority_epoch=_authority_epoch(),
            permissions_authorized=("artifact.write",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:03:00+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:05:00+00:00",
        )


def test_enforcement_profile_must_bind_exact_effect_intent() -> None:
    intent = _intent()
    other = EffectIntent.build(
        capability_id="other.capability",
        capability_version="1",
        payload_sha256="e" * 64,
        declared_at="2026-09-24T02:02:00+00:00",
        effects_declared=("filesystem.change",),
    )

    with pytest.raises(
        ActionLeaseContractError,
        match="does not bind the supplied EffectIntent",
    ):
        ActionLease.issue(
            principal_id="operator:michael",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=_enforcement(other),
            authority_epoch=_authority_epoch(),
            permissions_authorized=("artifact.write",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:03:00+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:05:00+00:00",
        )


def test_unmapped_effects_block_lease_issuance() -> None:
    intent = _intent(("filesystem.change", "process.spawn"))
    enforcement = EnforcementProfile.build(
        intent=intent,
        rules=(_filesystem_rule(),),
    )

    assert enforcement.mapping_complete is False

    with pytest.raises(
        ActionLeaseContractError,
        match="unmapped effects",
    ):
        ActionLease.issue(
            principal_id="operator:michael",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=enforcement,
            authority_epoch=_authority_epoch(),
            permissions_authorized=("artifact.write",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:03:00+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:05:00+00:00",
        )


def test_unenforced_effects_require_exact_explicit_acknowledgement() -> None:
    intent = _intent(("filesystem.change", "network.request"))
    enforcement = _enforcement(
        intent,
        include_network_gap=True,
    )

    assert enforcement.effects_without_enforced_rule == (
        "network.request",
    )

    with pytest.raises(
        ActionLeaseContractError,
        match="must exactly acknowledge",
    ):
        ActionLease.issue(
            principal_id="operator:michael",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=enforcement,
            authority_epoch=_authority_epoch(),
            permissions_authorized=("artifact.write",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:03:00+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:05:00+00:00",
        )

    lease = ActionLease.issue(
        principal_id="operator:michael",
        issuer_id="authority-broker:test",
        authorization_receipt_sha256=AUTHORIZATION,
        intent=intent,
        enforcement=enforcement,
        authority_epoch=_authority_epoch(),
        permissions_authorized=("artifact.write",),
        accepted_unenforced_effects=("network.request",),
        issued_at="2026-09-24T02:03:00+00:00",
        valid_from="2026-09-24T02:03:00+00:00",
        valid_until="2026-09-24T02:05:00+00:00",
    )

    assert lease.accepted_unenforced_effects == ("network.request",)


def test_permissions_cannot_exceed_authority_epoch_grants() -> None:
    intent = _intent()

    with pytest.raises(
        ActionLeaseContractError,
        match="exceed AuthorityEpoch grants",
    ):
        ActionLease.issue(
            principal_id="operator:michael",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=_enforcement(intent),
            authority_epoch=_authority_epoch(),
            permissions_authorized=("memory.read",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:03:00+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:05:00+00:00",
        )


def test_lease_cannot_outlive_next_known_authority_transition() -> None:
    intent = _intent()

    with pytest.raises(
        ActionLeaseContractError,
        match="next known authority transition",
    ):
        ActionLease.issue(
            principal_id="operator:michael",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=_enforcement(intent),
            authority_epoch=_authority_epoch(),
            permissions_authorized=("artifact.write",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:03:00+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:11:00+00:00",
        )


def test_lease_cannot_be_issued_before_authority_epoch_observation() -> None:
    intent = _intent()

    with pytest.raises(
        ActionLeaseContractError,
        match="before its AuthorityEpoch observation",
    ):
        ActionLease.issue(
            principal_id="operator:michael",
            issuer_id="authority-broker:test",
            authorization_receipt_sha256=AUTHORIZATION,
            intent=intent,
            enforcement=_enforcement(intent),
            authority_epoch=_authority_epoch(),
            permissions_authorized=("artifact.write",),
            accepted_unenforced_effects=(),
            issued_at="2026-09-24T02:02:59+00:00",
            valid_from="2026-09-24T02:03:00+00:00",
            valid_until="2026-09-24T02:05:00+00:00",
        )


def test_current_unused_lease_evaluates_as_usable_action_authority() -> None:
    lease = _lease()

    evaluation = evaluate_action_lease(
        lease=lease,
        checked_at="2026-09-24T02:04:00+00:00",
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        uses_consumed=0,
    )

    assert evaluation.usable is True
    assert evaluation.reason == "lease_current"
    assert evaluation.action_authority is True
    assert evaluation.execution_authority is False
    assert evaluation.effect_performed is False


@pytest.mark.parametrize(
    ("checked_at", "current_epoch", "uses", "reason"),
    [
        (
            "2026-09-24T02:02:59+00:00",
            None,
            0,
            "lease_not_yet_valid",
        ),
        (
            "2026-09-24T02:05:00+00:00",
            None,
            0,
            "lease_expired",
        ),
        (
            "2026-09-24T02:04:00+00:00",
            None,
            1,
            "lease_consumed",
        ),
        (
            "2026-09-24T02:04:00+00:00",
            "f" * 64,
            0,
            "authority_epoch_changed",
        ),
    ],
)
def test_stale_expired_or_consumed_lease_fails_closed(
    checked_at: str,
    current_epoch: str | None,
    uses: int,
    reason: str,
) -> None:
    lease = _lease()

    evaluation = evaluate_action_lease(
        lease=lease,
        checked_at=checked_at,
        current_authority_epoch_sha256=(
            current_epoch or lease.authority_epoch_sha256
        ),
        uses_consumed=uses,
    )

    assert evaluation.usable is False
    assert evaluation.reason == reason
    assert evaluation.action_authority is False
    assert evaluation.execution_authority is False


def test_action_lease_v01_is_strictly_single_use() -> None:
    payload = _lease().to_dict()
    payload["max_uses"] = 2

    with pytest.raises(
        ActionLeaseContractError,
        match="single-use",
    ):
        ActionLease.from_dict(payload)


def test_serialized_lease_cannot_gain_execution_authority() -> None:
    payload = _lease().to_dict()
    payload["execution_authority"] = True

    with pytest.raises(
        ActionLeaseContractError,
        match="cannot carry execution authority",
    ):
        ActionLease.from_dict(payload)


def test_serialized_lease_cannot_drop_its_bounded_action_authority() -> None:
    payload = _lease().to_dict()
    payload["action_authority"] = False

    with pytest.raises(
        ActionLeaseContractError,
        match="must carry its bounded action authority",
    ):
        ActionLease.from_dict(payload)


def test_serialized_lease_cannot_claim_effect_performed() -> None:
    payload = _lease().to_dict()
    payload["effect_performed"] = True

    with pytest.raises(
        ActionLeaseContractError,
        match="cannot claim an effect",
    ):
        ActionLease.from_dict(payload)


def test_tampered_lease_digest_fails_closed() -> None:
    payload = copy.deepcopy(_lease().to_dict())
    payload["issuer_id"] = "authority-broker:tampered"

    with pytest.raises(
        ActionLeaseContractError,
        match="does not match canonical",
    ):
        ActionLease.from_dict(payload)


def test_authorization_receipt_changes_lease_identity() -> None:
    first = _lease()
    intent = _intent()
    second = ActionLease.issue(
        principal_id="operator:michael",
        issuer_id="authority-broker:test",
        authorization_receipt_sha256="e" * 64,
        intent=intent,
        enforcement=_enforcement(intent),
        authority_epoch=_authority_epoch(),
        permissions_authorized=("artifact.write",),
        accepted_unenforced_effects=(),
        issued_at="2026-09-24T02:03:00+00:00",
        valid_from="2026-09-24T02:03:00+00:00",
        valid_until="2026-09-24T02:05:00+00:00",
    )

    assert first.action_lease_sha256 != second.action_lease_sha256
