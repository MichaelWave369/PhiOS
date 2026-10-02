"""Normalized public NBG-A contract for PhiOS <-> PhiKernel integration.

This module intentionally models only the stable, observable boundary. It does not
encode PhiKernel storage, routing, decay, or TIEKAT implementation internals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

MEMORY_RECEIPT_SCHEMA = "phikernel.nbga.memory-receipt.v1"
BUBBLE_ZERO_STATUS_SCHEMA = "phikernel.nbga.bubble-zero-status.v1"

_FORBIDDEN_FIELDS = frozenset(
    {
        "authority",
        "authority_grant",
        "capability_grant",
        "internal_state",
        "payload",
        "payload_ref",
        "private_state",
        "raw_state",
        "secret",
        "secrets",
    }
)


class NBGContractError(ValueError):
    """Raised when an NBG-A public-contract payload is invalid or overexposes state."""


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise NBGContractError(f"{field} must be an object")
    return value


def _validate_keys(
    payload: Mapping[str, object],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    keys = set(payload)
    leaked = keys & _FORBIDDEN_FIELDS
    if leaked:
        raise NBGContractError(
            "public NBG-A payload exposes forbidden field(s): " + ", ".join(sorted(leaked))
        )
    missing = required - keys
    if missing:
        raise NBGContractError("missing required field(s): " + ", ".join(sorted(missing)))
    unknown = keys - required - optional
    if unknown:
        raise NBGContractError("unknown public-contract field(s): " + ", ".join(sorted(unknown)))


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NBGContractError(f"{field} must be a non-empty string")
    return value


def _require_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise NBGContractError(f"{field} must be an integer >= {minimum}")
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise NBGContractError(f"{field} must be a boolean")
    return value


def _require_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NBGContractError("confidence must be a number from 0 to 1")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise NBGContractError("confidence must be a finite number from 0 to 1")
    return result


def _require_string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise NBGContractError(f"{field} must be an array")
    return tuple(_require_str(item, f"{field}[]") for item in value)


@dataclass(frozen=True, slots=True)
class GearHop:
    """One normalized directional transformation in a proof-carrying retrieval path."""

    gear_id: str
    transform: str
    source: str
    destination: str

    @classmethod
    def from_payload(cls, value: object) -> "GearHop":
        payload = _require_mapping(value, "gear_path[]")
        _validate_keys(
            payload,
            required=frozenset({"gear_id", "transform", "source", "destination"}),
        )
        return cls(
            gear_id=_require_str(payload["gear_id"], "gear_id"),
            transform=_require_str(payload["transform"], "transform"),
            source=_require_str(payload["source"], "source"),
            destination=_require_str(payload["destination"], "destination"),
        )


@dataclass(frozen=True, slots=True)
class MemoryReceipt:
    """Observable memory plus the path and evidence used to retrieve it."""

    bubble_id: str
    bubble_version: int
    observable: str
    trust_state: str
    confidence: float | None
    evidence: tuple[str, ...]
    gear_path: tuple[GearHop, ...]
    event_head: str
    provenance_root: str

    @classmethod
    def from_payload(cls, value: object) -> "MemoryReceipt":
        payload = _require_mapping(value, "memory receipt")
        _validate_keys(
            payload,
            required=frozenset(
                {
                    "schema_version",
                    "bubble_id",
                    "bubble_version",
                    "observable",
                    "trust_state",
                    "evidence",
                    "gear_path",
                    "event_head",
                    "provenance_root",
                }
            ),
            optional=frozenset({"confidence"}),
        )
        if payload["schema_version"] != MEMORY_RECEIPT_SCHEMA:
            raise NBGContractError("unsupported memory receipt schema_version")

        raw_path = payload["gear_path"]
        if not isinstance(raw_path, list):
            raise NBGContractError("gear_path must be an array")

        confidence = None
        if "confidence" in payload and payload["confidence"] is not None:
            confidence = _require_confidence(payload["confidence"])

        return cls(
            bubble_id=_require_str(payload["bubble_id"], "bubble_id"),
            bubble_version=_require_int(payload["bubble_version"], "bubble_version", minimum=1),
            observable=_require_str(payload["observable"], "observable"),
            trust_state=_require_str(payload["trust_state"], "trust_state"),
            confidence=confidence,
            evidence=_require_string_tuple(payload["evidence"], "evidence"),
            gear_path=tuple(GearHop.from_payload(item) for item in raw_path),
            event_head=_require_str(payload["event_head"], "event_head"),
            provenance_root=_require_str(payload["provenance_root"], "provenance_root"),
        )


@dataclass(frozen=True, slots=True)
class BubbleZeroStatus:
    """Minimal continuity status exposed across the PhiKernel public boundary."""

    system_id: str
    epoch: int
    verified: bool
    governance_root: str
    event_log_head: str
    topology_root: str
    anchor_root: str
    commitment_root: str
    last_checkpoint: str | None

    @classmethod
    def from_payload(cls, value: object) -> "BubbleZeroStatus":
        payload = _require_mapping(value, "Bubble Zero status")
        _validate_keys(
            payload,
            required=frozenset(
                {
                    "schema_version",
                    "system_id",
                    "epoch",
                    "verified",
                    "governance_root",
                    "event_log_head",
                    "topology_root",
                    "anchor_root",
                    "commitment_root",
                    "last_checkpoint",
                }
            ),
        )
        if payload["schema_version"] != BUBBLE_ZERO_STATUS_SCHEMA:
            raise NBGContractError("unsupported Bubble Zero schema_version")

        checkpoint = payload["last_checkpoint"]
        if checkpoint is not None:
            checkpoint = _require_str(checkpoint, "last_checkpoint")

        return cls(
            system_id=_require_str(payload["system_id"], "system_id"),
            epoch=_require_int(payload["epoch"], "epoch"),
            verified=_require_bool(payload["verified"], "verified"),
            governance_root=_require_str(payload["governance_root"], "governance_root"),
            event_log_head=_require_str(payload["event_log_head"], "event_log_head"),
            topology_root=_require_str(payload["topology_root"], "topology_root"),
            anchor_root=_require_str(payload["anchor_root"], "anchor_root"),
            commitment_root=_require_str(payload["commitment_root"], "commitment_root"),
            last_checkpoint=checkpoint,
        )


__all__ = [
    "BUBBLE_ZERO_STATUS_SCHEMA",
    "MEMORY_RECEIPT_SCHEMA",
    "BubbleZeroStatus",
    "GearHop",
    "MemoryReceipt",
    "NBGContractError",
]
