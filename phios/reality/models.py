from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from phios.mandala import MandalaPacket, RealityReceipt


class RealityClaimKind(StrEnum):
    SOURCE_CONTAINS_TEXT = "source_contains_text"
    WORLD_STATE = "world_state"
    LOCAL_INTERFACE_STATE = "local_interface_state"
    LOCAL_TCP_LISTENER_STATE = "local_tcp_listener_state"


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
    interface_name: str | None = None
    expected_is_up: bool | None = None
    local_port: int | None = None
    local_address: str | None = None
    expected_listening: bool | None = None

    @classmethod
    def create(
        cls,
        *,
        kind: RealityClaimKind,
        statement: str,
        evidence_refs: tuple[str, ...] = (),
        expected_text: str | None = None,
        case_sensitive: bool = False,
        interface_name: str | None = None,
        expected_is_up: bool | None = None,
        local_port: int | None = None,
        local_address: str | None = None,
        expected_listening: bool | None = None,
    ) -> "RealityClaim":
        return cls(
            claim_id=str(uuid.uuid4()),
            kind=kind,
            statement=statement,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            expected_text=expected_text,
            case_sensitive=case_sensitive,
            interface_name=interface_name,
            expected_is_up=expected_is_up,
            local_port=local_port,
            local_address=local_address,
            expected_listening=expected_listening,
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

        if self.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
            if self.interface_name is None or not self.interface_name.strip():
                errors.append("local_interface_claim_requires_interface_name")
            if self.expected_is_up is None:
                errors.append("local_interface_claim_requires_expected_state")

        if self.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
            if self.local_port is None:
                errors.append("local_tcp_claim_requires_port")
            elif not 1 <= self.local_port <= 65535:
                errors.append("local_tcp_claim_invalid_port")
            if self.local_address is not None and not self.local_address.strip():
                errors.append("local_tcp_claim_invalid_address")
            if self.expected_listening is None:
                errors.append("local_tcp_claim_requires_expected_state")

        return tuple(errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind.value,
            "statement": self.statement,
            "evidence_refs": list(self.evidence_refs),
            "expected_text": self.expected_text,
            "case_sensitive": self.case_sensitive,
            "interface_name": self.interface_name,
            "expected_is_up": self.expected_is_up,
            "local_port": self.local_port,
            "local_address": self.local_address,
            "expected_listening": self.expected_listening,
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
