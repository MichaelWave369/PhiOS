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
from phios.phivid_operator_approval import create_phivid_operator_approval
from phios.spine.ledger import RealityLedger

EPOCH_SHA = "6" * 64
CONFIRMED_AT = "2026-10-04T23:15:00Z"
OPERATOR_ID = "operator:local"


def _ref(*, source_id: str, source_kind: str, sha: str) -> EvidenceRef:
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


def _proof(intake, receipt, *, key: bytes = b"k" * 32):
    return create_phivid_operator_approval(
        envelope_sha256=intake.envelope_sha256,
        admission_receipt_sha256=receipt.admission_receipt_sha256,
        authority_epoch_sha256=EPOCH_SHA,
        operator_id=OPERATOR_ID,
        approved_at=CONFIRMED_AT,
        key=key,
    )


def _admit_kwargs(intake, receipt, ledger, *, key: bytes = b"k" * 32):
    approval = _proof(intake, receipt, key=key)
    return {
        "admission_receipt": receipt,
        "authority": _authority(PHIVID_LEDGER_ADMIT_PERMISSION),
        "authority_epoch_sha256": EPOCH_SHA,
        "operator_approval": approval,
        "operator_key": key,
        "ledger": ledger,
        "operator_id": OPERATOR_ID,
        "operator_confirmed": True,
        "operator_confirmed_at": CONFIRMED_AT,
    }


def test_eligible_evidence_requires_proof_permission_and_confirmation(
    tmp_path: Path,
) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)

    record = admit_phivid_evidence(intake, **kwargs)

    approval = kwargs["operator_approval"]
    assert record.schema_version == "phios.phivid_ledger_admission.v0.2"
    assert record.ledger_write_performed is True
    assert record.evidence_admitted is True
    assert record.operator_approval_verified is True
    assert record.authority_epoch_sha256 == EPOCH_SHA
    assert record.operator_approval_sha256 == canonical_sha256(
        approval.to_dict()
    )
    assert record.operator_approval_payload_sha256 == approval.payload_sha256
    assert (
        record.operator_approval_proof_hmac_sha256
        == approval.proof_hmac_sha256
    )
    assert record.operational_authority is False
    assert record.action_authority is False
    assert record.execution_authority is False

    rows = ledger.phivid_evidence_admission_records(
        envelope_sha256=intake.envelope_sha256
    )
    assert len(rows) == 1
    assert PHIVidLedgerAdmissionRecord.from_dict(rows[0]) == record


def test_wrong_operator_key_performs_no_write(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)
    kwargs["operator_key"] = b"x" * 32

    with pytest.raises(
        PHIVidLedgerAdmissionError,
        match="HMAC verification failed",
    ):
        admit_phivid_evidence(intake, **kwargs)

    assert ledger.phivid_evidence_admission_records() == []


def test_missing_operator_confirmation_performs_no_write(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)
    kwargs["operator_confirmed"] = False

    with pytest.raises(
        PHIVidLedgerAdmissionError,
        match="operator confirmation",
    ):
        admit_phivid_evidence(intake, **kwargs)

    assert ledger.phivid_evidence_admission_records() == []


def test_missing_authority_grant_performs_no_write(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)
    kwargs["authority"] = _authority()

    with pytest.raises(PHIVidLedgerAdmissionError, match="does not grant"):
        admit_phivid_evidence(intake, **kwargs)

    assert ledger.phivid_evidence_admission_records() == []


def test_hold_receipt_cannot_cross_ledger_boundary(tmp_path: Path) -> None:
    intake = _intake(warnings=["unknown_warning"])
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)

    with pytest.raises(PHIVidLedgerAdmissionError, match="not eligible"):
        admit_phivid_evidence(intake, **kwargs)

    assert ledger.phivid_evidence_admission_records() == []


def test_admission_receipt_must_bind_exact_intake(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    altered = copy.copy(intake)
    object.__setattr__(altered, "plan_id", "other-plan")
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)

    with pytest.raises(PHIVidLedgerAdmissionError, match="plan_id"):
        admit_phivid_evidence(altered, **kwargs)


def test_proof_must_bind_exact_authority_epoch(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)
    kwargs["authority_epoch_sha256"] = "7" * 64

    with pytest.raises(
        PHIVidLedgerAdmissionError,
        match="authority_epoch_sha256",
    ):
        admit_phivid_evidence(intake, **kwargs)

    assert ledger.phivid_evidence_admission_records() == []


def test_duplicate_envelope_is_not_appended_twice(tmp_path: Path) -> None:
    intake = _intake()
    receipt = _receipt(intake)
    ledger = _ledger(tmp_path)
    kwargs = _admit_kwargs(intake, receipt, ledger)

    admit_phivid_evidence(intake, **kwargs)
    with pytest.raises(PHIVidLedgerAdmissionError, match="already admitted"):
        admit_phivid_evidence(intake, **kwargs)

    assert len(ledger.phivid_evidence_admission_records()) == 1


def test_v01_record_remains_parseable() -> None:
    body: dict[str, object] = {
        "schema_version": "phios.phivid_ledger_admission.v0.1",
        "admission_receipt_sha256": "1" * 64,
        "envelope_sha256": "2" * 64,
        "source_receipt_sha256": "3" * 64,
        "policy_profile_sha256": "4" * 64,
        "plan_id": "old-plan",
        "output_evidence_ref": f"evidence:sha256:{'5' * 64}",
        "operator_id": "operator:legacy",
        "operator_confirmed_at": "2026-10-04T23:15:00Z",
        "authority_context_sha256": "6" * 64,
        "permission": PHIVID_LEDGER_ADMIT_PERMISSION,
        "operator_confirmed": True,
        "ledger_write_performed": True,
        "evidence_admitted": True,
        "operational_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    payload = {
        **body,
        "ledger_admission_sha256": canonical_sha256(body),
    }
    parsed = PHIVidLedgerAdmissionRecord.from_dict(payload)
    assert parsed.schema_version == "phios.phivid_ledger_admission.v0.1"
    assert parsed.operator_approval_sha256 is None
