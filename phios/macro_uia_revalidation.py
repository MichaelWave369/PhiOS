"""Semantic UIA selector replay revalidation for Macro Runtime v0.17.

This layer takes a recorded v0.16 SemanticTarget, scopes it to the expected
process/window, proves that it resolves to exactly one usable UI Automation
element, and returns CLEAR or HOLD evidence. It never injects desktop input and
never grants execution authority.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import WindowFrame
from phios.macro_windows_uia import (
    ComtypesWindowsUiaBackend,
    UiaElementSnapshot,
    WINDOWS_UIA_PROVIDER_ID,
)
from phios.spine.ledger import RealityLedger

SEMANTIC_REVALIDATION_SCHEMA_VERSION = (
    "phios.semantic_revalidation_receipt.v0.17"
)
MAX_UIA_REPLAY_SCAN = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PID_RE = re.compile(r"^pid:([1-9][0-9]*)$")


class SemanticRevalidationContractError(ValueError):
    """Raised when semantic replay evidence cannot be trusted."""


class SemanticRevalidationDecision(StrEnum):
    CLEAR = "CLEAR"
    HOLD = "HOLD"


class SemanticRevalidationReason(StrEnum):
    TARGET_CLEAR = "TARGET_CLEAR"
    PROVIDER_UNSUPPORTED = "PROVIDER_UNSUPPORTED"
    SELECTOR_INVALID = "SELECTOR_INVALID"
    PROCESS_MISMATCH = "PROCESS_MISMATCH"
    WINDOW_MISMATCH = "WINDOW_MISMATCH"
    NOT_FOREGROUND = "NOT_FOREGROUND"
    BACKEND_ERROR = "BACKEND_ERROR"
    TARGET_MISSING = "TARGET_MISSING"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    CANDIDATE_PROCESS_MISMATCH = "CANDIDATE_PROCESS_MISMATCH"
    AUTOMATION_ID_MISMATCH = "AUTOMATION_ID_MISMATCH"
    CONTROL_TYPE_MISMATCH = "CONTROL_TYPE_MISMATCH"
    ENABLED_UNKNOWN = "ENABLED_UNKNOWN"
    DISABLED = "DISABLED"
    OFFSCREEN_UNKNOWN = "OFFSCREEN_UNKNOWN"
    OFFSCREEN = "OFFSCREEN"
    BOUNDS_UNKNOWN = "BOUNDS_UNKNOWN"
    BOUNDS_OUTSIDE_WINDOW = "BOUNDS_OUTSIDE_WINDOW"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise SemanticRevalidationContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise SemanticRevalidationContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise SemanticRevalidationContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise SemanticRevalidationContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticRevalidationContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise SemanticRevalidationContractError(
            f"{field} must be at least {minimum}"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SemanticRevalidationContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise SemanticRevalidationContractError(
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
        raise SemanticRevalidationContractError(
            "semantic replay payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    import hashlib

    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_pid(process_id: str) -> int:
    match = _PID_RE.fullmatch(
        _require_text(process_id, "process_id", maximum=128)
    )
    if match is None:
        raise SemanticRevalidationContractError(
            "process_id must use pid:<positive-int>"
        )
    return int(match.group(1))


@dataclass(frozen=True, slots=True)
class UiaSelectorSpec:
    automation_id: str
    control_type: int | None

    def __post_init__(self) -> None:
        _require_text(
            self.automation_id,
            "automation_id",
            maximum=2048,
        )
        if self.control_type is not None:
            _require_int(
                self.control_type,
                "control_type",
                minimum=0,
            )

    @classmethod
    def from_target(
        cls,
        target: SemanticTarget,
    ) -> "UiaSelectorSpec":
        if target.provider != WINDOWS_UIA_PROVIDER_ID:
            raise SemanticRevalidationContractError(
                "semantic target provider is unsupported"
            )
        try:
            payload = json.loads(target.selector)
        except json.JSONDecodeError as exc:
            raise SemanticRevalidationContractError(
                "semantic target selector is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise SemanticRevalidationContractError(
                "semantic target selector must be an object"
            )
        if set(payload) != {"automation_id", "control_type"}:
            raise SemanticRevalidationContractError(
                "semantic target selector has unsupported fields"
            )
        automation_id = payload.get("automation_id")
        control_type = payload.get("control_type")
        if not isinstance(automation_id, str) or not automation_id:
            raise SemanticRevalidationContractError(
                "semantic selector automation_id is invalid"
            )
        if control_type is not None:
            if isinstance(control_type, bool) or not isinstance(
                control_type,
                int,
            ):
                raise SemanticRevalidationContractError(
                    "semantic selector control_type is invalid"
                )
            if control_type < 0:
                raise SemanticRevalidationContractError(
                    "semantic selector control_type must be non-negative"
                )
        return cls(
            automation_id=automation_id,
            control_type=control_type,
        )


class UiaReplayBackend(Protocol):
    """Read-only backend that returns candidates for one scoped selector."""

    backend_id: str

    def find_matches(
        self,
        *,
        frame: WindowFrame,
        selector: UiaSelectorSpec,
    ) -> tuple[UiaElementSnapshot, ...]: ...


@dataclass(frozen=True, slots=True)
class SemanticRevalidationReceipt:
    target_sha256: str
    frame_sha256: str
    expected_process_id: str
    expected_window_title_sha256: str
    backend_id: str
    decision: SemanticRevalidationDecision
    reason: SemanticRevalidationReason
    match_count: int
    candidate_snapshot_sha256s: tuple[str, ...]
    selected_snapshot_sha256: str | None
    resolved_x_px: int | None
    resolved_y_px: int | None
    observed_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SEMANTIC_REVALIDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_REVALIDATION_SCHEMA_VERSION:
            raise SemanticRevalidationContractError(
                "unsupported semantic revalidation receipt schema"
            )
        _require_sha256(self.target_sha256, "target_sha256")
        _require_sha256(self.frame_sha256, "frame_sha256")
        _parse_pid(self.expected_process_id)
        _require_sha256(
            self.expected_window_title_sha256,
            "expected_window_title_sha256",
        )
        _require_text(self.backend_id, "backend_id", maximum=256)
        _require_int(self.match_count, "match_count", minimum=0)
        if self.match_count != len(self.candidate_snapshot_sha256s):
            raise SemanticRevalidationContractError(
                "match_count must equal candidate snapshot hash count"
            )
        for item in self.candidate_snapshot_sha256s:
            _require_sha256(item, "candidate_snapshot_sha256")
        if self.selected_snapshot_sha256 is not None:
            _require_sha256(
                self.selected_snapshot_sha256,
                "selected_snapshot_sha256",
            )
            if (
                self.selected_snapshot_sha256
                not in self.candidate_snapshot_sha256s
            ):
                raise SemanticRevalidationContractError(
                    "selected snapshot must be one of the candidates"
                )
        _require_timestamp(self.observed_at, "observed_at")
        if self.decision is SemanticRevalidationDecision.CLEAR:
            if self.reason is not SemanticRevalidationReason.TARGET_CLEAR:
                raise SemanticRevalidationContractError(
                    "CLEAR semantic receipt requires TARGET_CLEAR"
                )
            if (
                self.match_count != 1
                or self.selected_snapshot_sha256 is None
                or self.resolved_x_px is None
                or self.resolved_y_px is None
            ):
                raise SemanticRevalidationContractError(
                    "CLEAR semantic receipt requires one selected candidate and coordinates"
                )
        else:
            if (
                self.selected_snapshot_sha256 is not None
                or self.resolved_x_px is not None
                or self.resolved_y_px is not None
            ):
                raise SemanticRevalidationContractError(
                    "HOLD semantic receipt cannot claim selected coordinates"
                )
        if (
            self.resolved_x_px is not None
            and isinstance(self.resolved_x_px, bool)
        ):
            raise SemanticRevalidationContractError(
                "resolved_x_px must be an integer"
            )
        if (
            self.resolved_y_px is not None
            and isinstance(self.resolved_y_px, bool)
        ):
            raise SemanticRevalidationContractError(
                "resolved_y_px must be an integer"
            )
        if self.resolved_x_px is not None:
            _require_int(self.resolved_x_px, "resolved_x_px")
        if self.resolved_y_px is not None:
            _require_int(self.resolved_y_px, "resolved_y_px")
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise SemanticRevalidationContractError(
                "SemanticRevalidationReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_sha256": self.target_sha256,
            "frame_sha256": self.frame_sha256,
            "expected_process_id": self.expected_process_id,
            "expected_window_title_sha256": (
                self.expected_window_title_sha256
            ),
            "backend_id": self.backend_id,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "match_count": self.match_count,
            "candidate_snapshot_sha256s": list(
                self.candidate_snapshot_sha256s
            ),
            "selected_snapshot_sha256": self.selected_snapshot_sha256,
            "resolved_x_px": self.resolved_x_px,
            "resolved_y_px": self.resolved_y_px,
            "observed_at": self.observed_at,
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


class SemanticReplayRevalidator:
    """Fail-closed semantic selector replay gate."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        backend: UiaReplayBackend,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise SemanticRevalidationContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._backend = backend

    @classmethod
    def from_system(
        cls,
        *,
        ledger: RealityLedger,
    ) -> "SemanticReplayRevalidator":
        return cls(
            ledger=ledger,
            backend=ComtypesWindowsUiaReplayBackend(),
        )

    def assess(
        self,
        *,
        target: SemanticTarget,
        expected_process_id: str,
        expected_window_title_sha256: str,
        frame: WindowFrame,
        observed_at: str,
    ) -> SemanticRevalidationReceipt:
        observed_at = _require_timestamp(observed_at, "observed_at")
        _parse_pid(expected_process_id)
        _require_sha256(
            expected_window_title_sha256,
            "expected_window_title_sha256",
        )

        if frame.process_id != expected_process_id:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=SemanticRevalidationReason.PROCESS_MISMATCH,
                observed_at=observed_at,
            )
        if frame.window_title_sha256 != expected_window_title_sha256:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=SemanticRevalidationReason.WINDOW_MISMATCH,
                observed_at=observed_at,
            )
        if not frame.foreground:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=SemanticRevalidationReason.NOT_FOREGROUND,
                observed_at=observed_at,
            )

        try:
            selector = UiaSelectorSpec.from_target(target)
        except SemanticRevalidationContractError as exc:
            reason = (
                SemanticRevalidationReason.PROVIDER_UNSUPPORTED
                if "provider is unsupported" in str(exc)
                else SemanticRevalidationReason.SELECTOR_INVALID
            )
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=reason,
                observed_at=observed_at,
            )

        try:
            candidates = self._backend.find_matches(
                frame=frame,
                selector=selector,
            )
        except Exception:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=SemanticRevalidationReason.BACKEND_ERROR,
                observed_at=observed_at,
            )

        for candidate in candidates:
            self._ledger.append_uia_element_snapshot(candidate)

        if not candidates:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=SemanticRevalidationReason.TARGET_MISSING,
                observed_at=observed_at,
            )
        if len(candidates) != 1:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=SemanticRevalidationReason.TARGET_AMBIGUOUS,
                observed_at=observed_at,
                candidates=candidates,
            )

        candidate = candidates[0]
        hold_reason = self._candidate_hold_reason(
            candidate=candidate,
            selector=selector,
            frame=frame,
            expected_process_id=expected_process_id,
        )
        if hold_reason is not None:
            return self._hold(
                target=target,
                frame=frame,
                expected_process_id=expected_process_id,
                expected_window_title_sha256=(
                    expected_window_title_sha256
                ),
                reason=hold_reason,
                observed_at=observed_at,
                candidates=candidates,
            )

        assert candidate.bounding_left is not None
        assert candidate.bounding_top is not None
        assert candidate.bounding_right is not None
        assert candidate.bounding_bottom is not None
        resolved_x = (
            candidate.bounding_left + candidate.bounding_right
        ) // 2
        resolved_y = (
            candidate.bounding_top + candidate.bounding_bottom
        ) // 2
        receipt = SemanticRevalidationReceipt(
            target_sha256=target.target_sha256,
            frame_sha256=frame.frame_sha256,
            expected_process_id=expected_process_id,
            expected_window_title_sha256=(
                expected_window_title_sha256
            ),
            backend_id=self._backend.backend_id,
            decision=SemanticRevalidationDecision.CLEAR,
            reason=SemanticRevalidationReason.TARGET_CLEAR,
            match_count=1,
            candidate_snapshot_sha256s=(
                candidate.snapshot_sha256,
            ),
            selected_snapshot_sha256=candidate.snapshot_sha256,
            resolved_x_px=resolved_x,
            resolved_y_px=resolved_y,
            observed_at=observed_at,
        )
        self._ledger.append_semantic_revalidation_receipt(receipt)
        return receipt

    def _candidate_hold_reason(
        self,
        *,
        candidate: UiaElementSnapshot,
        selector: UiaSelectorSpec,
        frame: WindowFrame,
        expected_process_id: str,
    ) -> SemanticRevalidationReason | None:
        expected_pid = _parse_pid(expected_process_id)
        if candidate.process_id != expected_pid:
            return SemanticRevalidationReason.CANDIDATE_PROCESS_MISMATCH
        if candidate.automation_id != selector.automation_id:
            return SemanticRevalidationReason.AUTOMATION_ID_MISMATCH
        if (
            selector.control_type is not None
            and candidate.control_type != selector.control_type
        ):
            return SemanticRevalidationReason.CONTROL_TYPE_MISMATCH
        if candidate.enabled is None:
            return SemanticRevalidationReason.ENABLED_UNKNOWN
        if candidate.enabled is False:
            return SemanticRevalidationReason.DISABLED
        if candidate.offscreen is None:
            return SemanticRevalidationReason.OFFSCREEN_UNKNOWN
        if candidate.offscreen is True:
            return SemanticRevalidationReason.OFFSCREEN

        bounds = (
            candidate.bounding_left,
            candidate.bounding_top,
            candidate.bounding_right,
            candidate.bounding_bottom,
        )
        if any(value is None for value in bounds):
            return SemanticRevalidationReason.BOUNDS_UNKNOWN

        assert candidate.bounding_left is not None
        assert candidate.bounding_top is not None
        assert candidate.bounding_right is not None
        assert candidate.bounding_bottom is not None
        if not (
            frame.left_px <= candidate.bounding_left
            and frame.top_px <= candidate.bounding_top
            and candidate.bounding_right
            <= frame.left_px + frame.width_px
            and candidate.bounding_bottom
            <= frame.top_px + frame.height_px
        ):
            return SemanticRevalidationReason.BOUNDS_OUTSIDE_WINDOW
        return None

    def _hold(
        self,
        *,
        target: SemanticTarget,
        frame: WindowFrame,
        expected_process_id: str,
        expected_window_title_sha256: str,
        reason: SemanticRevalidationReason,
        observed_at: str,
        candidates: tuple[UiaElementSnapshot, ...] = (),
    ) -> SemanticRevalidationReceipt:
        receipt = SemanticRevalidationReceipt(
            target_sha256=target.target_sha256,
            frame_sha256=frame.frame_sha256,
            expected_process_id=expected_process_id,
            expected_window_title_sha256=(
                expected_window_title_sha256
            ),
            backend_id=self._backend.backend_id,
            decision=SemanticRevalidationDecision.HOLD,
            reason=reason,
            match_count=len(candidates),
            candidate_snapshot_sha256s=tuple(
                candidate.snapshot_sha256
                for candidate in candidates
            ),
            selected_snapshot_sha256=None,
            resolved_x_px=None,
            resolved_y_px=None,
            observed_at=observed_at,
        )
        self._ledger.append_semantic_revalidation_receipt(receipt)
        return receipt


