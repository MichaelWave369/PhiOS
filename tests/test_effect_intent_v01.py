from __future__ import annotations

import copy

import pytest

from phios.effect_intent import (
    EFFECT_INTENT_SCHEMA_VERSION,
    EffectIntent,
    EffectIntentContractError,
)


PAYLOAD = "a" * 64
EVIDENCE_A = "b" * 64
EVIDENCE_B = "c" * 64


def build_intent() -> EffectIntent:
    return EffectIntent.build(
        capability_id="commons.text_artifact",
        capability_version="0.1.0",
        payload_sha256=PAYLOAD,
        declared_at="2026-09-24T00:20:00+00:00",
        effects_declared=("filesystem.change", "local_state.change"),
        evidence_ref_sha256s=(EVIDENCE_B, EVIDENCE_A),
    )


def test_effect_intent_is_deterministic_and_zero_authority() -> None:
    intent = build_intent()
    payload = intent.to_dict()

    assert intent.schema_version == EFFECT_INTENT_SCHEMA_VERSION
    assert payload["effects_declared"] == [
        "filesystem.change",
        "local_state.change",
    ]
    assert payload["active_effects"] == [
        "filesystem.change",
        "local_state.change",
    ]
    assert payload["evidence_ref_sha256s"] == [
        EVIDENCE_A,
        EVIDENCE_B,
    ]
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert len(payload["effect_intent_sha256"]) == 64

    rebuilt = build_intent()
    assert rebuilt.effect_intent_sha256 == intent.effect_intent_sha256
    assert rebuilt.to_dict() == payload


def test_effect_intent_round_trips_exactly() -> None:
    intent = build_intent()

    parsed = EffectIntent.from_dict(intent.to_dict())

    assert parsed == intent
    assert parsed.effect_intent_sha256 == intent.effect_intent_sha256


def test_effect_intent_identity_changes_when_exact_payload_changes() -> None:
    first = build_intent()
    second = EffectIntent.build(
        capability_id=first.capability_id,
        capability_version=first.capability_version,
        payload_sha256="d" * 64,
        declared_at=first.declared_at,
        effects_declared=first.effects_declared,
        evidence_ref_sha256s=first.evidence_ref_sha256s,
    )

    assert first.effect_intent_sha256 != second.effect_intent_sha256


def test_effect_intent_identity_changes_when_evidence_changes() -> None:
    first = build_intent()
    second = EffectIntent.build(
        capability_id=first.capability_id,
        capability_version=first.capability_version,
        payload_sha256=first.payload_sha256,
        declared_at=first.declared_at,
        effects_declared=first.effects_declared,
        evidence_ref_sha256s=(EVIDENCE_A,),
    )

    assert first.effect_intent_sha256 != second.effect_intent_sha256


def test_effect_intent_rejects_unknown_effects() -> None:
    with pytest.raises(EffectIntentContractError, match="unknown"):
        EffectIntent.build(
            capability_id="cap",
            capability_version="1",
            payload_sha256=PAYLOAD,
            declared_at="2026-09-24T00:20:00+00:00",
            effects_declared=("unknown",),
        )


def test_effect_intent_allows_none_only_as_the_sole_effect() -> None:
    intent = EffectIntent.build(
        capability_id="cap",
        capability_version="1",
        payload_sha256=PAYLOAD,
        declared_at="2026-09-24T00:20:00+00:00",
        effects_declared=("none",),
    )

    assert intent.effects_declared == ("none",)
    assert intent.active_effects == ()

    with pytest.raises(EffectIntentContractError, match="cannot combine none"):
        EffectIntent.build(
            capability_id="cap",
            capability_version="1",
            payload_sha256=PAYLOAD,
            declared_at="2026-09-24T00:20:00+00:00",
            effects_declared=("none", "filesystem.read"),
        )


def test_read_only_effects_do_not_become_active_effects() -> None:
    intent = EffectIntent.build(
        capability_id="observer",
        capability_version="1",
        payload_sha256=PAYLOAD,
        declared_at="2026-09-24T00:20:00+00:00",
        effects_declared=("filesystem.read", "local_state.read"),
    )

    assert intent.active_effects == ()


def test_effect_intent_rejects_authority_carrying_payload() -> None:
    payload = build_intent().to_dict()
    payload["action_authority"] = True

    with pytest.raises(EffectIntentContractError, match="cannot carry"):
        EffectIntent.from_dict(payload)


def test_effect_intent_rejects_tampered_active_effects() -> None:
    payload = build_intent().to_dict()
    payload["active_effects"] = ["filesystem.change"]

    with pytest.raises(
        EffectIntentContractError,
        match="active_effects does not match",
    ):
        EffectIntent.from_dict(payload)


def test_effect_intent_rejects_tampered_digest() -> None:
    payload = build_intent().to_dict()
    payload["capability_version"] = "9.9.9"

    with pytest.raises(
        EffectIntentContractError,
        match="does not match canonical",
    ):
        EffectIntent.from_dict(payload)


def test_effect_intent_rejects_unknown_fields() -> None:
    payload = build_intent().to_dict()
    payload["permission_granted"] = True

    with pytest.raises(EffectIntentContractError, match="fields mismatch"):
        EffectIntent.from_dict(payload)


def test_effect_intent_requires_timezone_aware_declaration_time() -> None:
    with pytest.raises(EffectIntentContractError, match="timezone"):
        EffectIntent.build(
            capability_id="cap",
            capability_version="1",
            payload_sha256=PAYLOAD,
            declared_at="2026-09-24T00:20:00",
            effects_declared=("filesystem.read",),
        )


def test_builder_canonicalizes_effect_and_evidence_order() -> None:
    intent = EffectIntent.build(
        capability_id="cap",
        capability_version="1",
        payload_sha256=PAYLOAD,
        declared_at="2026-09-24T00:20:00+00:00",
        effects_declared=(
            "local_state.change",
            "filesystem.change",
            "local_state.change",
        ),
        evidence_ref_sha256s=(EVIDENCE_B, EVIDENCE_A, EVIDENCE_B),
    )

    assert intent.effects_declared == (
        "filesystem.change",
        "local_state.change",
    )
    assert intent.evidence_ref_sha256s == (
        EVIDENCE_A,
        EVIDENCE_B,
    )


def test_direct_constructor_requires_canonical_effect_order() -> None:
    with pytest.raises(
        EffectIntentContractError,
        match="sorted, unique, and canonical",
    ):
        EffectIntent(
            capability_id="cap",
            capability_version="1",
            payload_sha256=PAYLOAD,
            declared_at="2026-09-24T00:20:00+00:00",
            effects_declared=(
                "local_state.change",
                "filesystem.change",
            ),
        )


def test_serialized_authority_flags_must_be_boolean() -> None:
    payload = copy.deepcopy(build_intent().to_dict())
    payload["execution_authority"] = 0

    with pytest.raises(EffectIntentContractError, match="must be Boolean"):
        EffectIntent.from_dict(payload)
