from __future__ import annotations

import copy

import pytest

from phios.evidence_ref import (
    EVIDENCE_REF_SCHEMA_VERSION,
    EvidenceRef,
    EvidenceRefContractError,
)


CONTENT = "a" * 64
LINEAGE_A = "b" * 64
LINEAGE_B = "c" * 64
ADMISSIBILITY = "d" * 64


def build_ref() -> EvidenceRef:
    return EvidenceRef.build(
        source_id="phishell.system-state.example",
        source_kind="system-state",
        source_version="phios.system-state.v1",
        content_sha256=CONTENT,
        created_at="2026-09-23T22:59:00+00:00",
        observed_at="2026-09-23T23:00:00+00:00",
        transformation_lineage_sha256s=(LINEAGE_B, LINEAGE_A),
        admissibility_receipt_sha256=ADMISSIBILITY,
        exactness_class="REVERSIBLE",
    )


def test_evidence_ref_is_deterministic_content_addressed_and_zero_authority() -> None:
    ref = build_ref()
    payload = ref.to_dict()

    assert ref.schema_version == EVIDENCE_REF_SCHEMA_VERSION
    assert ref.evidence_ref == f"evidence:sha256:{CONTENT}"
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert payload["transformation_lineage_sha256s"] == [
        LINEAGE_A,
        LINEAGE_B,
    ]
    assert len(payload["evidence_ref_sha256"]) == 64

    rebuilt = build_ref()
    assert rebuilt.reference_sha256 == ref.reference_sha256
    assert rebuilt.to_dict() == payload


def test_content_identity_and_provenance_identity_remain_distinct() -> None:
    first = build_ref()
    second = EvidenceRef.build(
        source_id="different-observer",
        source_kind="system-state",
        source_version="phios.system-state.v1",
        content_sha256=CONTENT,
        observed_at="2026-09-23T23:00:00+00:00",
    )

    assert first.evidence_ref == second.evidence_ref
    assert first.reference_sha256 != second.reference_sha256


def test_evidence_ref_round_trips_exactly() -> None:
    ref = build_ref()

    parsed = EvidenceRef.from_dict(ref.to_dict())

    assert parsed == ref
    assert parsed.reference_sha256 == ref.reference_sha256


def test_evidence_ref_rejects_authority_carrying_payload() -> None:
    payload = build_ref().to_dict()
    payload["execution_authority"] = True

    with pytest.raises(EvidenceRefContractError, match="cannot carry"):
        EvidenceRef.from_dict(payload)


def test_admissibility_reference_does_not_mint_authority() -> None:
    ref = build_ref()

    assert ref.admissibility_receipt_sha256 == ADMISSIBILITY
    assert ref.operational_authority is False
    assert ref.action_authority is False
    assert ref.execution_authority is False


def test_evidence_ref_rejects_tampered_content_address() -> None:
    payload = build_ref().to_dict()
    payload["evidence_ref"] = f"evidence:sha256:{'e' * 64}"

    with pytest.raises(
        EvidenceRefContractError,
        match="does not match content_sha256",
    ):
        EvidenceRef.from_dict(payload)


def test_evidence_ref_rejects_tampered_reference_digest() -> None:
    payload = build_ref().to_dict()
    payload["source_id"] = "tampered-source"

    with pytest.raises(
        EvidenceRefContractError,
        match="does not match canonical EvidenceRef",
    ):
        EvidenceRef.from_dict(payload)


def test_evidence_ref_rejects_unknown_fields() -> None:
    payload = build_ref().to_dict()
    payload["surprise_authority"] = "absolutely-not"

    with pytest.raises(EvidenceRefContractError, match="fields mismatch"):
        EvidenceRef.from_dict(payload)


def test_evidence_ref_requires_timezone_aware_observation_time() -> None:
    with pytest.raises(EvidenceRefContractError, match="timezone"):
        EvidenceRef.build(
            source_id="source",
            source_kind="observation",
            content_sha256=CONTENT,
            observed_at="2026-09-23T23:00:00",
        )


def test_evidence_ref_rejects_created_time_after_observation() -> None:
    with pytest.raises(EvidenceRefContractError, match="later than observed"):
        EvidenceRef.build(
            source_id="source",
            source_kind="observation",
            content_sha256=CONTENT,
            created_at="2026-09-23T23:01:00+00:00",
            observed_at="2026-09-23T23:00:00+00:00",
        )


def test_builder_sorts_and_deduplicates_lineage() -> None:
    ref = EvidenceRef.build(
        source_id="source",
        source_kind="derived",
        content_sha256=CONTENT,
        observed_at="2026-09-23T23:00:00+00:00",
        transformation_lineage_sha256s=(
            LINEAGE_B,
            LINEAGE_A,
            LINEAGE_B,
        ),
    )

    assert ref.transformation_lineage_sha256s == (LINEAGE_A, LINEAGE_B)


def test_direct_constructor_requires_canonical_lineage_order() -> None:
    with pytest.raises(EvidenceRefContractError, match="must be sorted"):
        EvidenceRef(
            source_id="source",
            source_kind="derived",
            content_sha256=CONTENT,
            observed_at="2026-09-23T23:00:00+00:00",
            transformation_lineage_sha256s=(LINEAGE_B, LINEAGE_A),
        )


def test_serialized_authority_flags_must_be_boolean() -> None:
    payload = copy.deepcopy(build_ref().to_dict())
    payload["action_authority"] = 0

    with pytest.raises(EvidenceRefContractError, match="must be Boolean"):
        EvidenceRef.from_dict(payload)
