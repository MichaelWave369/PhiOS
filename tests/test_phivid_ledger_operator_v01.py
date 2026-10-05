from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

from phios.authority_epoch import AuthorityEpoch
from phios.covenant.models import canonical_sha256
from phios.evidence_ref import EvidenceRef
from phios.mandala import (
    AuthoritativeAuthorityEvent,
    AuthorityEventKind,
)
from phios.phivid_admission import (
    PHIVidAdmissionPolicy,
    evaluate_phivid_admission,
)
from phios.phivid_evidence import validate_phivid_evidence_envelope
from phios.phivid_ledger_admission import (
    PHIVID_LEDGER_ADMIT_PERMISSION,
)


def _envelope() -> dict[str, object]:
    source = EvidenceRef.build(
        source_id="clip-a",
        source_kind="phivid.video.source",
        source_version="phivid.render-receipt.v0.2",
        content_sha256="3" * 64,
        observed_at="2026-10-04T22:56:00Z",
        exactness_class="byte_exact",
    )
    output = EvidenceRef.build(
        source_id="phivid:render:render-42",
        source_kind="phivid.video.render",
        source_version="phivid.render-receipt.v0.2",
        content_sha256="4" * 64,
        observed_at="2026-10-04T22:56:00Z",
        transformation_lineage_sha256s=("1" * 64, "2" * 64),
        exactness_class="byte_exact",
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
        "warnings": ["render_used_cpu_encoder"],
        "operational_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    body["envelope_sha256"] = canonical_sha256(body)
    return body


def _write_inputs(
    root: Path,
    *,
    grant_permission: bool = True,
    expiry: str | None = None,
) -> tuple[Path, Path, Path, Path]:
    envelope = _envelope()
    intake = validate_phivid_evidence_envelope(envelope)
    admission = evaluate_phivid_admission(
        intake,
        policy=PHIVidAdmissionPolicy.strict_default(),
        evaluated_at="2026-10-04T23:10:00Z",
    )

    envelope_path = root / "envelope.json"
    receipt_path = root / "admission.json"
    epoch_path = root / "authority-epoch.json"
    ledger_path = root / "ledger" / "reality-ledger.jsonl"
    envelope_path.write_text(
        json.dumps(envelope, indent=2),
        encoding="utf-8",
    )
    receipt_path.write_text(
        json.dumps(admission.to_dict(), indent=2),
        encoding="utf-8",
    )

    events = ()
    if grant_permission:
        events = (
            AuthoritativeAuthorityEvent(
                event_id="grant-phivid-ledger-admit",
                sequence=0,
                kind=AuthorityEventKind.GRANT,
                permission=PHIVID_LEDGER_ADMIT_PERMISSION,
                authority_source="operator:local",
                effective_at="2026-10-04T23:00:00+00:00",
                expires_at=expiry,
            ),
        )
    epoch = AuthorityEpoch.build(
        principal_id="operator:local",
        policy_sha256="a" * 64,
        ceiling=(PHIVID_LEDGER_ADMIT_PERMISSION,),
        events=events,
        observed_at="2026-10-04T23:05:00+00:00",
    )
    epoch_path.write_text(
        json.dumps(epoch.to_dict(), indent=2),
        encoding="utf-8",
    )
    return envelope_path, receipt_path, epoch_path, ledger_path


def _run(
    *,
    envelope: Path,
    receipt: Path,
    epoch: Path,
    ledger: Path,
    operator_id: str = "operator:local",
    confirmed_at: str = "2026-10-04T23:15:00+00:00",
    confirm: bool = True,
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        "-m",
        "phios.phivid_ledger_operator",
        "--envelope",
        str(envelope),
        "--admission-receipt",
        str(receipt),
        "--authority-epoch",
        str(epoch),
        "--ledger",
        str(ledger),
        "--operator-id",
        operator_id,
        "--confirmed-at",
        confirmed_at,
    ]
    if confirm:
        args.append("--confirm-admit")
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
    )


def test_operator_cli_reconstructs_authority_and_admits(
    tmp_path: Path,
) -> None:
    envelope, receipt, epoch, ledger = _write_inputs(tmp_path)
    result = _run(
        envelope=envelope,
        receipt=receipt,
        epoch=epoch,
        ledger=ledger,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "admitted"
    assert payload["ledger_write_performed"] is True
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert len(payload["ledger_admission_sha256"]) == 64

    admission_log = ledger.parent / "phivid-evidence-admissions.jsonl"
    rows = [
        json.loads(line)
        for line in admission_log.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1


def test_cli_requires_explicit_confirmation_and_writes_nothing(
    tmp_path: Path,
) -> None:
    envelope, receipt, epoch, ledger = _write_inputs(tmp_path)
    result = _run(
        envelope=envelope,
        receipt=receipt,
        epoch=epoch,
        ledger=ledger,
        confirm=False,
    )

    assert result.returncode == 1
    assert "confirm-admit" in json.loads(result.stdout)["error"]
    assert not (ledger.parent / "phivid-evidence-admissions.jsonl").exists()


def test_cli_refuses_epoch_without_required_grant(tmp_path: Path) -> None:
    envelope, receipt, epoch, ledger = _write_inputs(
        tmp_path,
        grant_permission=False,
    )
    result = _run(
        envelope=envelope,
        receipt=receipt,
        epoch=epoch,
        ledger=ledger,
    )

    assert result.returncode == 1
    assert "does not grant" in json.loads(result.stdout)["error"]


def test_cli_refuses_operator_principal_mismatch(tmp_path: Path) -> None:
    envelope, receipt, epoch, ledger = _write_inputs(tmp_path)
    result = _run(
        envelope=envelope,
        receipt=receipt,
        epoch=epoch,
        ledger=ledger,
        operator_id="operator:other",
    )

    assert result.returncode == 1
    assert "principal_id" in json.loads(result.stdout)["error"]


def test_cli_refuses_stale_authority_epoch(tmp_path: Path) -> None:
    envelope, receipt, epoch, ledger = _write_inputs(
        tmp_path,
        expiry="2026-10-04T23:12:00+00:00",
    )
    result = _run(
        envelope=envelope,
        receipt=receipt,
        epoch=epoch,
        ledger=ledger,
        confirmed_at="2026-10-04T23:15:00+00:00",
    )

    assert result.returncode == 1
    assert "stale" in json.loads(result.stdout)["error"]
    assert not (ledger.parent / "phivid-evidence-admissions.jsonl").exists()
