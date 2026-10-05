"""Local operator CLI for PHIVid evidence admission.

This command is an explicit local operator boundary. It reconstructs the
AuthorityContext from a canonical AuthorityEpoch file, re-validates the PHIVid
envelope and policy receipt, checks temporal freshness, and only then calls the
governed ledger-admission service.

It does not create authority. It consumes authority already present in the
AuthorityEpoch.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from phios.authority_epoch import AuthorityEpoch
from phios.mandala import AuthorityContext
from phios.phivid_admission import PHIVidAdmissionReceipt
from phios.phivid_evidence import validate_phivid_evidence_envelope
from phios.phivid_ledger_admission import (
    PHIVidLedgerAdmissionError,
    admit_phivid_evidence,
)
from phios.phivid_operator_approval import (
    PHIVidOperatorApproval,
    default_key_path,
    load_or_create_operator_key,
    verify_phivid_operator_approval,
)
from phios.spine.ledger import RealityLedger


class PHIVidLedgerOperatorError(ValueError):
    """Raised when the local operator admission boundary is not satisfied."""


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PHIVidLedgerOperatorError(
            f"invalid {label}: {path}"
        ) from exc


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PHIVidLedgerOperatorError(
            f"{label} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PHIVidLedgerOperatorError(
            f"{label} must include a timezone"
        )
    return parsed


def _authority_from_epoch(
    epoch: AuthorityEpoch,
    *,
    operator_id: str,
    confirmed_at: str,
) -> AuthorityContext:
    if epoch.principal_id != operator_id:
        raise PHIVidLedgerOperatorError(
            "operator_id does not match AuthorityEpoch principal_id"
        )

    confirmed = _parse_time(confirmed_at, "confirmed_at")
    observed = _parse_time(epoch.observed_at, "AuthorityEpoch observed_at")
    if confirmed < observed:
        raise PHIVidLedgerOperatorError(
            "operator confirmation predates AuthorityEpoch observation"
        )

    if epoch.next_known_transition_at is not None:
        transition = _parse_time(
            epoch.next_known_transition_at,
            "AuthorityEpoch next_known_transition_at",
        )
        if confirmed >= transition:
            raise PHIVidLedgerOperatorError(
                "AuthorityEpoch is stale at operator confirmation time"
            )

    return AuthorityContext(
        ceiling=epoch.ceiling,
        grants=epoch.grants,
    )


def admit_from_files(
    *,
    envelope_path: Path,
    admission_receipt_path: Path,
    authority_epoch_path: Path,
    ledger_path: Path,
    operator_id: str,
    confirmed_at: str,
    operator_confirmed: bool,
    approval_proof_path: Path,
    operator_key_path: Path,
):
    if operator_confirmed is not True:
        raise PHIVidLedgerOperatorError(
            "explicit --confirm-admit is required"
        )

    intake = validate_phivid_evidence_envelope(
        _read_json(envelope_path, "PHIVid evidence envelope")
    )
    admission_receipt = PHIVidAdmissionReceipt.from_dict(
        _read_json(
            admission_receipt_path,
            "PHIVid admission receipt",
        )
    )
    epoch = AuthorityEpoch.from_dict(
        _read_json(authority_epoch_path, "AuthorityEpoch")
    )
    approval = PHIVidOperatorApproval.from_dict(
        _read_json(approval_proof_path, "PHIVid operator approval")
    )
    key = load_or_create_operator_key(operator_key_path)
    if not verify_phivid_operator_approval(approval, key=key):
        raise PHIVidLedgerOperatorError(
            "PHIVid operator approval HMAC verification failed"
        )
    expected = {
        "envelope_sha256": intake.envelope_sha256,
        "admission_receipt_sha256": (
            admission_receipt.admission_receipt_sha256
        ),
        "authority_epoch_sha256": epoch.authority_epoch_sha256,
        "operator_id": operator_id,
        "approved_at": confirmed_at,
    }
    actual = {
        "envelope_sha256": approval.envelope_sha256,
        "admission_receipt_sha256": approval.admission_receipt_sha256,
        "authority_epoch_sha256": approval.authority_epoch_sha256,
        "operator_id": approval.operator_id,
        "approved_at": approval.approved_at,
    }
    if actual != expected:
        raise PHIVidLedgerOperatorError(
            "PHIVid operator approval does not bind this exact admission"
        )
    authority = _authority_from_epoch(
        epoch,
        operator_id=operator_id,
        confirmed_at=confirmed_at,
    )

    return admit_phivid_evidence(
        intake,
        admission_receipt=admission_receipt,
        authority=authority,
        authority_epoch_sha256=epoch.authority_epoch_sha256,
        operator_approval=approval,
        operator_key=key,
        ledger=RealityLedger(ledger_path),
        operator_id=operator_id,
        operator_confirmed=True,
        operator_confirmed_at=confirmed_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Admit one eligible PHIVid evidence envelope through the "
            "local PhiOS operator boundary."
        )
    )
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--admission-receipt", required=True, type=Path)
    parser.add_argument("--authority-epoch", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--confirmed-at", required=True)
    parser.add_argument("--approval-proof", required=True, type=Path)
    parser.add_argument("--operator-key", type=Path, default=default_key_path())
    parser.add_argument(
        "--confirm-admit",
        action="store_true",
        help="Explicitly confirm this exact evidence admission.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        record = admit_from_files(
            envelope_path=args.envelope,
            admission_receipt_path=args.admission_receipt,
            authority_epoch_path=args.authority_epoch,
            ledger_path=args.ledger,
            operator_id=args.operator_id,
            confirmed_at=args.confirmed_at,
            operator_confirmed=args.confirm_admit,
            approval_proof_path=args.approval_proof,
            operator_key_path=args.operator_key,
        )
    except (
        ValueError,
        PHIVidLedgerAdmissionError,
        PHIVidLedgerOperatorError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "admitted",
                "ledger_admission_sha256": (
                    record.ledger_admission_sha256
                ),
                "envelope_sha256": record.envelope_sha256,
                "output_evidence_ref": record.output_evidence_ref,
                "operator_id": record.operator_id,
                "permission": record.permission,
                "authority_epoch_sha256": record.authority_epoch_sha256,
                "operator_approval_sha256": record.operator_approval_sha256,
                "operator_approval_payload_sha256": (
                    record.operator_approval_payload_sha256
                ),
                "ledger_write_performed": (
                    record.ledger_write_performed
                ),
                "operational_authority": (
                    record.operational_authority
                ),
                "action_authority": record.action_authority,
                "execution_authority": record.execution_authority,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
