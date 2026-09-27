"""Narrow PhiVessel ↔ PhiOS bridge contracts.

Bridge v0.1 exposes three operations only:

    observe(...)
    propose(work_id, packet_refs, proposal_type)
    execute(action_lease_sha256)

Observation and proposal carry no action authority. Proposal is an append-only
local Ledger record, not an AuthorityRequest. Execution delegates only an
already-issued ActionLease identity to the v0.35 Ghost-Walk execution handoff.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Mapping, Protocol

from phios.macro_action_lease_service import (
    GhostWalkActionLeaseError,
    GhostWalkActionLeaseRecord,
)
from phios.macro_lease_execution_handoff import (
    GhostWalkLeaseExecutionError,
    GhostWalkLeaseExecutionReceipt,
)
from phios.spine.ledger import RealityLedger

PHIVESSEL_BRIDGE_VERSION = "PV-PHIOS-BRIDGE-0.1"
PHIVESSEL_PROPOSAL_SCHEMA_VERSION = "phios.phivessel_proposal.v0.1"
PHIVESSEL_OBSERVATION_SCHEMA_VERSION = "phios.phivessel_observation.v0.1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WORK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


class PhiVesselBridgeError(ValueError):
    """Raised when bridge inputs or persisted bridge state are malformed."""


class PhiVesselBridgeUnavailableError(PhiVesselBridgeError):
    """Raised when a trusted local bridge dependency is not mounted."""


class PhiVesselProposalType(StrEnum):
    OBSERVE = "OBSERVE"
    BUILD = "BUILD"
    PATCH = "PATCH"
    RUN = "RUN"
    MOVE = "MOVE"
    WRITE = "WRITE"
    DEPLOY = "DEPLOY"


class PhiVesselObservationKind(StrEnum):
    BRIDGE_STATUS = "BRIDGE_STATUS"
    GHOSTWALK_CONTROL = "GHOSTWALK_CONTROL"
    LEASE_STATUS = "LEASE_STATUS"


def _require_text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise PhiVesselBridgeError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise PhiVesselBridgeError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise PhiVesselBridgeError(f"{field} contains control characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise PhiVesselBridgeError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PhiVesselBridgeError("bridge payload must be canonical JSON") from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PhiVesselBridgeError("bridge clock must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _packet_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise PhiVesselBridgeError("packet_refs must contain at least one reference")
    if len(values) > 64:
        raise PhiVesselBridgeError("packet_refs exceeds 64 references")
    normalized = tuple(
        sorted(
            {
                _require_text(value, "packet_ref", maximum=256)
                for value in values
            }
        )
    )
    if not normalized:
        raise PhiVesselBridgeError("packet_refs must contain at least one reference")
    return normalized


class GhostWalkSurfacePort(Protocol):
    def snapshot(self) -> object: ...


class GhostWalkLeaseExecutionPort(Protocol):
    def execute(
        self,
        *,
        action_lease_sha256: str,
    ) -> GhostWalkLeaseExecutionReceipt: ...


@dataclass(frozen=True, slots=True)
class PhiVesselProposalPacket:
    work_id: str
    packet_refs: tuple[str, ...]
    proposal_type: PhiVesselProposalType
    source_id: str
    proposed_at: str
    proposal_id: str
    authority_request_created: bool = False
    authorization_granted: bool = False
    action_lease_created: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    desktop_effect_performed: bool = False
    schema_version: str = PHIVESSEL_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PHIVESSEL_PROPOSAL_SCHEMA_VERSION:
            raise PhiVesselBridgeError("unsupported PhiVessel proposal schema")
        if not _WORK_ID_RE.fullmatch(self.work_id):
            raise PhiVesselBridgeError("work_id must be a canonical bounded identifier")
        _packet_refs(self.packet_refs)
        _require_text(self.source_id, "source_id", maximum=256)
        _require_text(self.proposed_at, "proposed_at", maximum=64)
        if not self.proposal_id.startswith("pvp:") or len(self.proposal_id) != 28:
            raise PhiVesselBridgeError("proposal_id is malformed")
        if any(
            (
                self.authority_request_created,
                self.authorization_granted,
                self.action_lease_created,
                self.policy_authority,
                self.operational_authority,
                self.action_authority,
                self.execution_authority,
                self.desktop_effect_performed,
            )
        ):
            raise PhiVesselBridgeError(
                "PhiVessel proposal cannot carry authority or desktop effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "work_id": self.work_id,
            "packet_refs": list(self.packet_refs),
            "proposal_type": self.proposal_type.value,
            "source_id": self.source_id,
            "proposed_at": self.proposed_at,
            "proposal_id": self.proposal_id,
            "authority_request_created": self.authority_request_created,
            "authorization_granted": self.authorization_granted,
            "action_lease_created": self.action_lease_created,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "desktop_effect_performed": self.desktop_effect_performed,
        }

    @property
    def proposal_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["proposal_sha256"] = self.proposal_sha256
        return payload


@dataclass(frozen=True, slots=True)
class PhiVesselBridgeObservation:
    kind: PhiVesselObservationKind
    observed_at: str
    payload: Mapping[str, object]
    source_id: str
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = PHIVESSEL_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PHIVESSEL_OBSERVATION_SCHEMA_VERSION:
            raise PhiVesselBridgeError("unsupported PhiVessel observation schema")
        _require_text(self.observed_at, "observed_at", maximum=64)
        _require_text(self.source_id, "source_id", maximum=256)
        if any(
            (
                self.policy_authority,
                self.operational_authority,
                self.action_authority,
                self.execution_authority,
                self.effect_performed,
            )
        ):
            raise PhiVesselBridgeError(
                "PhiVessel observation cannot carry authority or effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "observed_at": self.observed_at,
            "payload": dict(self.payload),
            "source_id": self.source_id,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["observation_sha256"] = self.observation_sha256
        return payload


class PhiVesselBridgeService:
    """Zero-authority observation/proposal bridge plus lease-only execution."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        ghostwalk_surface: GhostWalkSurfacePort | None = None,
        lease_executor: GhostWalkLeaseExecutionPort | None = None,
        source_id: str = "phivessel:local",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise PhiVesselBridgeError("ledger must be a RealityLedger")
        self._ledger = ledger
        self._surface = ghostwalk_surface
        self._lease_executor = lease_executor
        self.source_id = _require_text(source_id, "source_id", maximum=256)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    @property
    def execution_available(self) -> bool:
        return self._lease_executor is not None

    def observe(
        self,
        *,
        kind: PhiVesselObservationKind,
        action_lease_sha256: str | None = None,
    ) -> PhiVesselBridgeObservation:
        observed_at = _canonical_time(self._now())
        if kind is PhiVesselObservationKind.BRIDGE_STATUS:
            payload: dict[str, object] = {
                "bridge_version": PHIVESSEL_BRIDGE_VERSION,
                "observe_available": True,
                "proposal_available": True,
                "execution_available": self.execution_available,
                "proposal_creates_authority_request": False,
                "proposal_creates_lease": False,
                "execute_accepts_lease_identity_only": True,
            }
        elif kind is PhiVesselObservationKind.GHOSTWALK_CONTROL:
            if self._surface is None:
                raise PhiVesselBridgeUnavailableError(
                    "Ghost-Walk control observation is not mounted"
                )
            snapshot = self._surface.snapshot()
            to_dict = getattr(snapshot, "to_dict", None)
            if not callable(to_dict):
                raise PhiVesselBridgeError(
                    "Ghost-Walk control snapshot is not serializable"
                )
            payload = {"snapshot": to_dict()}
        elif kind is PhiVesselObservationKind.LEASE_STATUS:
            lease_sha = _require_sha256(
                action_lease_sha256,
                "action_lease_sha256",
            )
            payload = self._lease_status(lease_sha)
        else:
            raise PhiVesselBridgeError("unsupported observation kind")
        return PhiVesselBridgeObservation(
            kind=kind,
            observed_at=observed_at,
            payload=payload,
            source_id=self.source_id,
        )

    def propose(
        self,
        *,
        work_id: str,
        packet_refs: tuple[str, ...],
        proposal_type: PhiVesselProposalType,
    ) -> PhiVesselProposalPacket:
        if not _WORK_ID_RE.fullmatch(work_id):
            raise PhiVesselBridgeError("work_id must be a canonical bounded identifier")
        refs = _packet_refs(packet_refs)
        if not isinstance(proposal_type, PhiVesselProposalType):
            raise PhiVesselBridgeError("proposal_type is unsupported")
        proposed_at = _canonical_time(self._now())
        identity_body = {
            "schema_version": PHIVESSEL_PROPOSAL_SCHEMA_VERSION,
            "work_id": work_id,
            "packet_refs": list(refs),
            "proposal_type": proposal_type.value,
            "source_id": self.source_id,
            "proposed_at": proposed_at,
        }
        proposal_id = "pvp:" + _canonical_sha256(identity_body)[:24]
        packet = PhiVesselProposalPacket(
            work_id=work_id,
            packet_refs=refs,
            proposal_type=proposal_type,
            source_id=self.source_id,
            proposed_at=proposed_at,
            proposal_id=proposal_id,
        )
        with self._lock:
            self._ledger.append_phivessel_proposal(packet)
        return packet

    def execute(
        self,
        *,
        action_lease_sha256: str,
    ) -> GhostWalkLeaseExecutionReceipt:
        lease_sha = _require_sha256(
            action_lease_sha256,
            "action_lease_sha256",
        )
        if self._lease_executor is None:
            raise PhiVesselBridgeUnavailableError(
                "Ghost-Walk lease execution is not mounted"
            )
        try:
            return self._lease_executor.execute(
                action_lease_sha256=lease_sha
            )
        except GhostWalkLeaseExecutionError as exc:
            raise PhiVesselBridgeError(str(exc)) from exc

    def _lease_status(self, lease_sha: str) -> dict[str, object]:
        try:
            rows = self._ledger.ghostwalk_action_lease_records(
                action_lease_sha256=lease_sha
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PhiVesselBridgeError(
                "ActionLease custody could not be read safely"
            ) from exc
        if len(rows) > 1:
            raise PhiVesselBridgeError(
                "ActionLease identity is not unique in custody"
            )
        custody: GhostWalkActionLeaseRecord | None = None
        if rows:
            try:
                custody = GhostWalkActionLeaseRecord.from_dict(rows[0])
            except GhostWalkActionLeaseError as exc:
                raise PhiVesselBridgeError(
                    "ActionLease custody is invalid"
                ) from exc
        try:
            consumed = self._ledger.has_consumed_action_lease(lease_sha)
            execution_rows = self._ledger.ghostwalk_lease_execution_receipts(
                action_lease_sha256=lease_sha
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PhiVesselBridgeError(
                "ActionLease execution state could not be read safely"
            ) from exc
        latest: GhostWalkLeaseExecutionReceipt | None = None
        if execution_rows:
            try:
                latest = GhostWalkLeaseExecutionReceipt.from_dict(
                    execution_rows[-1]
                )
            except GhostWalkLeaseExecutionError as exc:
                raise PhiVesselBridgeError(
                    "lease execution receipt is invalid"
                ) from exc
        return {
            "action_lease_sha256": lease_sha,
            "custody_found": custody is not None,
            "lease_consumed": consumed,
            "target_inference_receipt_sha256": (
                None
                if custody is None
                else custody.target_inference_receipt_sha256
            ),
            "executable_binding_sha256": (
                None
                if custody is None
                else custody.executable_binding_sha256
            ),
            "latest_execution": (
                None if latest is None else latest.to_dict()
            ),
        }

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise PhiVesselBridgeError("bridge clock must return datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise PhiVesselBridgeError(
                "bridge clock must return timezone-aware datetime"
            )
        return value.astimezone(UTC)
