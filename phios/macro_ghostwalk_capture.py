"""Observation-only Ghost-Walk capture adapter for Macro Runtime v0.14.

This layer accepts one host-observed pointer click, resolves the OS window
context, optionally enriches it with a semantic UI target, and feeds the exact
v0.13 GhostWalkRecorder contract. It never injects desktop input.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from phios.macro_ghostwalk import (
    GhostWalkObservation,
    GhostWalkRecorder,
    SemanticTarget,
)
from phios.macro_interaction_guard import WindowFrame
from phios.spine.ledger import RealityLedger

GHOSTWALK_CLICK_EVENT_SCHEMA_VERSION = "phios.ghostwalk_click_event.v0.14"
GHOSTWALK_CAPTURE_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_capture_receipt.v0.14"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkCaptureContractError(ValueError):
    """Raised when a captured desktop observation cannot be trusted."""


class PointerButton(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    MIDDLE = "MIDDLE"


class CaptureStatus(StrEnum):
    RECORDED = "RECORDED"
    HELD = "HELD"


class CaptureReason(StrEnum):
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"
    INJECTED_EVENT = "INJECTED_EVENT"
    UNSUPPORTED_BUTTON = "UNSUPPORTED_BUTTON"
    WINDOW_UNAVAILABLE = "WINDOW_UNAVAILABLE"
    CLICK_OUTSIDE_WINDOW = "CLICK_OUTSIDE_WINDOW"
    SEMANTIC_LOOKUP_ERROR = "SEMANTIC_LOOKUP_ERROR"


class SemanticLookupStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkCaptureContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkCaptureContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkCaptureContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkCaptureContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GhostWalkCaptureContractError(
            f"{field} must be an integer"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkCaptureContractError(
            f"{field} must be Boolean"
        )
    return value


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
        raise GhostWalkCaptureContractError(
            "ghost-walk capture payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PointerClickEvent:
    """One host-observed pointer click. Observation only."""

    event_id: str
    x_px: int
    y_px: int
    button: PointerButton
    observed_at: str
    injected: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_CLICK_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_CLICK_EVENT_SCHEMA_VERSION:
            raise GhostWalkCaptureContractError(
                "unsupported pointer click event schema"
            )
        _require_text(self.event_id, "event_id", maximum=512)
        _require_int(self.x_px, "x_px")
        _require_int(self.y_px, "y_px")
        if not isinstance(self.button, PointerButton):
            raise GhostWalkCaptureContractError(
                "button must be a PointerButton"
            )
        if not isinstance(self.injected, bool):
            raise GhostWalkCaptureContractError(
                "injected must be Boolean"
            )
        _require_text(self.observed_at, "observed_at", maximum=64)
        try:
            parsed = datetime.fromisoformat(
                self.observed_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise GhostWalkCaptureContractError(
                "observed_at must be an ISO-8601 timestamp"
            ) from exc
        if parsed.tzinfo is None:
            raise GhostWalkCaptureContractError(
                "observed_at must include a timezone"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkCaptureContractError(
                "PointerClickEvent cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "x_px": self.x_px,
            "y_px": self.y_px,
            "button": self.button.value,
            "observed_at": self.observed_at,
            "injected": self.injected,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def event_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["event_sha256"] = self.event_sha256
        return payload


class WindowFrameProvider(Protocol):
    """Read-only provider for the window under one observed desktop point."""

    provider_id: str

    def frame_for_click(
        self,
        event: PointerClickEvent,
    ) -> WindowFrame | None: ...


class SemanticTargetProvider(Protocol):
    """Optional read-only semantic lookup provider."""

    provider_id: str

    def target_for_click(
        self,
        *,
        event: PointerClickEvent,
        frame: WindowFrame,
    ) -> SemanticTarget | None: ...


@dataclass(frozen=True, slots=True)
class GhostWalkCaptureReceipt:
    session_id: str
    event_id: str
    event_sha256: str
    window_provider_id: str
    semantic_provider_id: str | None
    semantic_lookup_status: SemanticLookupStatus
    status: CaptureStatus
    reason: CaptureReason
    frame_sha256: str | None
    semantic_target_sha256: str | None
    observation_sha256: str | None
    preferred_strategy: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_CAPTURE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_CAPTURE_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkCaptureContractError(
                "unsupported ghost-walk capture receipt schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_text(self.event_id, "event_id", maximum=512)
        _require_sha256(self.event_sha256, "event_sha256")
        _require_text(
            self.window_provider_id,
            "window_provider_id",
            maximum=256,
        )
        if self.semantic_provider_id is not None:
            _require_text(
                self.semantic_provider_id,
                "semantic_provider_id",
                maximum=256,
            )
        for field, value in (
            ("frame_sha256", self.frame_sha256),
            ("semantic_target_sha256", self.semantic_target_sha256),
            ("observation_sha256", self.observation_sha256),
        ):
            if value is not None:
                _require_sha256(value, field)
        if self.preferred_strategy is not None:
            _require_text(
                self.preferred_strategy,
                "preferred_strategy",
                maximum=64,
            )
        if self.semantic_lookup_status is SemanticLookupStatus.FOUND:
            if (
                self.semantic_provider_id is None
                or self.semantic_target_sha256 is None
            ):
                raise GhostWalkCaptureContractError(
                    "FOUND semantic lookup requires provider and target hash"
                )
        elif self.semantic_target_sha256 is not None:
            raise GhostWalkCaptureContractError(
                "non-FOUND semantic lookup cannot claim target hash"
            )
        if (
            self.semantic_lookup_status
            is SemanticLookupStatus.NOT_CONFIGURED
            and self.semantic_provider_id is not None
        ):
            raise GhostWalkCaptureContractError(
                "NOT_CONFIGURED semantic lookup cannot name a provider"
            )
        if self.status is CaptureStatus.RECORDED:
            if (
                self.frame_sha256 is None
                or self.observation_sha256 is None
                or self.preferred_strategy is None
            ):
                raise GhostWalkCaptureContractError(
                    "RECORDED receipt requires frame, observation, and strategy"
                )
        else:
            if (
                self.observation_sha256 is not None
                or self.preferred_strategy is not None
            ):
                raise GhostWalkCaptureContractError(
                    "HELD receipt cannot claim observation or strategy"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkCaptureContractError(
                "GhostWalkCaptureReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "event_id": self.event_id,
            "event_sha256": self.event_sha256,
            "window_provider_id": self.window_provider_id,
            "semantic_provider_id": self.semantic_provider_id,
            "semantic_lookup_status": self.semantic_lookup_status.value,
            "status": self.status.value,
            "reason": self.reason.value,
            "frame_sha256": self.frame_sha256,
            "semantic_target_sha256": self.semantic_target_sha256,
            "observation_sha256": self.observation_sha256,
            "preferred_strategy": self.preferred_strategy,
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
class GhostWalkCaptureOutcome:
    receipt: GhostWalkCaptureReceipt
    observation: GhostWalkObservation | None


class GhostWalkCaptureAdapter:
    """Translate one observed host click into a v0.13 recorder observation."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        window_provider: WindowFrameProvider,
        semantic_provider: SemanticTargetProvider | None = None,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkCaptureContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._recorder = GhostWalkRecorder(ledger)
        self._window_provider = window_provider
        self._semantic_provider = semantic_provider

    def capture_click(
        self,
        *,
        session_id: str,
        event: PointerClickEvent,
    ) -> GhostWalkCaptureOutcome:
        self._recorder.observations(session_id=session_id)
        if event.injected:
            return self._held(
                session_id=session_id,
                event=event,
                reason=CaptureReason.INJECTED_EVENT,
                semantic_status=SemanticLookupStatus.NOT_CONFIGURED,
            )
        if event.button is not PointerButton.LEFT:
            return self._held(
                session_id=session_id,
                event=event,
                reason=CaptureReason.UNSUPPORTED_BUTTON,
                semantic_status=SemanticLookupStatus.NOT_CONFIGURED,
            )

        frame = self._window_provider.frame_for_click(event)
        if frame is None:
            return self._held(
                session_id=session_id,
                event=event,
                reason=CaptureReason.WINDOW_UNAVAILABLE,
                semantic_status=SemanticLookupStatus.NOT_CONFIGURED,
            )
        if not (
            frame.left_px <= event.x_px < frame.left_px + frame.width_px
            and frame.top_px <= event.y_px < frame.top_px + frame.height_px
        ):
            return self._held(
                session_id=session_id,
                event=event,
                reason=CaptureReason.CLICK_OUTSIDE_WINDOW,
                semantic_status=SemanticLookupStatus.NOT_CONFIGURED,
                frame=frame,
            )

        semantic: SemanticTarget | None = None
        semantic_status = SemanticLookupStatus.NOT_CONFIGURED
        semantic_provider = self._semantic_provider
        if semantic_provider is not None:
            try:
                semantic = semantic_provider.target_for_click(
                    event=event,
                    frame=frame,
                )
            except Exception:
                semantic_status = SemanticLookupStatus.ERROR
            else:
                semantic_status = (
                    SemanticLookupStatus.FOUND
                    if semantic is not None
                    else SemanticLookupStatus.NOT_FOUND
                )

        observation = self._recorder.record_click(
            session_id=session_id,
            frame=frame,
            x_px=event.x_px,
            y_px=event.y_px,
            observed_at=event.observed_at,
            semantic_target=semantic,
            semantic_hint=(
                None if semantic is None else semantic.name_hint
            ),
        )
        reason = (
            CaptureReason.SEMANTIC_LOOKUP_ERROR
            if semantic_status is SemanticLookupStatus.ERROR
            else CaptureReason.OBSERVATION_RECORDED
        )
        receipt = GhostWalkCaptureReceipt(
            session_id=session_id,
            event_id=event.event_id,
            event_sha256=event.event_sha256,
            window_provider_id=self._window_provider.provider_id,
            semantic_provider_id=(
                None
                if semantic_provider is None
                else semantic_provider.provider_id
            ),
            semantic_lookup_status=semantic_status,
            status=CaptureStatus.RECORDED,
            reason=reason,
            frame_sha256=frame.frame_sha256,
            semantic_target_sha256=(
                None if semantic is None else semantic.target_sha256
            ),
            observation_sha256=observation.observation_sha256,
            preferred_strategy=observation.preferred_strategy.value,
        )
        self._ledger.append_ghostwalk_capture_receipt(receipt)
        return GhostWalkCaptureOutcome(
            receipt=receipt,
            observation=observation,
        )

    def _held(
        self,
        *,
        session_id: str,
        event: PointerClickEvent,
        reason: CaptureReason,
        semantic_status: SemanticLookupStatus,
        frame: WindowFrame | None = None,
    ) -> GhostWalkCaptureOutcome:
        receipt = GhostWalkCaptureReceipt(
            session_id=session_id,
            event_id=event.event_id,
            event_sha256=event.event_sha256,
            window_provider_id=self._window_provider.provider_id,
            semantic_provider_id=(
                None
                if self._semantic_provider is None
                else self._semantic_provider.provider_id
            ),
            semantic_lookup_status=semantic_status,
            status=CaptureStatus.HELD,
            reason=reason,
            frame_sha256=(
                None if frame is None else frame.frame_sha256
            ),
            semantic_target_sha256=None,
            observation_sha256=None,
            preferred_strategy=None,
        )
        self._ledger.append_ghostwalk_capture_receipt(receipt)
        return GhostWalkCaptureOutcome(
            receipt=receipt,
            observation=None,
        )


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int32),
        ("y", ctypes.c_int32),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_int32),
        ("top", ctypes.c_int32),
        ("right", ctypes.c_int32),
        ("bottom", ctypes.c_int32),
    ]


