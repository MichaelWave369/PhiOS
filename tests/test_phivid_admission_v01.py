from __future__ import annotations

import copy

import pytest

from phios.covenant.models import canonical_sha256
from phios.evidence_ref import EvidenceRef
from phios.phivid_admission import (
    PHIVidAdmissionDecision,
    PHIVidAdmissionPolicy,
    PHIVidAdmissionReason,
    PHIVidAdmissionReceipt,
    evaluate_phivid_admission,
)
from phios.phivid_evidence import validate_phivid_evidence_envelope


def _ref(
    *,
    source_id: str,
    source_kind: str,
    sha: str,
    exactness: str = "byte_exact",
    admissibility: str | None = None,
) -> EvidenceRef:
    return EvidenceRef.build(
        source_id=source_id,
        source_kind=source_kind,
        source_version="phivid.render-receipt.v0.2",
        content_sha256=sha,
        observed_at="2026-10-04T22:56:00Z",
        transformation_lineage_sha256s=(
            () if source_kind.endswith("source") else ("1" * 64, "2" * 64)
        ),
        admissibility_receipt_sha256=admissibility,
        exactness_class=exactness,
    )


def _envelope(
    *,
    warnings: list[str] | None = None,
    source_kind: str = "phivid.video.source",
    output_exactness: str = "byte_exact",
    output_admissibility: str | None = None,
) -> dict[str, object]:
    source = _ref(
        source_id="clip-a",
        source_kind=source_kind,
        sha="3" * 64,
    )
    output = _ref(
        source_id="phivid:render:render-42",
        source_kind="phivid.video.render",
        sha="4" * 64,
        exactness=output_exactness,
        admissibility=output_admissibility,
    )
    refs = sorted(
        [source.to_dict(), output.to_dict()],
        key=lambda item: str(item["evidence_ref"]),
    )
    body: dict[str, object] = {
        "schema_version": "phivid.phios_evidence_envelope.v0.1",
        "event_type": "phivid.render.verified",
        "produced_by": "PHIVid",
        "source_receipt_sha256": "5" * 64,
        "plan_id": "render-42",
        "observed_at": "2026-10-04T22:56:00Z",
        "output_evidence_ref": f"evidence:sha256:{'4' * 64}",
        "evidence_refs": refs,
        "warnings": warnings or ["render_used_cpu_encoder"],
        "operational_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    body["envelope_sha256"] = canonical_sha256(body)
    return body


def _intake(**kwargs):
    return validate_phivid_evidence_envelope(_envelope(**kwargs))


def test_strict_policy_marks_expected_phivid_evidence_eligible() -> None:
    policy = PHIVidAdmissionPolicy.strict_default()
    receipt = evaluate_phivid_admission(
        _intake(),
        policy=policy,
        evaluated_at="2026-10-04T23:10:00Z",
    )

    assert receipt.decision is PHIVidAdmissionDecision.ELIGIBLE
    assert receipt.reason is PHIVidAdmissionReason.POLICY_SATISFIED
    assert receipt.eligible_for_ledger_admission is True
    assert receipt.ledger_write_performed is False
    assert receipt.admission_effect_performed is False
    assert receipt.operational_authority is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    assert len(receipt.admission_receipt_sha256) == 64


def test_unknown_warning_fails_closed_as_hold() -> None:
    receipt = evaluate_phivid_admission(
        _intake(warnings=["render_used_cpu_encoder", "mystery_warning"]),
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )

    assert receipt.decision is PHIVidAdmissionDecision.HOLD
    assert receipt.reason is PHIVidAdmissionReason.WARNING_NOT_ALLOWED
    assert receipt.eligible_for_ledger_admission is False


def test_unexpected_source_kind_fails_closed_as_hold() -> None:
    receipt = evaluate_phivid_admission(
        _intake(source_kind="other.video.source"),
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )

    assert receipt.decision is PHIVidAdmissionDecision.HOLD
    assert receipt.reason is PHIVidAdmissionReason.SOURCE_KIND_NOT_ALLOWED


def test_unexpected_exactness_fails_closed_as_hold() -> None:
    receipt = evaluate_phivid_admission(
        _intake(output_exactness="interpretive"),
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )

    assert receipt.decision is PHIVidAdmissionDecision.HOLD
    assert receipt.reason is PHIVidAdmissionReason.EXACTNESS_NOT_ALLOWED


def test_existing_admission_binding_fails_closed_as_hold() -> None:
    receipt = evaluate_phivid_admission(
        _intake(output_admissibility="6" * 64),
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )

    assert receipt.decision is PHIVidAdmissionDecision.HOLD
    assert receipt.reason is PHIVidAdmissionReason.PREVIOUS_ADMISSION_BINDING_PRESENT


def test_receipt_round_trips_and_detects_tampering() -> None:
    receipt = evaluate_phivid_admission(
        _intake(),
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00+00:00",
    )
    payload = receipt.to_dict()

    assert PHIVidAdmissionReceipt.from_dict(payload) == receipt

    tampered = copy.deepcopy(payload)
    tampered["eligible_for_ledger_admission"] = False
    with pytest.raises(ValueError):
        PHIVidAdmissionReceipt.from_dict(tampered)


def test_policy_and_receipt_are_zero_authority() -> None:
    policy = PHIVidAdmissionPolicy.strict_default()
    assert policy.operational_authority is False
    assert policy.action_authority is False
    assert policy.execution_authority is False

    with pytest.raises(ValueError, match="cannot carry authority"):
        PHIVidAdmissionPolicy(
            profile_id="bad",
            allowed_source_kinds=("phivid.video.render",),
            allowed_exactness_classes=("byte_exact",),
            allowed_warnings=(),
            execution_authority=True,
        )


def test_evaluation_has_no_filesystem_side_effects(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    evaluate_phivid_admission(
        _intake(),
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )
    assert list(tmp_path.iterdir()) == []
