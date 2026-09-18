from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from phios.mandala import MandalaPacket, RealityReceipt


class RealityClaimKind(StrEnum):
    SOURCE_CONTAINS_TEXT = "source_contains_text"
    WORLD_STATE = "world_state"


class RealityVerdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, kw_only=True)
class RealityClaim:
    claim_id: str
    kind: RealityClaimKind
    statement: str
    evidence_refs: tuple[str, ...] = ()
    expected_text: str | None = None
    case_sensitive: bool = False

    @classmethod
    def create(
        cls,
        *,
        kind: RealityClaimKind,
        statement: str,
        evidence_refs: tuple[str, ...] = (),
        expected_text: str | None = None,
        case_sensitive: bool = False,
    ) -> "RealityClaim":
        return cls(
            claim_id=str(uuid.uuid4()),
            kind=kind,
            statement=statement,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            expected_text=expected_text,
            case_sensitive=case_sensitive,
        )

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.statement.strip():
            errors.append("empty_statement")

        if self.kind is RealityClaimKind.SOURCE_CONTAINS_TEXT:
            if not self.evidence_refs:
                errors.append("source_claim_requires_evidence")
            if self.expected_text is None or not self.expected_text.strip():
                errors.append("source_claim_requires_expected_text")

        return tuple(errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind.value,
            "statement": self.statement,
            "evidence_refs": list(self.evidence_refs),
            "expected_text": self.expected_text,
            "case_sensitive": self.case_sensitive,
        }


@dataclass(frozen=True, kw_only=True)
class RealityVerificationResult:
    packet: MandalaPacket
    receipt: RealityReceipt
    claim_results: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet": self.packet.to_dict(),
            "receipt": self.receipt.to_dict(),
            "claim_results": [dict(item) for item in self.claim_results],
        }
