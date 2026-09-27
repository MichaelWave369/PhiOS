"""Privacy-bounded Windows UIA state observer for Macro Runtime v0.21.

This module inventories stable UI Automation identities inside one expected
foreground process/window and emits a v0.20 GhostWalkUiStateSnapshot. It never
reads control values and never performs desktop input.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import WindowFrame
from phios.macro_transition_inference import (
    GhostWalkUiStateSnapshot,
    SnapshotPhase,
)
from phios.macro_windows_uia import (
    ComtypesWindowsUiaBackend,
    UiaElementSnapshot,
    WINDOWS_UIA_PROVIDER_ID,
)
from phios.spine.ledger import RealityLedger

UIA_STATE_OBSERVER_RECEIPT_SCHEMA_VERSION = (
    "phios.uia_state_observer_receipt.v0.21"
)
MAX_UIA_INVENTORY_ELEMENTS = 512
MAX_UIA_STATE_TARGETS = 128
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PID_RE = re.compile(r"^pid:([1-9][0-9]*)$")


class UiaStateObserverContractError(ValueError):
    """Raised when semantic state-observation evidence is malformed."""


class UiaInventoryLimitExceeded(RuntimeError):
    """Raised when a complete bounded UIA inventory cannot be obtained."""


class UiaStateObservationStatus(StrEnum):
    CAPTURED = "CAPTURED"
    HELD = "HELD"


class UiaStateObservationReason(StrEnum):
    COMPLETE_INVENTORY = "COMPLETE_INVENTORY"
    FRAME_NOT_FOREGROUND = "FRAME_NOT_FOREGROUND"
    INVENTORY_LIMIT_EXCEEDED = "INVENTORY_LIMIT_EXCEEDED"
    TARGET_LIMIT_EXCEEDED = "TARGET_LIMIT_EXCEEDED"
    BACKEND_ERROR = "BACKEND_ERROR"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise UiaStateObserverContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise UiaStateObserverContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise UiaStateObserverContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise UiaStateObserverContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UiaStateObserverContractError(
            f"{field} must be an integer"
        )
    if value < minimum:
        raise UiaStateObserverContractError(
            f"{field} must be at least {minimum}"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UiaStateObserverContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise UiaStateObserverContractError(
            f"{field} must include a timezone"
        )
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
        raise UiaStateObserverContractError(
            "UIA state-observer payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _semantic_identity_sha256(target: SemanticTarget) -> str:
    return _canonical_sha256(
        {
            "provider": target.provider,
            "selector": target.selector,
            "role": target.role,
        }
    )


def _parse_pid(process_id: str) -> int:
    match = _PID_RE.fullmatch(
        _require_text(process_id, "process_id", maximum=128)
    )
    if match is None:
        raise UiaStateObserverContractError(
            "process_id must use pid:<positive-int>"
        )
    return int(match.group(1))


@dataclass(frozen=True, slots=True)
class UiaInventoryScan:
    """One complete bounded backend scan before semantic filtering."""

    scanned_element_count: int
    snapshots: tuple[UiaElementSnapshot, ...]

    def __post_init__(self) -> None:
        _require_int(
            self.scanned_element_count,
            "scanned_element_count",
        )
        if self.scanned_element_count > MAX_UIA_INVENTORY_ELEMENTS:
            raise UiaStateObserverContractError(
                "inventory scan exceeds safety bound"
            )
        if len(self.snapshots) > self.scanned_element_count:
            raise UiaStateObserverContractError(
                "snapshot count cannot exceed scanned element count"
            )


class UiaStateInventoryBackend(Protocol):
    backend_id: str

    def inventory(
        self,
        *,
        frame: WindowFrame,
    ) -> UiaInventoryScan: ...


@dataclass(frozen=True, slots=True)
class UiaStateObservationReceipt:
    session_id: str
    action_observation_sha256: str
    phase: SnapshotPhase
    frame_sha256: str
    observed_at: str
    backend_id: str
    status: UiaStateObservationStatus
    reason: UiaStateObservationReason
    scanned_element_count: int
    scoped_element_count: int
    semantic_candidate_count: int
    unique_target_count: int
    ambiguous_identity_count: int
    excluded_password_name_count: int
    complete_inventory: bool
    target_sha256s: tuple[str, ...]
    snapshot_sha256: str | None
    snapshot: GhostWalkUiStateSnapshot | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = UIA_STATE_OBSERVER_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != UIA_STATE_OBSERVER_RECEIPT_SCHEMA_VERSION:
            raise UiaStateObserverContractError(
                "unsupported UIA state-observer receipt schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.action_observation_sha256,
            "action_observation_sha256",
        )
        _require_sha256(self.frame_sha256, "frame_sha256")
        _require_timestamp(self.observed_at, "observed_at")
        _require_text(self.backend_id, "backend_id", maximum=256)
        for field, value in (
            ("scanned_element_count", self.scanned_element_count),
            ("scoped_element_count", self.scoped_element_count),
            ("semantic_candidate_count", self.semantic_candidate_count),
            ("unique_target_count", self.unique_target_count),
            ("ambiguous_identity_count", self.ambiguous_identity_count),
            (
                "excluded_password_name_count",
                self.excluded_password_name_count,
            ),
        ):
            _require_int(value, field)
        if self.unique_target_count != len(self.target_sha256s):
            raise UiaStateObserverContractError(
                "unique target count does not match target hashes"
            )
        if self.target_sha256s != tuple(sorted(self.target_sha256s)):
            raise UiaStateObserverContractError(
                "target hashes must be sorted"
            )
        if len(set(self.target_sha256s)) != len(self.target_sha256s):
            raise UiaStateObserverContractError(
                "target hashes must be unique"
            )
        for target_sha in self.target_sha256s:
            _require_sha256(target_sha, "target_sha256")
        if self.status is UiaStateObservationStatus.CAPTURED:
            if (
                not self.complete_inventory
                or self.snapshot is None
                or self.snapshot_sha256 is None
            ):
                raise UiaStateObserverContractError(
                    "CAPTURED receipt requires complete snapshot"
                )
            if self.snapshot.snapshot_sha256 != self.snapshot_sha256:
                raise UiaStateObserverContractError(
                    "state snapshot hash mismatch"
                )
            snapshot_targets = tuple(
                target.target_sha256
                for target in self.snapshot.semantic_targets
            )
            if snapshot_targets != self.target_sha256s:
                raise UiaStateObserverContractError(
                    "receipt targets differ from state snapshot"
                )
        else:
            if (
                self.complete_inventory
                or self.snapshot is not None
                or self.snapshot_sha256 is not None
                or self.target_sha256s
            ):
                raise UiaStateObserverContractError(
                    "HELD receipt cannot claim complete state evidence"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise UiaStateObserverContractError(
                "UiaStateObservationReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "action_observation_sha256": (
                self.action_observation_sha256
            ),
            "phase": self.phase.value,
            "frame_sha256": self.frame_sha256,
            "observed_at": self.observed_at,
            "backend_id": self.backend_id,
            "status": self.status.value,
            "reason": self.reason.value,
            "scanned_element_count": self.scanned_element_count,
            "scoped_element_count": self.scoped_element_count,
            "semantic_candidate_count": self.semantic_candidate_count,
            "unique_target_count": self.unique_target_count,
            "ambiguous_identity_count": self.ambiguous_identity_count,
            "excluded_password_name_count": (
                self.excluded_password_name_count
            ),
            "complete_inventory": self.complete_inventory,
            "target_sha256s": list(self.target_sha256s),
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot": (
                None if self.snapshot is None else self.snapshot.to_dict()
            ),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True, slots=True)
class UiaStateObservationOutcome:
    receipt: UiaStateObservationReceipt
    snapshot: GhostWalkUiStateSnapshot | None


class GhostWalkUiaStateObserver:
    """Build one complete stable-identity UI state snapshot."""

    observer_id = "ghostwalk.windows-uia-state.v0.21"

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        backend: UiaStateInventoryBackend,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise UiaStateObserverContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._backend = backend

    @classmethod
    def from_windows(
        cls,
        *,
        ledger: RealityLedger,
    ) -> "GhostWalkUiaStateObserver":
        return cls(
            ledger=ledger,
            backend=ComtypesWindowsUiaInventoryBackend(),
        )

    def capture(
        self,
        *,
        session_id: str,
        action_observation_sha256: str,
        phase: SnapshotPhase,
        frame: WindowFrame,
        observed_at: str,
    ) -> UiaStateObservationOutcome:
        _require_text(session_id, "session_id", maximum=512)
        _require_sha256(
            action_observation_sha256,
            "action_observation_sha256",
        )
        if not frame.foreground:
            return self._held(
                session_id=session_id,
                action_observation_sha256=action_observation_sha256,
                phase=phase,
                frame=frame,
                observed_at=observed_at,
                reason=UiaStateObservationReason.FRAME_NOT_FOREGROUND,
            )

        try:
            scan = self._backend.inventory(frame=frame)
        except UiaInventoryLimitExceeded:
            return self._held(
                session_id=session_id,
                action_observation_sha256=action_observation_sha256,
                phase=phase,
                frame=frame,
                observed_at=observed_at,
                reason=(
                    UiaStateObservationReason.INVENTORY_LIMIT_EXCEEDED
                ),
            )
        except Exception:
            return self._held(
                session_id=session_id,
                action_observation_sha256=action_observation_sha256,
                phase=phase,
                frame=frame,
                observed_at=observed_at,
                reason=UiaStateObservationReason.BACKEND_ERROR,
            )

        expected_pid = _parse_pid(frame.process_id)
        scoped: list[UiaElementSnapshot] = []
        for element_snapshot in scan.snapshots:
            if element_snapshot.process_id != expected_pid:
                continue
            if element_snapshot.offscreen is True:
                continue
            if (
                element_snapshot.bounding_left is None
                or element_snapshot.bounding_top is None
                or element_snapshot.bounding_right is None
                or element_snapshot.bounding_bottom is None
            ):
                continue
            if not (
                frame.left_px <= element_snapshot.bounding_left
                and frame.top_px <= element_snapshot.bounding_top
                and element_snapshot.bounding_right
                <= frame.left_px + frame.width_px
                and element_snapshot.bounding_bottom
                <= frame.top_px + frame.height_px
            ):
                continue
            scoped.append(element_snapshot)
            self._ledger.append_uia_element_snapshot(element_snapshot)

        candidate_targets: list[SemanticTarget] = []
        excluded_password_names = 0
        for snapshot in scoped:
            if not snapshot.automation_id:
                continue
            if snapshot.is_password is True and snapshot.name_hint is not None:
                excluded_password_names += 1
            selector = _canonical_json(
                {
                    "automation_id": snapshot.automation_id,
                    "control_type": snapshot.control_type,
                }
            )
            candidate_targets.append(
                SemanticTarget(
                    provider=WINDOWS_UIA_PROVIDER_ID,
                    selector=selector,
                    role=(
                        None
                        if snapshot.control_type is None
                        else (
                            "uia.control_type."
                            f"{snapshot.control_type}"
                        )
                    ),
                    name_hint=(
                        None
                        if snapshot.is_password is True
                        else snapshot.name_hint
                    ),
                )
            )

        identity_keys = tuple(
            _semantic_identity_sha256(target)
            for target in candidate_targets
        )
        counts = Counter(identity_keys)
        unique_by_identity = {
            identity_key: target
            for identity_key, target in zip(
                identity_keys,
                candidate_targets,
                strict=True,
            )
            if counts[identity_key] == 1
        }
        ambiguous_identity_count = sum(
            count
            for count in counts.values()
            if count > 1
        )
        unique_targets = tuple(
            unique_by_identity[identity_key]
            for identity_key in sorted(unique_by_identity)
        )
        unique_targets = tuple(
            sorted(
                unique_targets,
                key=lambda target: target.target_sha256,
            )
        )

        if len(unique_targets) > MAX_UIA_STATE_TARGETS:
            return self._held(
                session_id=session_id,
                action_observation_sha256=action_observation_sha256,
                phase=phase,
                frame=frame,
                observed_at=observed_at,
                reason=UiaStateObservationReason.TARGET_LIMIT_EXCEEDED,
                scanned_element_count=scan.scanned_element_count,
                scoped_element_count=len(scoped),
                semantic_candidate_count=len(candidate_targets),
                ambiguous_identity_count=ambiguous_identity_count,
                excluded_password_name_count=excluded_password_names,
            )

        state_snapshot = GhostWalkUiStateSnapshot(
            session_id=session_id,
            action_observation_sha256=action_observation_sha256,
            phase=phase,
            process_id=frame.process_id,
            window_title_sha256=frame.window_title_sha256,
            frame_sha256=frame.frame_sha256,
            semantic_targets=unique_targets,
            observed_at=observed_at,
        )
        receipt = UiaStateObservationReceipt(
            session_id=session_id,
            action_observation_sha256=action_observation_sha256,
            phase=phase,
            frame_sha256=frame.frame_sha256,
            observed_at=observed_at,
            backend_id=self._backend.backend_id,
            status=UiaStateObservationStatus.CAPTURED,
            reason=UiaStateObservationReason.COMPLETE_INVENTORY,
            scanned_element_count=scan.scanned_element_count,
            scoped_element_count=len(scoped),
            semantic_candidate_count=len(candidate_targets),
            unique_target_count=len(unique_targets),
            ambiguous_identity_count=ambiguous_identity_count,
            excluded_password_name_count=excluded_password_names,
            complete_inventory=True,
            target_sha256s=tuple(
                target.target_sha256
                for target in unique_targets
            ),
            snapshot_sha256=state_snapshot.snapshot_sha256,
            snapshot=state_snapshot,
        )
        self._ledger.append_uia_state_observation_receipt(receipt)
        return UiaStateObservationOutcome(
            receipt=receipt,
            snapshot=state_snapshot,
        )

    def _held(
        self,
        *,
        session_id: str,
        action_observation_sha256: str,
        phase: SnapshotPhase,
        frame: WindowFrame,
        observed_at: str,
        reason: UiaStateObservationReason,
        scanned_element_count: int = 0,
        scoped_element_count: int = 0,
        semantic_candidate_count: int = 0,
        ambiguous_identity_count: int = 0,
        excluded_password_name_count: int = 0,
    ) -> UiaStateObservationOutcome:
        receipt = UiaStateObservationReceipt(
            session_id=session_id,
            action_observation_sha256=action_observation_sha256,
            phase=phase,
            frame_sha256=frame.frame_sha256,
            observed_at=_require_timestamp(
                observed_at,
                "observed_at",
            ),
            backend_id=self._backend.backend_id,
            status=UiaStateObservationStatus.HELD,
            reason=reason,
            scanned_element_count=scanned_element_count,
            scoped_element_count=scoped_element_count,
            semantic_candidate_count=semantic_candidate_count,
            unique_target_count=0,
            ambiguous_identity_count=ambiguous_identity_count,
            excluded_password_name_count=excluded_password_name_count,
            complete_inventory=False,
            target_sha256s=(),
            snapshot_sha256=None,
            snapshot=None,
        )
        self._ledger.append_uia_state_observation_receipt(receipt)
        return UiaStateObservationOutcome(
            receipt=receipt,
            snapshot=None,
        )


class ComtypesWindowsUiaInventoryBackend(ComtypesWindowsUiaBackend):
    """Complete bounded process-scoped UIA identity inventory."""

    backend_id = "windows.comtypes.uia-inventory.v0.21"

    def __init__(self) -> None:
        if os.name != "nt":
            raise UiaStateObserverContractError(
                "ComtypesWindowsUiaInventoryBackend requires Windows"
            )
        super().__init__()

    def inventory(
        self,
        *,
        frame: WindowFrame,
    ) -> UiaInventoryScan:
        expected_pid = _parse_pid(frame.process_id)
        process_property_id = self._constant(
            "UIA_ProcessIdPropertyId",
            30002,
        )
        tree_scope_descendants = self._constant(
            "TreeScope_Descendants",
            4,
        )
        process_condition = self._automation.CreatePropertyCondition(
            process_property_id,
            expected_pid,
        )
        root = self._automation.GetRootElement()
        if root is None:
            raise UiaStateObserverContractError(
                "UIA desktop root is unavailable"
            )
        collection = root.FindAll(
            tree_scope_descendants,
            process_condition,
        )
        if collection is None:
            return UiaInventoryScan(
                scanned_element_count=0,
                snapshots=(),
            )

        length = self._coerce_int(
            getattr(
                collection,
                "Length",
                getattr(collection, "length", None),
            ),
            "uia_inventory_length",
        )
        if length is None:
            raise UiaStateObserverContractError(
                "UIA inventory collection has no length"
            )
        if length > MAX_UIA_INVENTORY_ELEMENTS:
            raise UiaInventoryLimitExceeded(
                "UIA process inventory exceeds safety bound"
            )

        get_element = getattr(
            collection,
            "GetElement",
            getattr(collection, "getElement", None),
        )
        if get_element is None:
            raise UiaStateObserverContractError(
                "UIA inventory collection has no GetElement"
            )

        snapshots: list[UiaElementSnapshot] = []
        for index in range(length):
            element = get_element(index)
            if element is None:
                raise UiaStateObserverContractError(
                    "UIA inventory returned an empty element"
                )
            snapshots.append(self.snapshot_from_element(element))

        return UiaInventoryScan(
            scanned_element_count=length,
            snapshots=tuple(snapshots),
        )

    def _constant(
        self,
        name: str,
        fallback: int,
    ) -> int:
        value = getattr(self._uia_module, name, fallback)
        coerced = self._coerce_int(value, name)
        if coerced is None:
            raise UiaStateObserverContractError(
                f"UIA constant unavailable: {name}"
            )
        return coerced