class WindowsWindowFrameProvider:
    """Read the root window under an observed click using the Windows API."""

    provider_id = "windows.user32.window-under-point.v0.14"

    def __init__(self) -> None:
        if os.name != "nt":
            raise GhostWalkCaptureContractError(
                "WindowsWindowFrameProvider requires Windows"
            )

    def frame_for_click(
        self,
        event: PointerClickEvent,
    ) -> WindowFrame | None:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise GhostWalkCaptureContractError(
                "ctypes Windows API loader is unavailable"
            )
        user32 = windll.user32

        window_from_point = user32.WindowFromPoint
        window_from_point.argtypes = [_POINT]
        window_from_point.restype = ctypes.c_void_p

        get_ancestor = user32.GetAncestor
        get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        get_ancestor.restype = ctypes.c_void_p

        get_window_rect = user32.GetWindowRect
        get_window_rect.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_RECT),
        ]
        get_window_rect.restype = ctypes.c_int

        get_window_thread_process_id = user32.GetWindowThreadProcessId
        get_window_thread_process_id.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        get_window_thread_process_id.restype = ctypes.c_uint32

        get_window_text_length = user32.GetWindowTextLengthW
        get_window_text_length.argtypes = [ctypes.c_void_p]
        get_window_text_length.restype = ctypes.c_int

        get_window_text = user32.GetWindowTextW
        get_window_text.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        get_window_text.restype = ctypes.c_int

        get_foreground_window = user32.GetForegroundWindow
        get_foreground_window.argtypes = []
        get_foreground_window.restype = ctypes.c_void_p

        clicked = window_from_point(_POINT(event.x_px, event.y_px))
        if not clicked:
            return None

        ga_root = 2
        root = get_ancestor(clicked, ga_root) or clicked

        rect = _RECT()
        if not get_window_rect(root, ctypes.byref(rect)):
            return None
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return None

        process_id = ctypes.c_uint32()
        get_window_thread_process_id(root, ctypes.byref(process_id))
        if process_id.value == 0:
            return None

        title_length = max(get_window_text_length(root), 0)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        get_window_text(root, title_buffer, title_length + 1)
        title_sha256 = hashlib.sha256(
            title_buffer.value.encode("utf-8")
        ).hexdigest()

        dpi = 96
        get_dpi_for_window = getattr(user32, "GetDpiForWindow", None)
        if get_dpi_for_window is not None:
            get_dpi_for_window.argtypes = [ctypes.c_void_p]
            get_dpi_for_window.restype = ctypes.c_uint
            observed_dpi = int(get_dpi_for_window(root))
            if observed_dpi > 0:
                dpi = observed_dpi
        scale = max(50, min(500, round(dpi * 100 / 96)))

        foreground = get_foreground_window()
        foreground_root = (
            get_ancestor(foreground, ga_root)
            if foreground
            else None
        )
        is_foreground = root == (foreground_root or foreground)

        return WindowFrame(
            process_id=f"pid:{process_id.value}",
            window_title_sha256=title_sha256,
            left_px=int(rect.left),
            top_px=int(rect.top),
            width_px=width,
            height_px=height,
            display_scale_percent=scale,
            foreground=is_foreground,
            captured_at=event.observed_at,
        )