class ComtypesWindowsUiaReplayBackend(ComtypesWindowsUiaBackend):
    """Read-only UIA replay lookup scoped by process and current window bounds."""

    backend_id = "windows.comtypes.uia-replay.v0.17"

    def __init__(self) -> None:
        if os.name != "nt":
            raise SemanticRevalidationContractError(
                "ComtypesWindowsUiaReplayBackend requires Windows"
            )
        super().__init__()

    def find_matches(
        self,
        *,
        frame: WindowFrame,
        selector: UiaSelectorSpec,
    ) -> tuple[UiaElementSnapshot, ...]:
        expected_pid = _parse_pid(frame.process_id)
        automation_property_id = int(
            getattr(
                self._uia_module,
                "UIA_AutomationIdPropertyId",
                30011,
            )
        )
        control_type_property_id = int(
            getattr(
                self._uia_module,
                "UIA_ControlTypePropertyId",
                30003,
            )
        )
        tree_scope_descendants = int(
            getattr(
                self._uia_module,
                "TreeScope_Descendants",
                4,
            )
        )

        automation_condition = self._automation.CreatePropertyCondition(
            automation_property_id,
            selector.automation_id,
        )
        condition = automation_condition
        if selector.control_type is not None:
            control_condition = self._automation.CreatePropertyCondition(
                control_type_property_id,
                selector.control_type,
            )
            condition = self._automation.CreateAndCondition(
                automation_condition,
                control_condition,
            )

        root = self._automation.GetRootElement()
        if root is None:
            return ()
        collection = root.FindAll(
            tree_scope_descendants,
            condition,
        )
        if collection is None:
            return ()

        length = self._coerce_int(
            getattr(
                collection,
                "Length",
                getattr(collection, "length", None),
            ),
            "uia_match_count",
        )
        if length is None:
            raise SemanticRevalidationContractError(
                "UIA replay match collection has no length"
            )
        if length > MAX_UIA_REPLAY_SCAN:
            raise SemanticRevalidationContractError(
                "UIA replay match scan exceeds safety bound"
            )

        matches: list[UiaElementSnapshot] = []
        get_element = getattr(
            collection,
            "GetElement",
            getattr(collection, "getElement", None),
        )
        if get_element is None:
            raise SemanticRevalidationContractError(
                "UIA replay match collection has no GetElement"
            )

        for index in range(length):
            element = get_element(index)
            if element is None:
                continue
            snapshot = self.snapshot_from_element(element)
            if snapshot.process_id != expected_pid:
                continue
            if (
                snapshot.bounding_left is not None
                and snapshot.bounding_top is not None
                and snapshot.bounding_right is not None
                and snapshot.bounding_bottom is not None
                and (
                    snapshot.bounding_right <= frame.left_px
                    or snapshot.bounding_bottom <= frame.top_px
                    or snapshot.bounding_left
                    >= frame.left_px + frame.width_px
                    or snapshot.bounding_top
                    >= frame.top_px + frame.height_px
                )
            ):
                continue
            matches.append(snapshot)
            if len(matches) >= 2:
                break

        return tuple(matches)
