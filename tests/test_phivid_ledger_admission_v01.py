from __future__ import annotations

import copy
from pathlib import Path

import pytest

from phios.covenant.models import canonical_sha256
from phios.evidence_ref import EvidenceRef
from phios.mandala import AuthorityContext
from phios.phivid_admission import (
    PHIVidAdmissionPolicy,
    evaluate_phivid_admission,
)
from phios.phivid_evidence import validate_phivid_evidence_envelope
from phios.phivid_ledger_admission import (
    PHIVID_LEDGER_ADMIT_PERMISSION,
    PHIVidLedgerAdmissionError,
    PHIVidLedgerAdmissionRecord,
    admit_phivid_evidence,
)
from phios.spine.ledger import RealityLedger


def _ref(
    *,
    source_id: str,
    source_kind: str,
    sha: str,
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
        exactness_class="byte_exact",
    )


def _intake(*, warnings: list[str] | None = None):
    source = _ref(
        source_id="clip-a",
        source_kind="phivid.video.source",
        sha="3" * 64,
    )
    output = _ref(
        source_id="phivid:render:render-42",
        source_kind="phivid.video.render",
        sha="4" * 64,
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
    return validate_phivid_evidence_envelope(body)


def _receipt(intake):
    return evaluate_phivid_admission(
        intake,
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )


def _authority(*permissions: str) -> AuthorityContext:
    values = tuple(sorted(set(permissions)))
    return AuthorityContext(ceiling=values, grants=values)


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "reality-ledger.jsonl")


def test_eligible_evidence_requires_explicit_permission_and_operator_confirmation(
    tmp_path: Path,
) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)

    record = admit_phivid_evidence(
        intake,
        admission_receipt=receipt,
        authority=_authority(PHIVID_LEDGER_ADMIT_PERMISSION),
        ledger=ledger,
        operator_id="operator:local",
        operator_confirmed=True,
        operator_confirmed_at="2026-10-04T23:15:00Z",
    )

    assert record.ledger_write_performed is True
    assert record.evidence_admitted is True
    assert record.operational_authority is False
    assert record.action_authority is False
    assert record.execution_authority is False
    assert len(record.ledger_admission_sha256) == 64

    rows = ledger.phivid_evidence_admission_records(
        envelope_sha256=intake.envelope_sha256
    )
    assert len(rows) == 1
    assert PHIVidLedgerAdmissionRecord.from_dict(rows[0]) == record


def test_missing_operator_confirmation_performs_no_write(tmp_path: Path) -> None:
    intake = _intake()
    ledger = _ledger(tmp_path)

    with pytest.raises(
        PHIVidLedgerAdmissionError,
        match="operator confirmation",
    ):
        admit_phivid_evidence(
            intake,
            admission_receipt=_receipt(intake),
            authority=_authority(PHIVID_LEDGER_ADMIT_PERMISSION),
            ledger=ledger,
            operator_id="operator:local",
            operator_confirmed=False,
            operator_confirmed_at="2026-10-04T23:15:00Z",
        )

    assert ledger.phivid_evidence_admission_records() == []


def test_missing_authority_grant_performs_no_write(tmp_path: Path) -> None:
    intake = _intake()
    ledger = _ledger(tmp_path)

    with pytest.raises(PHIVidLedgerAdmissionError, match="does not grant"):
        admit_phivid_evidence(
            intake,
            admission_receipt=_receipt(intake),
            authority=_authority(),
            ledger=ledger,
            operator_id="operator:local",
            operator_confirmed=True,
            operator_confirmed_at="2026-10-04T23:15:00Z",
        )

    assert ledger.phivid_evidence_admission_records() == []


def test_hold_receipt_cannot_cross_ledger_boundary(tmp_path: Path) -> None:
    intake = _intake(warnings=["unknown_warning"])
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)

    with pytest.raises(PHIVidLedgerAdmissionError, match="not eligible"):
        admit_phivid_evidence(
            intake,
            admission_receipt=receipt,
            authority=_authority(PHIVID_LEDGER_ADMIT_PERMISSION),
            ledger=ledger,
            operator_id="operator:local",
            operator_confirmed=True,
            operator_confirmed_at="2026-10-04T23:15:00Z",
        )

    assert ledger.phivid_evidence_admission_records() == []


def test_admission_receipt_must_bind_exact_intake(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    altered = copy.copy(intake)
    object.__setattr__(altered, "plan_id", "other-plan")
    ledger = _ledger(tmp_path)

    with pytest.raises(PHIVidLedgerAdmissionError, match="plan_id"):
        admit_phivid_evidence(
            altered,
            admission_receipt=receipt,
            authority=_authority(PHIVID_LEDGER_ADMIT_PERMISSION),
            ledger=ledger,
            operator_id="operator:local",
            operator_confirmed=True,
            operator_confirmed_at="2026-10-04T23:15:00Z",
        )


def test_duplicate_envelope_is_not_appended_twice(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = dict(
        admission_receipt=receipt,
        authority=_authority(PHIVID_LEDGER_ADMIT_PERMISSION),
        ledger=ledger,
        operator_id="operator:local",
        operator_confirmed=True,
        operator_confirmed_at="2026-10-04T23:15:00Z",
    )

    admit_phivid_evidence(intake, **kwargs)
    with pytest.raises(PHIVidLedgerAdmissionError, match="already admitted"):
        admit_phivid_evidence(intake, **kwargs)

    assert len(ledger.phivid_evidence_admission_records()) == 1
