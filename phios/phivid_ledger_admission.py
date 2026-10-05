"""Proof-bound PHIVid evidence admission to the Reality Ledger.

Every new admission requires:
- policy ELIGIBLE evidence,
- an authority context granting the PHIVid ledger permission,
- explicit operator confirmation,
- a valid HMAC operator approval for the exact envelope, policy receipt,
  AuthorityEpoch, operator, and timestamp.

The append-only record binds the approval proof and still grants no action or
execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from phios.covenant.models import (
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_bool,
    require_sha256,
    require_text,
)
from phios.mandala import AuthorityContext
from phios.phivid_admission import (
    PHIVidAdmissionDecision,
    PHIVidAdmissionReceipt,
)
from phios.phivid_evidence import PHIVidEvidenceIntake
from phios.phivid_operator_approval import (
    PHIVidOperatorApproval,
    verify_phivid_operator_approval,
)
from phios.phivid_permissions import PHIVID_LEDGER_ADMIT_PERMISSION
from phios.spine.ledger import RealityLedger

PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION = (
    "phios.phivid_ledger_admission.v0.2"
)
PHIVID_LEDGER_ADMISSION_SCHEMA_V01 = "phios.phivid_ledger_admission.v0.1"


class PHIVidLedgerAdmissionError(ValueError):
    """Raised when PHIVid evidence cannot cross the ledger-write boundary."""


def _require_timestamp(value: object, field: str) -> str:
    text = require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PHIVidLedgerAdmissionError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PHIVidLedgerAdmissionError(
            f"{field} must include a timezone"
        )
    return text


@dataclass(frozen=True, slots=True)
class PHIVidLedgerAdmissionRecord:
    admission_receipt_sha256: str
    envelope_sha256: str
    source_receipt_sha256: str
    policy_profile_sha256: str
    plan_id: str
    output_evidence_ref: str
    operator_id: str
    operator_confirmed_at: str
    authority_context_sha256: str
    authority_epoch_sha256: str | None = None
    operator_approval_sha256: str | None = None
    operator_approval_payload_sha256: str | None = None
    operator_approval_proof_hmac_sha256: str | None = None
    permission: str = PHIVID_LEDGER_ADMIT_PERMISSION
    operator_confirmed: bool = True
    operator_approval_verified: bool = True
    ledger_write_performed: bool = True
    evidence_admitted: bool = True
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in {
            PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION,
            PHIVID_LEDGER_ADMISSION_SCHEMA_V01,
        }:
            raise PHIVidLedgerAdmissionError(
                "unsupported PHIVid ledger admission schema"
            )

        for field, digest in (
            ("admission_receipt_sha256", self.admission_receipt_sha256),
            ("envelope_sha256", self.envelope_sha256),
            ("source_receipt_sha256", self.source_receipt_sha256),
            ("policy_profile_sha256", self.policy_profile_sha256),
            ("authority_context_sha256", self.authority_context_sha256),
        ):
            require_sha256(digest, field)

        if self.schema_version == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION:
            for field, digest in (
                ("authority_epoch_sha256", self.authority_epoch_sha256),
                ("operator_approval_sha256", self.operator_approval_sha256),
                (
                    "operator_approval_payload_sha256",
                    self.operator_approval_payload_sha256,
                ),
                (
                    "operator_approval_proof_hmac_sha256",
                    self.operator_approval_proof_hmac_sha256,
                ),
            ):
                require_sha256(digest, field)
            if self.operator_approval_verified is not True:
                raise PHIVidLedgerAdmissionError(
                    "v0.2 admission must record verified operator approval"
                )
        else:
            if any(
                value is not None
                for value in (
                    self.authority_epoch_sha256,
                    self.operator_approval_sha256,
                    self.operator_approval_payload_sha256,
                    self.operator_approval_proof_hmac_sha256,
                )
            ):
                raise PHIVidLedgerAdmissionError(
                    "v0.1 admission cannot carry v0.2 proof bindings"
                )

        require_text(self.plan_id, "plan_id", maximum=256)
        require_text(self.output_evidence_ref, "output_evidence_ref", maximum=256)
        require_text(self.operator_id, "operator_id", maximum=256)
        _require_timestamp(self.operator_confirmed_at, "operator_confirmed_at")

        if self.permission != PHIVID_LEDGER_ADMIT_PERMISSION:
            raise PHIVidLedgerAdmissionError(
                "unsupported PHIVid ledger admission permission"
            )
        if self.operator_confirmed is not True:
            raise PHIVidLedgerAdmissionError(
                "ledger admission must record explicit operator confirmation"
            )
        if self.ledger_write_performed is not True:
            raise PHIVidLedgerAdmissionError(
                "ledger admission record must describe a completed ledger write"
            )
        if self.evidence_admitted is not True:
            raise PHIVidLedgerAdmissionError(
                "ledger admission record must describe admitted evidence"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise PHIVidLedgerAdmissionError(
                "ledger admission record cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema_version": self.schema_version,
            "admission_receipt_sha256": self.admission_receipt_sha256,
            "envelope_sha256": self.envelope_sha256,
            "source_receipt_sha256": self.source_receipt_sha256,
            "policy_profile_sha256": self.policy_profile_sha256,
            "plan_id": self.plan_id,
            "output_evidence_ref": self.output_evidence_ref,
            "operator_id": self.operator_id,
            "operator_confirmed_at": self.operator_confirmed_at,
            "authority_context_sha256": self.authority_context_sha256,
            "permission": self.permission,
            "operator_confirmed": self.operator_confirmed,
            "ledger_write_performed": self.ledger_write_performed,
            "evidence_admitted": self.evidence_admitted,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }
        if self.schema_version == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION:
            body.update(
                {
                    "authority_epoch_sha256": self.authority_epoch_sha256,
                    "operator_approval_sha256": self.operator_approval_sha256,
                    "operator_approval_payload_sha256": (
                        self.operator_approval_payload_sha256
                    ),
                    "operator_approval_proof_hmac_sha256": (
                        self.operator_approval_proof_hmac_sha256
                    ),
                    "operator_approval_verified": self.operator_approval_verified,
                }
            )
        return body

    @property
    def ledger_admission_sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["ledger_admission_sha256"] = self.ledger_admission_sha256
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "PHIVidLedgerAdmissionRecord":
        data = expect_mapping(value, "PHIVid ledger admission record")
        schema = require_text(data.get("schema_version"), "schema_version", maximum=64)

        common = {
            "schema_version",
            "admission_receipt_sha256",
            "envelope_sha256",
            "source_receipt_sha256",
            "policy_profile_sha256",
            "plan_id",
            "output_evidence_ref",
            "operator_id",
            "operator_confirmed_at",
            "authority_context_sha256",
            "permission",
            "operator_confirmed",
            "ledger_write_performed",
            "evidence_admitted",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "ledger_admission_sha256",
        }
        if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION:
            expected = common | {
                "authority_epoch_sha256",
                "operator_approval_sha256",
                "operator_approval_payload_sha256",
                "operator_approval_proof_hmac_sha256",
                "operator_approval_verified",
            }
        elif schema == PHIVID_LEDGER_ADMISSION_SCHEMA_V01:
            expected = common
        else:
            raise PHIVidLedgerAdmissionError(
                "unsupported PHIVid ledger admission schema"
            )
        expect_exact_keys(data, expected, "PHIVid ledger admission record")

        claimed = require_sha256(
            data["ledger_admission_sha256"],
            "ledger_admission_sha256",
        )
        bool_fields = (
            "operator_confirmed",
            "ledger_write_performed",
            "evidence_admitted",
            "operational_authority",
            "action_authority",
            "execution_authority",
        )
        for field in bool_fields:
            require_bool(data[field], field)
        if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION:
            require_bool(
                data["operator_approval_verified"],
                "operator_approval_verified",
            )

        record = cls(
            schema_version=schema,
            admission_receipt_sha256=require_sha256(
                data["admission_receipt_sha256"],
                "admission_receipt_sha256",
            ),
            envelope_sha256=require_sha256(
                data["envelope_sha256"], "envelope_sha256"
            ),
            source_receipt_sha256=require_sha256(
                data["source_receipt_sha256"], "source_receipt_sha256"
            ),
            policy_profile_sha256=require_sha256(
                data["policy_profile_sha256"], "policy_profile_sha256"
            ),
            plan_id=require_text(data["plan_id"], "plan_id", maximum=256),
            output_evidence_ref=require_text(
                data["output_evidence_ref"], "output_evidence_ref", maximum=256
            ),
            operator_id=require_text(
                data["operator_id"], "operator_id", maximum=256
            ),
            operator_confirmed_at=_require_timestamp(
                data["operator_confirmed_at"], "operator_confirmed_at"
            ),
            authority_context_sha256=require_sha256(
                data["authority_context_sha256"], "authority_context_sha256"
            ),
            authority_epoch_sha256=(
                require_sha256(data["authority_epoch_sha256"], "authority_epoch_sha256")
                if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION
                else None
            ),
            operator_approval_sha256=(
                require_sha256(data["operator_approval_sha256"], "operator_approval_sha256")
                if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION
                else None
            ),
            operator_approval_payload_sha256=(
                require_sha256(
                    data["operator_approval_payload_sha256"],
                    "operator_approval_payload_sha256",
                )
                if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION
                else None
            ),
            operator_approval_proof_hmac_sha256=(
                require_sha256(
                    data["operator_approval_proof_hmac_sha256"],
                    "operator_approval_proof_hmac_sha256",
                )
                if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION
                else None
            ),
            permission=require_text(
                data["permission"], "permission", maximum=128
            ),
            operator_confirmed=data["operator_confirmed"],
            operator_approval_verified=(
                data["operator_approval_verified"]
                if schema == PHIVID_LEDGER_ADMISSION_SCHEMA_VERSION
                else False
            ),
            ledger_write_performed=data["ledger_write_performed"],
            evidence_admitted=data["evidence_admitted"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )
        if record.ledger_admission_sha256 != claimed:
            raise PHIVidLedgerAdmissionError(
                "PHIVid ledger admission record hash mismatch"
            )
        return record


def admit_phivid_evidence(
    intake: PHIVidEvidenceIntake,
    *,
    admission_receipt: PHIVidAdmissionReceipt,
    authority: AuthorityContext,
    authority_epoch_sha256: str,
    operator_approval: PHIVidOperatorApproval,
    operator_key: bytes,
    ledger: RealityLedger,
    operator_id: str,
    operator_confirmed: bool,
    operator_confirmed_at: str,
) -> PHIVidLedgerAdmissionRecord:
    if operator_confirmed is not True:
        raise PHIVidLedgerAdmissionError(
            "explicit operator confirmation is required"
        )

    operator = require_text(operator_id, "operator_id", maximum=256)
    confirmed_at = _require_timestamp(
        operator_confirmed_at, "operator_confirmed_at"
    )
    epoch_sha = require_sha256(
        authority_epoch_sha256, "authority_epoch_sha256"
    )

    if not authority.allows(PHIVID_LEDGER_ADMIT_PERMISSION):
        raise PHIVidLedgerAdmissionError(
            "authority context does not grant evidence.phivid.ledger.admit"
        )
    if (
        admission_receipt.decision is not PHIVidAdmissionDecision.ELIGIBLE
        or admission_receipt.eligible_for_ledger_admission is not True
    ):
        raise PHIVidLedgerAdmissionError(
            "PHIVid evidence is not eligible for ledger admission"
        )

    bindings = (
        (admission_receipt.envelope_sha256, intake.envelope_sha256, "envelope_sha256"),
        (
            admission_receipt.source_receipt_sha256,
            intake.source_receipt_sha256,
            "source_receipt_sha256",
        ),
        (admission_receipt.plan_id, intake.plan_id, "plan_id"),
        (
            admission_receipt.output_evidence_ref,
            intake.output_evidence_ref,
            "output_evidence_ref",
        ),
    )
    for receipt_value, intake_value, field in bindings:
        if receipt_value != intake_value:
            raise PHIVidLedgerAdmissionError(
                f"admission receipt {field} does not match validated intake"
            )

    if not verify_phivid_operator_approval(
        operator_approval, key=operator_key
    ):
        raise PHIVidLedgerAdmissionError(
            "PHIVid operator approval HMAC verification failed"
        )

    approval_bindings = (
        (
            operator_approval.envelope_sha256,
            intake.envelope_sha256,
            "operator approval envelope_sha256",
        ),
        (
            operator_approval.admission_receipt_sha256,
            admission_receipt.admission_receipt_sha256,
            "operator approval admission_receipt_sha256",
        ),
        (
            operator_approval.authority_epoch_sha256,
            epoch_sha,
            "operator approval authority_epoch_sha256",
        ),
        (
            operator_approval.operator_id,
            operator,
            "operator approval operator_id",
        ),
        (
            operator_approval.approved_at,
            confirmed_at,
            "operator approval approved_at",
        ),
    )
    for approval_value, expected_value, field in approval_bindings:
        if approval_value != expected_value:
            raise PHIVidLedgerAdmissionError(
                f"{field} does not match admission request"
            )

    existing = ledger.phivid_evidence_admission_records(
        envelope_sha256=intake.envelope_sha256
    )
    if existing:
        raise PHIVidLedgerAdmissionError(
            "PHIVid evidence envelope is already admitted"
        )

    authority_context_sha256 = canonical_sha256(authority.to_dict())
    approval_sha256 = canonical_sha256(operator_approval.to_dict())
    record = PHIVidLedgerAdmissionRecord(
        admission_receipt_sha256=admission_receipt.admission_receipt_sha256,
        envelope_sha256=intake.envelope_sha256,
        source_receipt_sha256=intake.source_receipt_sha256,
        policy_profile_sha256=admission_receipt.policy_profile_sha256,
        plan_id=intake.plan_id,
        output_evidence_ref=intake.output_evidence_ref,
        operator_id=operator,
        operator_confirmed_at=confirmed_at,
        authority_context_sha256=authority_context_sha256,
        authority_epoch_sha256=epoch_sha,
        operator_approval_sha256=approval_sha256,
        operator_approval_payload_sha256=operator_approval.payload_sha256,
        operator_approval_proof_hmac_sha256=(
            operator_approval.proof_hmac_sha256
        ),
        operator_approval_verified=True,
    )
    ledger.append_phivid_evidence_admission_record(record)
    return record
