from __future__ import annotations

import copy

import pytest

from phios.covenant.models import canonical_sha256
from phios.evidence_ref import EvidenceRef, EvidenceRefContractError
from phios.phivid_evidence import (
    PHIVID_ENVELOPE_SCHEMA_VERSION,
    validate_phivid_evidence_envelope,
)


def _source_ref() -> EvidenceRef:
    return EvidenceRef.build(
        source_id="clip-a",
        source_kind="phivid.video.source",
        source_version="phivid.render-receipt.v0.2",
        content_sha256="3" * 64,
        observed_at="2026-10-04T22:56:00Z",
        exactness_class="byte_exact",
    )


def _output_ref() -> EvidenceRef:
    return EvidenceRef.build(
        source_id="phivid:render:render-42",
        source_kind="phivid.video.render",
        source_version="phivid.render-receipt.v0.2",
        content_sha256="4" * 64,
        observed_at="2026-10-04T22:56:00Z",
        transformation_lineage_sha256s=(
            "1" * 64,
            "2" * 64,
            "3" * 64,
            "5" * 64,
        ),
        exactness_class="byte_exact",
    )


def _envelope() -> dict[str, object]:
    refs = sorted(
        [_source_ref().to_dict(), _output_ref().to_dict()],
        key=lambda item: str(item["evidence_ref"]),
    )
    body: dict[str, object] = {
        "schema_version": PHIVID_ENVELOPE_SCHEMA_VERSION,
        "event_type": "phivid.render.verified",
        "produced_by": "PHIVid",
        "source_receipt_sha256": "5" * 64,
        "plan_id": "render-42",
        "observed_at": "2026-10-04T22:56:00Z",
        "output_evidence_ref": f"evidence:sha256:{'4' * 64}",
        "evidence_refs": refs,
        "warnings": ["render_used_cpu_encoder"],
        "operational_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    body["envelope_sha256"] = canonical_sha256(body)
    return body


def test_valid_phivid_envelope_uses_native_evidence_ref_parser() -> None:
    intake = validate_phivid_evidence_envelope(_envelope())

    assert intake.schema_version == PHIVID_ENVELOPE_SCHEMA_VERSION
    assert intake.plan_id == "render-42"
    assert intake.output_evidence_ref == f"evidence:sha256:{'4' * 64}"
    assert len(intake.evidence_refs) == 2
    assert intake.ledger_admitted is False
    assert intake.operational_authority is False
    assert intake.action_authority is False
    assert intake.execution_authority is False


def test_nested_evidence_ref_tampering_is_rejected_by_phios_contract() -> None:
    value = _envelope()
    refs = value["evidence_refs"]
    assert isinstance(refs, list)
    refs[0]["source_id"] = "tampered"

    body = dict(value)
    del body["envelope_sha256"]
    value["envelope_sha256"] = canonical_sha256(body)

    with pytest.raises(
        EvidenceRefContractError,
        match="does not match canonical EvidenceRef",
    ):
        validate_phivid_evidence_envelope(value)


def test_envelope_authority_is_rejected_even_with_valid_digest() -> None:
    value = _envelope()
    value["execution_authority"] = True
    body = dict(value)
    del body["envelope_sha256"]
    value["envelope_sha256"] = canonical_sha256(body)

    with pytest.raises(ValueError, match="cannot carry execution_authority"):
        validate_phivid_evidence_envelope(value)


def test_envelope_digest_tampering_is_rejected() -> None:
    value = _envelope()
    value["warnings"] = ["render_used_cpu_encoder", "invented_warning"]

    with pytest.raises(ValueError, match="digest does not match"):
        validate_phivid_evidence_envelope(value)


def test_output_reference_must_point_to_render_evidence() -> None:
    value = _envelope()
    value["output_evidence_ref"] = f"evidence:sha256:{'3' * 64}"
    body = dict(value)
    del body["envelope_sha256"]
    value["envelope_sha256"] = canonical_sha256(body)

    with pytest.raises(ValueError, match="source_kind phivid.video.render"):
        validate_phivid_evidence_envelope(value)


def test_evidence_refs_must_be_sorted_and_unique() -> None:
    value = _envelope()
    refs = value["evidence_refs"]
    assert isinstance(refs, list)
    value["evidence_refs"] = list(reversed(refs))
    body = dict(value)
    del body["envelope_sha256"]
    value["envelope_sha256"] = canonical_sha256(body)

    with pytest.raises(ValueError, match="must be sorted"):
        validate_phivid_evidence_envelope(value)


def test_validation_has_no_ledger_side_effects(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    validate_phivid_evidence_envelope(copy.deepcopy(_envelope()))

    assert list(tmp_path.iterdir()) == []
