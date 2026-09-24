from __future__ import annotations

import copy

import pytest

from phios.effect_intent import EffectIntent
from phios.enforcement_profile import (
    ENFORCEMENT_PROFILE_SCHEMA_VERSION,
    ENFORCEMENT_RULE_SCHEMA_VERSION,
    EnforcementProfile,
    EnforcementProfileContractError,
    EnforcementRule,
)


PAYLOAD = "a" * 64
EVIDENCE_A = "b" * 64
EVIDENCE_B = "c" * 64


def _intent(
    effects: tuple[str, ...] = (
        "external_state.change",
        "filesystem.change",
    ),
) -> EffectIntent:
    return EffectIntent.build(
        capability_id="example.capability",
        capability_version="1.0.0",
        payload_sha256=PAYLOAD,
        declared_at="2026-09-24T01:15:00+00:00",
        effects_declared=effects,
    )


def _filesystem_rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="workspace-write-confinement",
        effect_scope=("filesystem.change",),
        constraint="filesystem writes remain inside the reviewed workspace",
        layer="linux_namespaces",
        boundary="kernel_boundary",
        status="enforced",
        mechanism="mount namespace with bounded writable workspace",
        evidence_ref_sha256s=(EVIDENCE_A,),
    )


def _external_gap_rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="external-mutation-boundary",
        effect_scope=("external_state.change",),
        constraint="external mutation requires a stronger boundary",
        layer="none",
        boundary="none",
        status="not_enforced",
        mechanism="no enforcement mechanism is currently bound",
    )


def test_enforcement_rule_is_deterministic_and_zero_authority() -> None:
    rule = _filesystem_rule()
    payload = rule.to_dict()

    assert rule.schema_version == ENFORCEMENT_RULE_SCHEMA_VERSION
    assert payload["effect_scope"] == ["filesystem.change"]
    assert payload["status"] == "enforced"
    assert payload["evidence_ref_sha256s"] == [EVIDENCE_A]
    assert payload["effect_performed"] is False
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert len(payload["rule_sha256"]) == 64

    rebuilt = _filesystem_rule()
    assert rebuilt.to_dict() == payload
    assert rebuilt.rule_sha256 == rule.rule_sha256


def test_enforced_rule_requires_concrete_evidence() -> None:
    with pytest.raises(
        EnforcementProfileContractError,
        match="require evidence references",
    ):
        EnforcementRule.build(
            rule_id="missing-evidence",
            effect_scope=("filesystem.change",),
            constraint="writes are confined",
            layer="linux_namespaces",
            boundary="kernel_boundary",
            status="enforced",
            mechanism="mount namespace",
        )


def test_not_enforced_rule_is_explicit_and_cannot_fake_a_boundary() -> None:
    gap = _external_gap_rule()

    assert gap.layer == "none"
    assert gap.boundary == "none"
    assert gap.evidence_ref_sha256s == ()

    with pytest.raises(
        EnforcementProfileContractError,
        match="must use none layer and none boundary",
    ):
        EnforcementRule.build(
            rule_id="fake-gap",
            effect_scope=("external_state.change",),
            constraint="not actually enforced",
            layer="python_policy",
            boundary="same_process",
            status="not_enforced",
            mechanism="none",
        )


def test_unknown_rule_must_remain_explicitly_unknown() -> None:
    rule = EnforcementRule.build(
        rule_id="unknown-network-boundary",
        effect_scope=("network.request",),
        constraint="network enforcement has not been established",
        layer="unknown",
        boundary="unknown",
        status="unknown",
        mechanism="enforcement mechanism has not been verified",
    )

    assert rule.status == "unknown"

    with pytest.raises(
        EnforcementProfileContractError,
        match="must use unknown layer and unknown boundary",
    ):
        EnforcementRule.build(
            rule_id="laundered-unknown",
            effect_scope=("network.request",),
            constraint="network enforcement has not been established",
            layer="transport_boundary",
            boundary="transport_boundary",
            status="unknown",
            mechanism="unverified",
        )


def test_profile_maps_one_exact_effect_intent_without_granting_authority() -> None:
    intent = _intent()
    profile = EnforcementProfile.build(
        intent=intent,
        rules=(_external_gap_rule(), _filesystem_rule()),
    )
    payload = profile.to_dict()

    assert profile.schema_version == ENFORCEMENT_PROFILE_SCHEMA_VERSION
    assert profile.effect_intent_sha256 == intent.effect_intent_sha256
    assert profile.mapping_complete is True
    assert profile.profile_status == "mapped"
    assert profile.mapped_effects == (
        "external_state.change",
        "filesystem.change",
    )
    assert profile.effects_with_enforced_rule == ("filesystem.change",)
    assert profile.effects_without_enforced_rule == (
        "external_state.change",
    )
    assert payload["effect_performed"] is False
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False


def test_mapping_complete_does_not_mean_every_effect_is_enforced() -> None:
    profile = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(), _external_gap_rule()),
    )

    assert profile.mapping_complete is True
    assert profile.effects_without_enforced_rule == (
        "external_state.change",
    )


