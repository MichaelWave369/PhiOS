"""Deterministic identity-seal records for Covenant Runtime CR-01.

An IdentitySeal identifies exact implementation/provenance state. It does not
assert trust, permission, action authority, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import (
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_bool,
    require_sha256,
    require_text,
)

IDENTITY_SEAL_SCHEMA_VERSION = "phios.identity_seal.v0.1"


class IdentitySubjectKind(str, Enum):
    AGENT = "agent"
    APP = "app"
    TOOL = "tool"
    MODEL = "model"
    WORKFLOW = "workflow"
    RESOURCE = "resource"
    CAPABILITY = "capability"


@dataclass(frozen=True, slots=True)
class IdentitySeal:
    """Bind one canonical subject identity to exact provenance digests."""

    subject_id: str
    subject_kind: IdentitySubjectKind
    implementation_sha256: str
    manifest_sha256: str
    source_sha256: str
    issuer_id: str
    issuer_key_id: str
    trusted_identity: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = IDENTITY_SEAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != IDENTITY_SEAL_SCHEMA_VERSION:
            raise ValueError(f"Unsupported identity seal schema: {self.schema_version}")
        require_text(self.subject_id, "subject_id", maximum=128)
        if not isinstance(self.subject_kind, IdentitySubjectKind):
            raise ValueError("subject_kind must be a supported IdentitySubjectKind")
        require_sha256(self.implementation_sha256, "implementation_sha256")
        require_sha256(self.manifest_sha256, "manifest_sha256")
        require_sha256(self.source_sha256, "source_sha256")
        require_text(self.issuer_id, "issuer_id", maximum=128)
        require_text(self.issuer_key_id, "issuer_key_id", maximum=128)
        if self.trusted_identity is not False:
            raise ValueError("CR-01 IdentitySeal does not establish trusted identity")
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError("IdentitySeal cannot carry action or execution authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "implementation_sha256": self.implementation_sha256,
            "manifest_sha256": self.manifest_sha256,
            "source_sha256": self.source_sha256,
            "issuer_id": self.issuer_id,
            "issuer_key_id": self.issuer_key_id,
            "trusted_identity": self.trusted_identity,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["seal_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> IdentitySeal:
        data = expect_mapping(value, "identity seal")
        expected = {
            "schema_version",
            "subject_id",
            "subject_kind",
            "implementation_sha256",
            "manifest_sha256",
            "source_sha256",
            "issuer_id",
            "issuer_key_id",
            "trusted_identity",
            "action_authority",
            "execution_authority",
            "seal_sha256",
        }
        expect_exact_keys(data, expected, "identity seal")
        try:
            subject_kind = IdentitySubjectKind(
                require_text(
                    data["subject_kind"],
                    "subject_kind",
                    maximum=32,
                )
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported identity subject kind: {data['subject_kind']}"
            ) from exc
        seal = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            subject_id=require_text(data["subject_id"], "subject_id", maximum=128),
            subject_kind=subject_kind,
            implementation_sha256=require_sha256(
                data["implementation_sha256"],
                "implementation_sha256",
            ),
            manifest_sha256=require_sha256(
                data["manifest_sha256"],
                "manifest_sha256",
            ),
            source_sha256=require_sha256(
                data["source_sha256"],
                "source_sha256",
            ),
            issuer_id=require_text(data["issuer_id"], "issuer_id", maximum=128),
            issuer_key_id=require_text(
                data["issuer_key_id"],
                "issuer_key_id",
                maximum=128,
            ),
            trusted_identity=require_bool(
                data["trusted_identity"],
                "trusted_identity",
            ),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["seal_sha256"] != seal.sha256():
            raise ValueError("identity seal digest does not match canonical seal")
        return seal
