from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

MANDALA_CONTRACT_VERSION = "phios.mandala.v0.1"


class Gate(StrEnum):
    PERCEPTION = "PERCEPTION"
    DELIBERATION = "DELIBERATION"
    ACTION = "ACTION"
    MEMORY = "MEMORY"


class MandalaStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    ABORTED = "ABORTED"
    DISPUTED = "DISPUTED"
    UNKNOWN = "UNKNOWN"


class LifecycleState(StrEnum):
    INITIALIZED = "initialized"
    ACTIVE = "active"
    PAUSED = "paused"
    DEGRADED = "degraded"
    TERMINATED = "terminated"


class OriginKind(StrEnum):
    HUMAN = "human"
    SUBSYSTEM = "subsystem"
    TOOL = "tool"
    MODEL = "model"
    FILE = "file"
    DEVICE = "device"
    SERVICE = "service"


def canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, kw_only=True)
class OriginRef:
    kind: OriginKind
    identifier: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "identifier": self.identifier}


@dataclass(frozen=True, kw_only=True)
class AuthorityContext:
    ceiling: tuple[str, ...] = field(default_factory=tuple)
    grants: tuple[str, ...] = field(default_factory=tuple)

    def allows(self, permission: str) -> bool:
        return permission in self.ceiling and permission in self.grants

    def to_dict(self) -> dict[str, list[str]]:
        return {"ceiling": list(self.ceiling), "grants": list(self.grants)}


@dataclass(frozen=True, kw_only=True)
class PhiCoreState:
    task_id: str
    authority: AuthorityContext
    contract_digest: str
    coherence_status: MandalaStatus = MandalaStatus.UNKNOWN
    lifecycle: LifecycleState = LifecycleState.INITIALIZED
    ledger_pointer: str | None = None
    memory_pointer: str | None = None

    @classmethod
    def initialize(
        cls,
        *,
        task_id: str | None = None,
        authority_ceiling: tuple[str, ...] = (),
        explicit_grants: tuple[str, ...] = (),
        ledger_pointer: str | None = None,
        memory_pointer: str | None = None,
    ) -> PhiCoreState:
        authority = AuthorityContext(
            ceiling=authority_ceiling,
            grants=explicit_grants,
        )
        contract_digest = canonical_digest(
            {
                "contract_version": MANDALA_CONTRACT_VERSION,
                "authority": authority.to_dict(),
            }
        )
        return cls(
            task_id=task_id or str(uuid.uuid4()),
            authority=authority,
            contract_digest=contract_digest,
            ledger_pointer=ledger_pointer,
            memory_pointer=memory_pointer,
        )

    def activate(self) -> PhiCoreState:
        return replace(self, lifecycle=LifecycleState.ACTIVE)

    def terminate(self) -> PhiCoreState:
        return replace(self, lifecycle=LifecycleState.TERMINATED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "authority": self.authority.to_dict(),
            "contract_digest": self.contract_digest,
            "coherence_status": self.coherence_status.value,
            "lifecycle": self.lifecycle.value,
            "ledger_pointer": self.ledger_pointer,
            "memory_pointer": self.memory_pointer,
        }


@dataclass(frozen=True, kw_only=True)
class MandalaPacket:
    packet_id: str
    parent_id: str | None
    task_id: str
    gate: Gate
    origin: OriginRef
    payload_digest: str
    authority: AuthorityContext
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    claims: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    allowed_destinations: tuple[Gate, ...] = field(default_factory=tuple)
    resource_budget: dict[str, Any] = field(default_factory=dict)
    contract_version: str = MANDALA_CONTRACT_VERSION
    payload: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        gate: Gate,
        origin: OriginRef,
        payload: dict[str, Any],
        authority: AuthorityContext,
        parent_id: str | None = None,
        evidence_refs: tuple[str, ...] = (),
        claims: tuple[dict[str, Any], ...] = (),
        allowed_destinations: tuple[Gate, ...] = (),
        resource_budget: dict[str, Any] | None = None,
    ) -> MandalaPacket:
        return cls(
            packet_id=str(uuid.uuid4()),
            parent_id=parent_id,
            task_id=task_id,
            gate=gate,
            origin=origin,
            payload_digest=canonical_digest(payload),
            authority=authority,
            evidence_refs=evidence_refs,
            claims=claims,
            allowed_destinations=allowed_destinations,
            resource_budget=dict(resource_budget or {}),
            payload=dict(payload),
        )

    def to_dict(self, *, include_payload: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "packet_id": self.packet_id,
            "parent_id": self.parent_id,
            "task_id": self.task_id,
            "gate": self.gate.value,
            "origin": self.origin.to_dict(),
            "payload_digest": self.payload_digest,
            "authority": self.authority.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "claims": list(self.claims),
            "allowed_destinations": [gate.value for gate in self.allowed_destinations],
            "resource_budget": dict(self.resource_budget),
            "contract_version": self.contract_version,
        }
        if include_payload:
            data["payload"] = dict(self.payload)
        return data
