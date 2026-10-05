"""HMAC-bound local operator proof for PHIVid evidence admission.

The proof binds one operator to one exact PHIVid evidence envelope, one exact
policy admission receipt, and one exact AuthorityEpoch. It authorizes no action
by itself. The ledger-admission command must still verify the proof, reconstruct
authority, and receive explicit effect confirmation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from phios.covenant.models import (
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_sha256,
    require_text,
)
from phios.phivid_ledger_admission import PHIVID_LEDGER_ADMIT_PERMISSION

PHIVID_OPERATOR_APPROVAL_SCHEMA_VERSION = (
    "phios.phivid_operator_approval.v0.1"
)


class PHIVidOperatorApprovalError(ValueError):
    """Raised when a PHIVid operator approval proof is invalid."""


def _timestamp(value: object, field: str) -> str:
    text = require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PHIVidOperatorApprovalError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PHIVidOperatorApprovalError(
            f"{field} must include a timezone"
        )
    return text


def default_key_path() -> Path:
    configured = os.environ.get("PHIOS_PHIVID_OPERATOR_KEY")
    if configured:
        return Path(configured).expanduser()
    state_root = Path(
        os.environ.get("PHIOS_STATE_ROOT", str(Path.home() / ".phios"))
    ).expanduser()
    return state_root / "authority" / "phivid-ledger-admission.key"


def load_or_create_operator_key(path: Path) -> bytes:
    resolved = path.expanduser()
    resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    try:
        fd = os.open(
            resolved,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        pass
    else:
        try:
            os.write(fd, secrets.token_bytes(32).hex().encode("ascii") + b"\n")
        finally:
            os.close(fd)

    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise PHIVidOperatorApprovalError(
            "PHIVid operator key must not grant group/other access"
        )

    raw = resolved.read_text(encoding="ascii").strip()
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw):
        raise PHIVidOperatorApprovalError(
            "PHIVid operator key must contain 32 random bytes as lowercase hex"
        )
    return bytes.fromhex(raw)


@dataclass(frozen=True, slots=True)
class PHIVidOperatorApproval:
    envelope_sha256: str
    admission_receipt_sha256: str
    authority_epoch_sha256: str
    operator_id: str
    approved_at: str
    payload_sha256: str
    permission: str = PHIVID_LEDGER_ADMIT_PERMISSION
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = PHIVID_OPERATOR_APPROVAL_SCHEMA_VERSION
    proof_hmac_sha256: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != PHIVID_OPERATOR_APPROVAL_SCHEMA_VERSION:
            raise PHIVidOperatorApprovalError(
                "unsupported PHIVid operator approval schema"
            )
        for field, value in (
            ("envelope_sha256", self.envelope_sha256),
            ("admission_receipt_sha256", self.admission_receipt_sha256),
            ("authority_epoch_sha256", self.authority_epoch_sha256),
            ("payload_sha256", self.payload_sha256),
        ):
            require_sha256(value, field)
        require_text(self.operator_id, "operator_id", maximum=256)
        _timestamp(self.approved_at, "approved_at")
        if self.permission != PHIVID_LEDGER_ADMIT_PERMISSION:
            raise PHIVidOperatorApprovalError(
                "unsupported PHIVid operator approval permission"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise PHIVidOperatorApprovalError(
                "operator approval proof cannot carry authority"
            )
        if self.proof_hmac_sha256:
            require_sha256(
                self.proof_hmac_sha256,
                "proof_hmac_sha256",
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "envelope_sha256": self.envelope_sha256,
            "admission_receipt_sha256": self.admission_receipt_sha256,
            "authority_epoch_sha256": self.authority_epoch_sha256,
            "operator_id": self.operator_id,
            "approved_at": self.approved_at,
            "payload_sha256": self.payload_sha256,
            "permission": self.permission,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.body_dict(),
            "proof_hmac_sha256": self.proof_hmac_sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PHIVidOperatorApproval":
        data = expect_mapping(value, "PHIVid operator approval")
        expected = {
            "schema_version",
            "envelope_sha256",
            "admission_receipt_sha256",
            "authority_epoch_sha256",
            "operator_id",
            "approved_at",
            "payload_sha256",
            "permission",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "proof_hmac_sha256",
        }
        expect_exact_keys(data, expected, "PHIVid operator approval")
        return cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            envelope_sha256=require_sha256(
                data["envelope_sha256"],
                "envelope_sha256",
            ),
            admission_receipt_sha256=require_sha256(
                data["admission_receipt_sha256"],
                "admission_receipt_sha256",
            ),
            authority_epoch_sha256=require_sha256(
                data["authority_epoch_sha256"],
                "authority_epoch_sha256",
            ),
            operator_id=require_text(
                data["operator_id"],
                "operator_id",
                maximum=256,
            ),
            approved_at=_timestamp(data["approved_at"], "approved_at"),
            payload_sha256=require_sha256(
                data["payload_sha256"],
                "payload_sha256",
            ),
            permission=require_text(
                data["permission"],
                "permission",
                maximum=128,
            ),
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
            proof_hmac_sha256=require_sha256(
                data["proof_hmac_sha256"],
                "proof_hmac_sha256",
            ),
        )


def approval_payload_sha256(
    *,
    envelope_sha256: str,
    admission_receipt_sha256: str,
    authority_epoch_sha256: str,
    operator_id: str,
    approved_at: str,
) -> str:
    return canonical_sha256(
        {
            "envelope_sha256": require_sha256(
                envelope_sha256,
                "envelope_sha256",
            ),
            "admission_receipt_sha256": require_sha256(
                admission_receipt_sha256,
                "admission_receipt_sha256",
            ),
            "authority_epoch_sha256": require_sha256(
                authority_epoch_sha256,
                "authority_epoch_sha256",
            ),
            "operator_id": require_text(
                operator_id,
                "operator_id",
                maximum=256,
            ),
            "approved_at": _timestamp(approved_at, "approved_at"),
            "permission": PHIVID_LEDGER_ADMIT_PERMISSION,
        }
    )


def create_phivid_operator_approval(
    *,
    envelope_sha256: str,
    admission_receipt_sha256: str,
    authority_epoch_sha256: str,
    operator_id: str,
    approved_at: str,
    key: bytes,
) -> PHIVidOperatorApproval:
    payload_sha256 = approval_payload_sha256(
        envelope_sha256=envelope_sha256,
        admission_receipt_sha256=admission_receipt_sha256,
        authority_epoch_sha256=authority_epoch_sha256,
        operator_id=operator_id,
        approved_at=approved_at,
    )
    unsigned = PHIVidOperatorApproval(
        envelope_sha256=envelope_sha256,
        admission_receipt_sha256=admission_receipt_sha256,
        authority_epoch_sha256=authority_epoch_sha256,
        operator_id=operator_id,
        approved_at=approved_at,
        payload_sha256=payload_sha256,
    )
    proof = hmac.new(
        key,
        json.dumps(
            unsigned.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return PHIVidOperatorApproval(
        envelope_sha256=unsigned.envelope_sha256,
        admission_receipt_sha256=unsigned.admission_receipt_sha256,
        authority_epoch_sha256=unsigned.authority_epoch_sha256,
        operator_id=unsigned.operator_id,
        approved_at=unsigned.approved_at,
        payload_sha256=unsigned.payload_sha256,
        permission=unsigned.permission,
        operational_authority=unsigned.operational_authority,
        action_authority=unsigned.action_authority,
        execution_authority=unsigned.execution_authority,
        schema_version=unsigned.schema_version,
        proof_hmac_sha256=proof,
    )


def verify_phivid_operator_approval(
    approval: PHIVidOperatorApproval,
    *,
    key: bytes,
) -> bool:
    expected_payload = approval_payload_sha256(
        envelope_sha256=approval.envelope_sha256,
        admission_receipt_sha256=approval.admission_receipt_sha256,
        authority_epoch_sha256=approval.authority_epoch_sha256,
        operator_id=approval.operator_id,
        approved_at=approval.approved_at,
    )
    if not hmac.compare_digest(
        expected_payload,
        approval.payload_sha256,
    ):
        return False
    expected = hmac.new(
        key,
        json.dumps(
            approval.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, approval.proof_hmac_sha256)


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PHIVidOperatorApprovalError(
            f"invalid {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise PHIVidOperatorApprovalError(
            f"{label} must be a JSON object"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create one HMAC-bound PHIVid operator admission proof."
    )
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--admission-receipt", required=True, type=Path)
    parser.add_argument("--authority-epoch", required=True, type=Path)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--key", type=Path, default=default_key_path())
    args = parser.parse_args(argv)

    envelope = _read_json(args.envelope, "PHIVid evidence envelope")
    receipt = _read_json(args.admission_receipt, "PHIVid admission receipt")
    epoch = _read_json(args.authority_epoch, "AuthorityEpoch")

    approval = create_phivid_operator_approval(
        envelope_sha256=require_sha256(
            envelope.get("envelope_sha256"),
            "envelope_sha256",
        ),
        admission_receipt_sha256=require_sha256(
            receipt.get("admission_receipt_sha256"),
            "admission_receipt_sha256",
        ),
        authority_epoch_sha256=require_sha256(
            epoch.get("authority_epoch_sha256"),
            "authority_epoch_sha256",
        ),
        operator_id=args.operator_id,
        approved_at=args.approved_at,
        key=load_or_create_operator_key(args.key),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(approval.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "approved",
                "payload_sha256": approval.payload_sha256,
                "proof_hmac_sha256": approval.proof_hmac_sha256,
                "output": str(args.out),
                "operational_authority": False,
                "action_authority": False,
                "execution_authority": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
