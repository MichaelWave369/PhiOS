"""Windows Ghost-Walk listener for Macro Runtime v0.15.

This module observes low-level Windows mouse events and feeds genuine left-click
observations into the merged v0.14 GhostWalkCaptureAdapter. It never injects
desktop input.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import queue
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Mapping

from phios.macro_ghostwalk_capture import (
    CaptureStatus,
    GhostWalkCaptureAdapter,
    GhostWalkCaptureOutcome,
    PointerButton,
    PointerClickEvent,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_RAW_MOUSE_SCHEMA_VERSION = "phios.ghostwalk_raw_mouse.v0.15"
GHOSTWALK_LISTENER_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_listener_receipt.v0.15"
)

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_QUIT = 0x0012
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002
MAX_PENDING_HOOK_EVENTS = 1024
WORKER_SHUTDOWN_SECONDS = 10.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkListenerContractError(ValueError):
    """Raised when listener observation provenance cannot be trusted."""


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkListenerContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkListenerContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkListenerContractError(
            f"{field} contains control characters"
        )
    return value


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GhostWalkListenerContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise GhostWalkListenerContractError(
            f"{field} must be at least {minimum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkListenerContractError(
            f"{field} must be Boolean"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkListenerContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkListenerContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkListenerContractError(
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
        raise GhostWalkListenerContractError(
            "ghost-walk listener payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class RawMouseHookEvent:
    """Read-only fields observed from Windows MSLLHOOKSTRUCT."""

    x_px: int
    y_px: int
    flags: int
    hook_time_ms: int
    extra_info: int
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_RAW_MOUSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_RAW_MOUSE_SCHEMA_VERSION:
            raise GhostWalkListenerContractError(
                "unsupported raw mouse hook schema"
            )
        _require_int(self.x_px, "x_px")
        _require_int(self.y_px, "y_px")
        _require_int(self.flags, "flags", minimum=0)
        _require_int(self.hook_time_ms, "hook_time_ms", minimum=0)
        _require_int(self.extra_info, "extra_info", minimum=0)
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkListenerContractError(
                "RawMouseHookEvent cannot carry authority"
            )

    @property
    def injected(self) -> bool:
        return bool(
            self.flags
            & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED)
        )

    @property
    def lower_integrity_injected(self) -> bool:
        return bool(self.flags & LLMHF_LOWER_IL_INJECTED)

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "x_px": self.x_px,
            "y_px": self.y_px,
            "flags": self.flags,
            "hook_time_ms": self.hook_time_ms,
            "extra_info": self.extra_info,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def raw_event_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["raw_event_sha256"] = self.raw_event_sha256
        payload["injected"] = self.injected
        payload["lower_integrity_injected"] = (
            self.lower_integrity_injected
        )
        return payload


@dataclass(frozen=True, slots=True)
class GhostWalkListenerReceipt:
    listener_id: str
    listener_sequence: int
    session_id: str
    raw_event_sha256: str
    pointer_event_sha256: str
    capture_receipt_sha256: str
    capture_status: CaptureStatus
    injected: bool
    lower_integrity_injected: bool
    observed_at: str
    previous_listener_receipt_sha256: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_LISTENER_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_LISTENER_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkListenerContractError(
                "unsupported listener receipt schema"
            )
        _require_text(self.listener_id, "listener_id", maximum=512)
        _require_int(
            self.listener_sequence,
            "listener_sequence",
            minimum=0,
        )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(self.raw_event_sha256, "raw_event_sha256")
        _require_sha256(
            self.pointer_event_sha256,
            "pointer_event_sha256",
        )
        _require_sha256(
            self.capture_receipt_sha256,
            "capture_receipt_sha256",
        )
        _require_timestamp(self.observed_at, "observed_at")
        _require_bool(self.injected, "injected")
        _require_bool(
            self.lower_integrity_injected,
            "lower_integrity_injected",
        )
        if self.listener_sequence == 0:
            if self.previous_listener_receipt_sha256 is not None:
                raise GhostWalkListenerContractError(
                    "first listener receipt cannot reference prior history"
                )
        else:
            if self.previous_listener_receipt_sha256 is None:
                raise GhostWalkListenerContractError(
                    "later listener receipt requires prior receipt hash"
                )
            _require_sha256(
                self.previous_listener_receipt_sha256,
                "previous_listener_receipt_sha256",
            )
        if self.lower_integrity_injected and not self.injected:
            raise GhostWalkListenerContractError(
                "lower-integrity injection must also be injected"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkListenerContractError(
                "GhostWalkListenerReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "listener_id": self.listener_id,
            "listener_sequence": self.listener_sequence,
            "session_id": self.session_id,
            "raw_event_sha256": self.raw_event_sha256,
            "pointer_event_sha256": self.pointer_event_sha256,
            "capture_receipt_sha256": self.capture_receipt_sha256,
            "capture_status": self.capture_status.value,
            "injected": self.injected,
            "lower_integrity_injected": self.lower_integrity_injected,
            "observed_at": self.observed_at,
            "previous_listener_receipt_sha256": (
                self.previous_listener_receipt_sha256
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

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkListenerReceipt":
        claimed = _require_sha256(
            payload.get("receipt_sha256"),
            "receipt_sha256",
        )
        sequence_raw = payload.get("listener_sequence")
        if isinstance(sequence_raw, bool) or not isinstance(
            sequence_raw,
            int,
        ):
            raise GhostWalkListenerContractError(
                "listener_sequence must be an integer"
            )
        injected_raw = _require_bool(
            payload.get("injected"),
            "injected",
        )
        lower_raw = _require_bool(
            payload.get("lower_integrity_injected"),
            "lower_integrity_injected",
        )
        try:
            capture_status = CaptureStatus(
                _require_text(
                    payload.get("capture_status"),
                    "capture_status",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise GhostWalkListenerContractError(
                "unsupported capture_status"
            ) from exc
        receipt = cls(
            listener_id=_require_text(
                payload.get("listener_id"),
                "listener_id",
                maximum=512,
            ),
            listener_sequence=sequence_raw,
            session_id=_require_text(
                payload.get("session_id"),
                "session_id",
                maximum=512,
            ),
            raw_event_sha256=_require_sha256(
                payload.get("raw_event_sha256"),
                "raw_event_sha256",
            ),
            pointer_event_sha256=_require_sha256(
                payload.get("pointer_event_sha256"),
                "pointer_event_sha256",
            ),
            capture_receipt_sha256=_require_sha256(
                payload.get("capture_receipt_sha256"),
                "capture_receipt_sha256",
            ),
            capture_status=capture_status,
            injected=injected_raw,
            lower_integrity_injected=lower_raw,
            observed_at=_require_timestamp(
                payload.get("observed_at"),
                "observed_at",
            ),
            previous_listener_receipt_sha256=(
                None
                if payload.get("previous_listener_receipt_sha256") is None
                else _require_sha256(
                    payload.get("previous_listener_receipt_sha256"),
                    "previous_listener_receipt_sha256",
                )
            ),
            operational_authority=_require_bool(
                payload.get("operational_authority"),
                "operational_authority",
            ),
            action_authority=_require_bool(
                payload.get("action_authority"),
                "action_authority",
            ),
            execution_authority=_require_bool(
                payload.get("execution_authority"),
                "execution_authority",
            ),
            schema_version=_require_text(
                payload.get("schema_version"),
                "schema_version",
                maximum=128,
            ),
        )
        if receipt.receipt_sha256 != claimed:
            raise GhostWalkListenerContractError(
                "ghost-walk listener receipt hash mismatch"
            )
        return receipt


@dataclass(frozen=True, slots=True)
class GhostWalkListenerOutcome:
    receipt: GhostWalkListenerReceipt
    pointer_event: PointerClickEvent
    capture_outcome: GhostWalkCaptureOutcome


class GhostWalkListenerBridge:
    """Persist listener provenance and delegate exact capture to v0.14."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        capture_adapter: GhostWalkCaptureAdapter,
        listener_id: str,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkListenerContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._capture_adapter = capture_adapter
        self.listener_id = _require_text(
            listener_id,
            "listener_id",
            maximum=512,
        )

    def observe_left_button(
        self,
        *,
        session_id: str,
        raw_event: RawMouseHookEvent,
        observed_at: str,
    ) -> GhostWalkListenerOutcome:
        _require_text(session_id, "session_id", maximum=512)
        observed_at = _require_timestamp(observed_at, "observed_at")
        prior_rows = self._ledger.ghostwalk_listener_receipts(
            listener_id=self.listener_id
        )
        prior = [
            GhostWalkListenerReceipt.from_dict(row)
            for row in prior_rows
        ]
        previous_receipt: GhostWalkListenerReceipt | None = None
        for expected_sequence, item in enumerate(prior):
            if item.listener_id != self.listener_id:
                raise GhostWalkListenerContractError(
                    "listener identity changed in persisted receipt chain"
                )
            if item.listener_sequence != expected_sequence:
                raise GhostWalkListenerContractError(
                    "persisted listener sequences are not contiguous"
                )
            expected_previous = (
                None
                if previous_receipt is None
                else previous_receipt.receipt_sha256
            )
            if item.previous_listener_receipt_sha256 != expected_previous:
                raise GhostWalkListenerContractError(
                    "persisted listener receipt hash chain mismatch"
                )
            previous_receipt = item
        sequence = len(prior)
        event_identity = _canonical_sha256(
            {
                "listener_id": self.listener_id,
                "listener_sequence": sequence,
                "session_id": session_id,
                "raw_event_sha256": raw_event.raw_event_sha256,
                "observed_at": observed_at,
            }
        )
        pointer_event = PointerClickEvent(
            event_id=f"windows-hook:{event_identity}",
            x_px=raw_event.x_px,
            y_px=raw_event.y_px,
            button=PointerButton.LEFT,
            observed_at=observed_at,
            injected=raw_event.injected,
        )
        capture = self._capture_adapter.capture_click(
            session_id=session_id,
            event=pointer_event,
        )
        receipt = GhostWalkListenerReceipt(
            listener_id=self.listener_id,
            listener_sequence=sequence,
            session_id=session_id,
            raw_event_sha256=raw_event.raw_event_sha256,
            pointer_event_sha256=pointer_event.event_sha256,
            capture_receipt_sha256=capture.receipt.receipt_sha256,
            capture_status=capture.receipt.status,
            injected=raw_event.injected,
            lower_integrity_injected=(
                raw_event.lower_integrity_injected
            ),
            observed_at=observed_at,
            previous_listener_receipt_sha256=(
                None
                if previous_receipt is None
                else previous_receipt.receipt_sha256
            ),
        )
        self._ledger.append_ghostwalk_listener_receipt(receipt)
        return GhostWalkListenerOutcome(
            receipt=receipt,
            pointer_event=pointer_event,
            capture_outcome=capture,
        )


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt", _POINT),
        ("lPrivate", ctypes.c_uint32),
    ]