def test_profile_reports_unmapped_effects_without_inventing_enforcement() -> None:
    profile = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(),),
    )

    assert profile.mapping_complete is False
    assert profile.profile_status == "mapping_gaps"
    assert profile.unmapped_effects == ("external_state.change",)
    assert profile.effects_without_enforced_rule == (
        "external_state.change",
    )


def test_none_intent_needs_no_enforcement_rules() -> None:
    profile = EnforcementProfile.build(
        intent=_intent(("none",)),
    )

    assert profile.profile_status == "no_effects"
    assert profile.mapping_complete is True
    assert profile.mapped_effects == ()
    assert profile.unmapped_effects == ()
    assert profile.effects_without_enforced_rule == ()


def test_none_intent_rejects_rule_claims() -> None:
    with pytest.raises(
        EnforcementProfileContractError,
        match="none EffectIntent cannot carry",
    ):
        EnforcementProfile.build(
            intent=_intent(("none",)),
            rules=(_filesystem_rule(),),
        )


def test_rule_cannot_claim_effect_outside_bound_intent() -> None:
    network_rule = EnforcementRule.build(
        rule_id="network-boundary",
        effect_scope=("network.request",),
        constraint="network requests are brokered",
        layer="broker",
        boundary="process_boundary",
        status="enforced",
        mechanism="broker-mediated network request",
        evidence_ref_sha256s=(EVIDENCE_B,),
    )

    with pytest.raises(
        EnforcementProfileContractError,
        match="outside EffectIntent",
    ):
        EnforcementProfile.build(
            intent=_intent(("filesystem.change",)),
            rules=(network_rule,),
        )


def test_profile_round_trips_exactly() -> None:
    profile = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(), _external_gap_rule()),
    )

    parsed = EnforcementProfile.from_dict(profile.to_dict())

    assert parsed == profile
    assert parsed.profile_sha256 == profile.profile_sha256


def test_profile_builder_canonicalizes_rule_order() -> None:
    profile = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(), _external_gap_rule()),
    )

    assert [rule.rule_id for rule in profile.rules] == [
        "external-mutation-boundary",
        "workspace-write-confinement",
    ]


def test_profile_digest_changes_with_enforcement_map() -> None:
    intent = _intent()
    first = EnforcementProfile.build(
        intent=intent,
        rules=(_filesystem_rule(), _external_gap_rule()),
    )
    unknown_external = EnforcementRule.build(
        rule_id="external-mutation-boundary",
        effect_scope=("external_state.change",),
        constraint="external mutation boundary is not verified",
        layer="unknown",
        boundary="unknown",
        status="unknown",
        mechanism="unknown",
    )
    second = EnforcementProfile.build(
        intent=intent,
        rules=(_filesystem_rule(), unknown_external),
    )

    assert first.profile_sha256 != second.profile_sha256


def test_rule_rejects_authority_or_execution_claims() -> None:
    payload = _filesystem_rule().to_dict()
    payload["execution_authority"] = True

    with pytest.raises(
        EnforcementProfileContractError,
        match="cannot carry authority",
    ):
        EnforcementRule.from_dict(payload)

    payload = _filesystem_rule().to_dict()
    payload["effect_performed"] = True

    with pytest.raises(
        EnforcementProfileContractError,
        match="cannot claim an effect",
    ):
        EnforcementRule.from_dict(payload)


def test_profile_rejects_authority_or_execution_claims() -> None:
    profile = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(), _external_gap_rule()),
    )
    payload = profile.to_dict()
    payload["operational_authority"] = True

    with pytest.raises(
        EnforcementProfileContractError,
        match="cannot carry authority",
    ):
        EnforcementProfile.from_dict(payload)

    payload = profile.to_dict()
    payload["effect_performed"] = True

    with pytest.raises(
        EnforcementProfileContractError,
        match="cannot claim an effect",
    ):
        EnforcementProfile.from_dict(payload)


def test_profile_rejects_tampered_derived_map() -> None:
    payload = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(), _external_gap_rule()),
    ).to_dict()
    payload["effects_with_enforced_rule"] = [
        "external_state.change",
        "filesystem.change",
    ]

    with pytest.raises(
        EnforcementProfileContractError,
        match="does not match canonical",
    ):
        EnforcementProfile.from_dict(payload)


def test_profile_rejects_tampered_digest() -> None:
    payload = EnforcementProfile.build(
        intent=_intent(),
        rules=(_filesystem_rule(), _external_gap_rule()),
    ).to_dict()
    payload["profile_sha256"] = "d" * 64

    with pytest.raises(
        EnforcementProfileContractError,
        match="does not match canonical",
    ):
        EnforcementProfile.from_dict(payload)


def test_rule_rejects_unknown_fields() -> None:
    payload = copy.deepcopy(_filesystem_rule().to_dict())
    payload["trust_me"] = True

    with pytest.raises(
        EnforcementProfileContractError,
        match="fields mismatch",
    ):
        EnforcementRule.from_dict(payload)
