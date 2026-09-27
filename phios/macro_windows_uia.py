"""Windows UI Automation semantic targeting for Macro Runtime v0.16.

This provider enriches v0.14 Ghost-Walk click capture with Microsoft UI
Automation identity metadata. It never reads control values and never injects
desktop input.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_ghostwalk_capture import PointerClickEvent
from phios.macro_interaction_guard import WindowFrame
from phios.spine.ledger import RealityLedger

UIA_ELEMENT_SNAPSHOT_SCHEMA_VERSION = "phios.uia_element_snapshot.v0.16"
UIA_LOOKUP_RECEIPT_SCHEMA_VERSION = "phios.uia_lookup_receipt.v0.16"
WINDOWS_UIA_PROVIDER_ID = "windows.uia.v0.16"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WindowsUiaContractError(ValueError):
    """Raised when Windows UI Automation evidence cannot be trusted."""


class UiaLookupDecision(StrEnum):
    FOUND = "FOUND"
    NO_ELEMENT = "NO_ELEMENT"
    AMBIGUOUS = "AMBIGUOUS"
    FRAME_MISMATCH = "FRAME_MISMATCH"
    ERROR = "ERROR"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise WindowsUiaContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise WindowsUiaContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise WindowsUiaContractError(
            f"{field} contains control characters"
        )
    return value


def _optional_text(
    value: object,
    field: str,
    *,
    maximum: int = 1024,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WindowsUiaContractError(
            f"{field} must be string or null"
        )
    cleaned = value.strip()
    if not cleaned:
        return None
    return _require_text(cleaned, field, maximum=maximum)


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WindowsUiaContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise WindowsUiaContractError(
            f"{field} must be at least {minimum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise WindowsUiaContractError(
            f"{field} must be Boolean"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise WindowsUiaContractError(
            f"{field} must be a lowercase SHA-256 digest"
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
        raise WindowsUiaContractError(
            "UI Automation payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class UiaElementSnapshot:
    """Privacy-bounded identity metadata for one UI Automation element."""

    process_id: int
    automation_id: str | None
    name_hint: str | None
    control_type: int | None
    class_name: str | None
    framework_id: str | None
    enabled: bool | None
    offscreen: bool | None
    is_password: bool | None
    bounding_left: int | None
    bounding_top: int | None
    bounding_right: int | None
    bounding_bottom: int | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = UIA_ELEMENT_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != UIA_ELEMENT_SNAPSHOT_SCHEMA_VERSION:
            raise WindowsUiaContractError(
                "unsupported UI Automation snapshot schema"
            )
        _require_int(self.process_id, "process_id", minimum=1)
        _optional_text(
            self.automation_id,
            "automation_id",
            maximum=2048,
        )
        _optional_text(self.name_hint, "name_hint", maximum=512)
        if self.control_type is not None:
            _require_int(
                self.control_type,
                "control_type",
                minimum=0,
            )
        _optional_text(self.class_name, "class_name", maximum=512)
        _optional_text(self.framework_id, "framework_id", maximum=256)
        for field, value in (
            ("enabled", self.enabled),
            ("offscreen", self.offscreen),
            ("is_password", self.is_password),
        ):
            if value is not None:
                _require_bool(value, field)
        bounds = (
            self.bounding_left,
            self.bounding_top,
            self.bounding_right,
            self.bounding_bottom,
        )
        if any(value is not None for value in bounds):
            if any(value is None for value in bounds):
                raise WindowsUiaContractError(
                    "UIA bounding rectangle must be complete or absent"
                )
            assert self.bounding_left is not None
            assert self.bounding_top is not None
            assert self.bounding_right is not None
            assert self.bounding_bottom is not None
            _require_int(
                self.bounding_left,
                "bounding_left",
                minimum=None,
            )
            _require_int(
                self.bounding_top,
                "bounding_top",
                minimum=None,
            )
            _require_int(
                self.bounding_right,
                "bounding_right",
                minimum=None,
            )
            _require_int(
                self.bounding_bottom,
                "bounding_bottom",
                minimum=None,
            )
            if (
                self.bounding_right <= self.bounding_left
                or self.bounding_bottom <= self.bounding_top
            ):
                raise WindowsUiaContractError(
                    "UIA bounding rectangle is invalid"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise WindowsUiaContractError(
                "UiaElementSnapshot cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "process_id": self.process_id,
            "automation_id": self.automation_id,
            "name_hint": self.name_hint,
            "control_type": self.control_type,
            "class_name": self.class_name,
            "framework_id": self.framework_id,
            "enabled": self.enabled,
            "offscreen": self.offscreen,
            "is_password": self.is_password,
            "bounding_left": self.bounding_left,
            "bounding_top": self.bounding_top,
            "bounding_right": self.bounding_right,
            "bounding_bottom": self.bounding_bottom,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def snapshot_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["snapshot_sha256"] = self.snapshot_sha256
        return payload


class UiaBackend(Protocol):
    """Read-only point lookup backend."""

    backend_id: str

    def element_from_point(
        self,
        *,
        x_px: int,
        y_px: int,
    ) -> UiaElementSnapshot | None: ...


@dataclass(frozen=True, slots=True)
class UiaLookupReceipt:
    event_sha256: str
    frame_sha256: str
    provider_id: str
    backend_id: str
    decision: UiaLookupDecision
    reason: str
    snapshot_sha256: str | None
    semantic_target_sha256: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = UIA_LOOKUP_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != UIA_LOOKUP_RECEIPT_SCHEMA_VERSION:
            raise WindowsUiaContractError(
                "unsupported UI Automation lookup receipt schema"
            )
        _require_sha256(self.event_sha256, "event_sha256")
        _require_sha256(self.frame_sha256, "frame_sha256")
        _require_text(self.provider_id, "provider_id", maximum=256)
        _require_text(self.backend_id, "backend_id", maximum=256)
        _require_text(self.reason, "reason", maximum=512)
        if self.snapshot_sha256 is not None:
            _require_sha256(
                self.snapshot_sha256,
                "snapshot_sha256",
            )
        if self.semantic_target_sha256 is not None:
            _require_sha256(
                self.semantic_target_sha256,
                "semantic_target_sha256",
            )
        if self.decision is UiaLookupDecision.FOUND:
            if (
                self.snapshot_sha256 is None
                or self.semantic_target_sha256 is None
            ):
                raise WindowsUiaContractError(
                    "FOUND UIA lookup requires snapshot and target hashes"
                )
        elif self.semantic_target_sha256 is not None:
            raise WindowsUiaContractError(
                "non-FOUND UIA lookup cannot claim semantic target hash"
            )
        if self.decision is UiaLookupDecision.NO_ELEMENT:
            if self.snapshot_sha256 is not None:
                raise WindowsUiaContractError(
                    "NO_ELEMENT UIA lookup cannot claim snapshot"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise WindowsUiaContractError(
                "UiaLookupReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_sha256": self.event_sha256,
            "frame_sha256": self.frame_sha256,
            "provider_id": self.provider_id,
            "backend_id": self.backend_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "snapshot_sha256": self.snapshot_sha256,
            "semantic_target_sha256": self.semantic_target_sha256,
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


class WindowsUiaSemanticProvider:
    """Emit a strong SemanticTarget only when UIA exposes AutomationId."""

    provider_id = WINDOWS_UIA_PROVIDER_ID

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        backend: UiaBackend,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise WindowsUiaContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._backend = backend

    @classmethod
    def from_system(
        cls,
        *,
        ledger: RealityLedger,
    ) -> "WindowsUiaSemanticProvider":
        """Construct the real optional Windows/comtypes UIA provider."""

        return cls(
            ledger=ledger,
            backend=ComtypesWindowsUiaBackend(),
        )

    def target_for_click(
        self,
        *,
        event: PointerClickEvent,
        frame: WindowFrame,
    ) -> SemanticTarget | None:
        try:
            snapshot = self._backend.element_from_point(
                x_px=event.x_px,
                y_px=event.y_px,
            )
        except Exception:
            self._append_receipt(
                event=event,
                frame=frame,
                decision=UiaLookupDecision.ERROR,
                reason="uia_backend_error",
                snapshot=None,
                target=None,
            )
            raise

        if snapshot is None:
            self._append_receipt(
                event=event,
                frame=frame,
                decision=UiaLookupDecision.NO_ELEMENT,
                reason="no_uia_element_at_point",
                snapshot=None,
                target=None,
            )
            return None

        expected_process = f"pid:{snapshot.process_id}"
        if frame.process_id != expected_process:
            self._append_receipt(
                event=event,
                frame=frame,
                decision=UiaLookupDecision.FRAME_MISMATCH,
                reason="uia_process_does_not_match_window_frame",
                snapshot=snapshot,
                target=None,
            )
            return None

        if (
            snapshot.bounding_left is not None
            and snapshot.bounding_top is not None
            and snapshot.bounding_right is not None
            and snapshot.bounding_bottom is not None
            and not (
                snapshot.bounding_left <= event.x_px < snapshot.bounding_right
                and snapshot.bounding_top <= event.y_px < snapshot.bounding_bottom
            )
        ):
            self._append_receipt(
                event=event,
                frame=frame,
                decision=UiaLookupDecision.AMBIGUOUS,
                reason="uia_element_bounds_do_not_contain_click",
                snapshot=snapshot,
                target=None,
            )
            return None

        if snapshot.offscreen is True:
            self._append_receipt(
                event=event,
                frame=frame,
                decision=UiaLookupDecision.AMBIGUOUS,
                reason="uia_element_reported_offscreen",
                snapshot=snapshot,
                target=None,
            )
            return None

        automation_id = _optional_text(
            snapshot.automation_id,
            "automation_id",
            maximum=2048,
        )
        if automation_id is None:
            self._append_receipt(
                event=event,
                frame=frame,
                decision=UiaLookupDecision.AMBIGUOUS,
                reason="automation_id_missing",
                snapshot=snapshot,
                target=None,
            )
            return None

        selector_payload = {
            "automation_id": automation_id,
            "control_type": snapshot.control_type,
        }
        target = SemanticTarget(
            provider=self.provider_id,
            selector=_canonical_json(selector_payload),
            role=(
                None
                if snapshot.control_type is None
                else f"uia.control_type.{snapshot.control_type}"
            ),
            name_hint=(
                None
                if snapshot.is_password is True
                else snapshot.name_hint
            ),
        )
        self._append_receipt(
            event=event,
            frame=frame,
            decision=UiaLookupDecision.FOUND,
            reason="strong_automation_id",
            snapshot=snapshot,
            target=target,
        )
        return target

    def _append_receipt(
        self,
        *,
        event: PointerClickEvent,
        frame: WindowFrame,
        decision: UiaLookupDecision,
        reason: str,
        snapshot: UiaElementSnapshot | None,
        target: SemanticTarget | None,
    ) -> None:
        if snapshot is not None:
            self._ledger.append_uia_element_snapshot(snapshot)
        receipt = UiaLookupReceipt(
            event_sha256=event.event_sha256,
            frame_sha256=frame.frame_sha256,
            provider_id=self.provider_id,
            backend_id=self._backend.backend_id,
            decision=decision,
            reason=reason,
            snapshot_sha256=(
                None if snapshot is None else snapshot.snapshot_sha256
            ),
            semantic_target_sha256=(
                None if target is None else target.target_sha256
            ),
        )
        self._ledger.append_uia_lookup_receipt(receipt)


class ComtypesWindowsUiaBackend:
    """Windows UIA backend using the optional comtypes dependency."""

    backend_id = "windows.comtypes.uiautomationcore.v0.16"

    def __init__(self) -> None:
        if os.name != "nt":
            raise WindowsUiaContractError(
                "ComtypesWindowsUiaBackend requires Windows"
            )
        try:
            client = importlib.import_module("comtypes.client")
        except ImportError as exc:
            raise WindowsUiaContractError(
                "Windows UIA support requires the optional 'uia' extra"
            ) from exc

        client.GetModule("UIAutomationCore.dll")
        uia = importlib.import_module("comtypes.gen.UIAutomationClient")
        self._uia_module = uia
        self._automation = client.CreateObject(
            uia.CUIAutomation._reg_clsid_,
            interface=uia.IUIAutomation,
        )

    def element_from_point(
        self,
        *,
        x_px: int,
        y_px: int,
    ) -> UiaElementSnapshot | None:
        _require_int(x_px, "x_px", minimum=None)
        _require_int(y_px, "y_px", minimum=None)

        wintypes = importlib.import_module("ctypes.wintypes")
        point_type = getattr(
            wintypes,
            "tagPOINT",
            getattr(wintypes, "POINT"),
        )
        element = self._automation.ElementFromPoint(
            point_type(x_px, y_px)
        )
        if element is None:
            return None

        process_id = self._required_int_property(
            element,
            "CurrentProcessId",
            "currentProcessId",
        )
        automation_id = self._string_property(
            element,
            "CurrentAutomationId",
            "currentAutomationId",
            maximum=2048,
        )
        name = self._string_property(
            element,
            "CurrentName",
            "currentName",
            maximum=512,
        )
        class_name = self._string_property(
            element,
            "CurrentClassName",
            "currentClassName",
            maximum=512,
        )
        framework_id = self._string_property(
            element,
            "CurrentFrameworkId",
            "currentFrameworkId",
            maximum=256,
        )
        control_type_raw = self._optional_property(
            element,
            "CurrentControlType",
            "currentControlType",
        )
        enabled_raw = self._optional_property(
            element,
            "CurrentIsEnabled",
            "currentIsEnabled",
        )
        offscreen_raw = self._optional_property(
            element,
            "CurrentIsOffscreen",
            "currentIsOffscreen",
        )
        password_raw = self._optional_property(
            element,
            "CurrentIsPassword",
            "currentIsPassword",
        )
        rectangle = self._optional_property(
            element,
            "CurrentBoundingRectangle",
            "currentBoundingRectangle",
        )

        bounds: tuple[int, int, int, int] | None = None
        if rectangle is not None:
            left = self._coerce_int(
                getattr(rectangle, "left", None),
                "bounding_left",
            )
            top = self._coerce_int(
                getattr(rectangle, "top", None),
                "bounding_top",
            )
            right = self._coerce_int(
                getattr(rectangle, "right", None),
                "bounding_right",
            )
            bottom = self._coerce_int(
                getattr(rectangle, "bottom", None),
                "bounding_bottom",
            )
            if (
                left is not None
                and top is not None
                and right is not None
                and bottom is not None
            ):
                bounds = (left, top, right, bottom)

        return UiaElementSnapshot(
            process_id=process_id,
            automation_id=automation_id,
            name_hint=name,
            control_type=self._coerce_int(
                control_type_raw,
                "control_type",
            ),
            class_name=class_name,
            framework_id=framework_id,
            enabled=(
                None if enabled_raw is None else bool(enabled_raw)
            ),
            offscreen=(
                None if offscreen_raw is None else bool(offscreen_raw)
            ),
            is_password=(
                None if password_raw is None else bool(password_raw)
            ),
            bounding_left=(
                None if bounds is None else bounds[0]
            ),
            bounding_top=(
                None if bounds is None else bounds[1]
            ),
            bounding_right=(
                None if bounds is None else bounds[2]
            ),
            bounding_bottom=(
                None if bounds is None else bounds[3]
            ),
        )

    @staticmethod
    def _coerce_int(
        value: object,
        field: str,
    ) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise WindowsUiaContractError(
                f"{field} cannot be Boolean"
            )
        if isinstance(value, int):
            return value
        raw = getattr(value, "value", None)
        if isinstance(raw, bool):
            raise WindowsUiaContractError(
                f"{field} cannot be Boolean"
            )
        if isinstance(raw, int):
            return raw
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError as exc:
                raise WindowsUiaContractError(
                    f"{field} is not integer-like"
                ) from exc
        try:
            return int(str(value))
        except (TypeError, ValueError) as exc:
            raise WindowsUiaContractError(
                f"{field} is not integer-like"
            ) from exc

    @staticmethod
    def _required_int_property(
        element: object,
        *names: str,
    ) -> int:
        value = ComtypesWindowsUiaBackend._property(
            element,
            *names,
        )
        coerced = ComtypesWindowsUiaBackend._coerce_int(
            value,
            names[0],
        )
        if coerced is None:
            raise WindowsUiaContractError(
                f"UIA integer property unavailable: {names[0]}"
            )
        return coerced

    @staticmethod
    def _property(
        element: object,
        *names: str,
    ) -> object:
        value = ComtypesWindowsUiaBackend._optional_property(
            element,
            *names,
        )
        if value is None:
            raise WindowsUiaContractError(
                f"UIA property unavailable: {names[0]}"
            )
        return value

    @staticmethod
    def _optional_property(
        element: object,
        *names: str,
    ) -> object | None:
        for name in names:
            try:
                return getattr(element, name)
            except (AttributeError, OSError):
                continue
        return None

    @staticmethod
    def _string_property(
        element: object,
        *names: str,
        maximum: int,
    ) -> str | None:
        value = ComtypesWindowsUiaBackend._optional_property(
            element,
            *names,
        )
        if value is None:
            return None
        try:
            text = str(value).strip()
        except Exception:
            return None
        if not text:
            return None
        if len(text) > maximum:
            text = text[:maximum]
        if any(ord(char) < 32 for char in text):
            text = "".join(
                char if ord(char) >= 32 else " "
                for char in text
            ).strip()
        return text or None