class WindowsGhostWalkListener:
    """Blocking Windows WH_MOUSE_LL observer with explicit stop support."""

    def __init__(
        self,
        *,
        bridge: GhostWalkListenerBridge,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        if os.name != "nt":
            raise GhostWalkListenerContractError(
                "WindowsGhostWalkListener requires Windows"
            )
        self._bridge = bridge
        self._clock = clock
        self._thread_id: int | None = None
        self._hook_handle: int | None = None
        self._callback_ref: object | None = None
        self._last_callback_error: Exception | None = None

    def run(self, *, session_id: str) -> None:
        """Run the observation message loop until stop() posts WM_QUIT."""

        _require_text(session_id, "session_id", maximum=512)
        if self._hook_handle is not None:
            raise GhostWalkListenerContractError(
                "Windows ghost-walk listener is already running"
            )

        windll = getattr(ctypes, "windll", None)
        winfunctype = getattr(ctypes, "WINFUNCTYPE", None)
        if windll is None or winfunctype is None:
            raise GhostWalkListenerContractError(
                "ctypes Windows hook APIs are unavailable"
            )
        user32 = windll.user32
        kernel32 = windll.kernel32

        post_thread_message = user32.PostThreadMessageW
        post_thread_message.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        post_thread_message.restype = ctypes.c_int

        event_queue: queue.Queue[
            tuple[RawMouseHookEvent, str] | None
        ] = queue.Queue(maxsize=MAX_PENDING_HOOK_EVENTS)

        hook_proc_type = winfunctype(
            ctypes.c_ssize_t,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )

        set_windows_hook_ex = user32.SetWindowsHookExW
        set_windows_hook_ex.argtypes = [
            ctypes.c_int,
            hook_proc_type,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        set_windows_hook_ex.restype = ctypes.c_void_p

        call_next_hook_ex = user32.CallNextHookEx
        call_next_hook_ex.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        call_next_hook_ex.restype = ctypes.c_ssize_t

        unhook_windows_hook_ex = user32.UnhookWindowsHookEx
        unhook_windows_hook_ex.argtypes = [ctypes.c_void_p]
        unhook_windows_hook_ex.restype = ctypes.c_int

        get_message = user32.GetMessageW
        get_message.argtypes = [
            ctypes.POINTER(_MSG),
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        get_message.restype = ctypes.c_int

        get_current_thread_id = kernel32.GetCurrentThreadId
        get_current_thread_id.argtypes = []
        get_current_thread_id.restype = ctypes.c_uint32

        def request_quit() -> None:
            thread_id = self._thread_id
            if thread_id is not None:
                post_thread_message(
                    thread_id,
                    WM_QUIT,
                    0,
                    0,
                )

        def observation_worker() -> None:
            while True:
                item = event_queue.get()
                if item is None:
                    return
                raw, observed_at = item
                try:
                    self._bridge.observe_left_button(
                        session_id=session_id,
                        raw_event=raw,
                        observed_at=observed_at,
                    )
                except Exception as exc:
                    self._last_callback_error = exc
                    request_quit()
                    return

        worker_thread = threading.Thread(
            target=observation_worker,
            name="PhiOS-GhostWalk-Observer",
            daemon=True,
        )

        def callback(
            n_code: int,
            w_param: int,
            l_param: int,
        ) -> int:
            if n_code >= 0 and w_param == WM_LBUTTONDOWN:
                try:
                    observed = ctypes.cast(
                        l_param,
                        ctypes.POINTER(_MSLLHOOKSTRUCT),
                    ).contents
                    raw = RawMouseHookEvent(
                        x_px=int(observed.pt.x),
                        y_px=int(observed.pt.y),
                        flags=int(observed.flags),
                        hook_time_ms=int(observed.time),
                        extra_info=int(observed.dwExtraInfo),
                    )
                    event_queue.put_nowait(
                        (raw, self._clock())
                    )
                except (Exception, queue.Full) as exc:
                    self._last_callback_error = exc
                    request_quit()
            return int(
                call_next_hook_ex(
                    None,
                    n_code,
                    w_param,
                    l_param,
                )
            )

        callback_ref = hook_proc_type(callback)
        hook = set_windows_hook_ex(
            WH_MOUSE_LL,
            callback_ref,
            None,
            0,
        )
        if not hook:
            raise GhostWalkListenerContractError(
                "failed to install Windows low-level mouse hook"
            )

        self._callback_ref = callback_ref
        self._hook_handle = int(hook)
        self._thread_id = int(get_current_thread_id())
        worker_thread.start()
        message = _MSG()

        try:
            while True:
                result = int(
                    get_message(
                        ctypes.byref(message),
                        None,
                        0,
                        0,
                    )
                )
                if result == 0:
                    break
                if result < 0:
                    raise GhostWalkListenerContractError(
                        "Windows GetMessageW failed"
                    )
                if self._last_callback_error is not None:
                    error = self._last_callback_error
                    self._last_callback_error = None
                    raise GhostWalkListenerContractError(
                        "ghost-walk hook callback failed"
                    ) from error
        finally:
            unhook_windows_hook_ex(hook)
            event_queue.put(None)
            worker_thread.join(timeout=WORKER_SHUTDOWN_SECONDS)
            if worker_thread.is_alive() and self._last_callback_error is None:
                self._last_callback_error = GhostWalkListenerContractError(
                    "ghost-walk observation worker did not stop"
                )
            self._hook_handle = None
            self._thread_id = None
            self._callback_ref = None

        if self._last_callback_error is not None:
            error = self._last_callback_error
            self._last_callback_error = None
            raise GhostWalkListenerContractError(
                "ghost-walk hook callback failed"
            ) from error

    def stop(self) -> None:
        """Request loop termination without injecting desktop input."""

        thread_id = self._thread_id
        if thread_id is None:
            return
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise GhostWalkListenerContractError(
                "ctypes Windows API loader is unavailable"
            )
        post_thread_message = windll.user32.PostThreadMessageW
        post_thread_message.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        post_thread_message.restype = ctypes.c_int
        if not post_thread_message(
            thread_id,
            WM_QUIT,
            0,
            0,
        ):
            raise GhostWalkListenerContractError(
                "failed to post listener stop message"
            )
