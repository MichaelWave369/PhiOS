"""Guarded pixel-anchor mapping for Macro Runtime v0.12.

Ghost-walk observations can produce window-relative pixel anchors. The guard
revalidates frame identity and interference conditions before coordinates are
considered clear to attempt. CLEAR is not execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from phios.spine.ledger import RealityLedger

INTERACTION_FRAME_SCHEMA_VERSION = "phios.interaction_frame.v0.12"
PIXEL_ANCHOR_SCHEMA_VERSION = "phios.pixel_anchor.v0.12"
INTERACTION_GUARD_SCHEMA_VERSION = "phios.interaction_guard_receipt.v0.12"
PPM_SCALE = 1_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class InteractionGuardContractError(ValueError):
    """Raised when a GUI interaction anchor cannot be trusted."""


class GuardDecision(StrEnum):
    CLEAR = "CLEAR"
    HOLD = "HOLD"


class GuardReason(StrEnum):
    FRAME_MATCH = "FRAME_MATCH"
    PROCESS_MISMATCH = "PROCESS_MISMATCH"
    WINDOW_MISMATCH = "WINDOW_MISMATCH"
    NOT_FOREGROUND = "NOT_FOREGROUND"
    OVERLAY_DETECTED = "OVERLAY_DETECTED"
    OPERATOR_INPUT_DETECTED = "OPERATOR_INPUT_DETECTED"
    POINTER_MOVED = "POINTER_MOVED"
    COORDINATE_OUT_OF_BOUNDS = "COORDINATE_OUT_OF_BOUNDS"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 1024,
) -> str:
    if not isinstance(value, str) or not value:
        raise InteractionGuardContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise InteractionGuardContractError(
            f"{field} exceeds {maximum} characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise InteractionGuardContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InteractionGuardContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise InteractionGuardContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise InteractionGuardContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InteractionGuardContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise InteractionGuardContractError(
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
        raise InteractionGuardContractError(
            "interaction payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WindowFrame:
    process_id: str
    window_title_sha256: str
    left_px: int
    top_px: int
    width_px: int
    height_px: int
    display_scale_percent: int
    foreground: bool
    captured_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = INTERACTION_FRAME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INTERACTION_FRAME_SCHEMA_VERSION:
            raise InteractionGuardContractError(
                "unsupported interaction frame schema"
            )
        _require_text(self.process_id, "process_id", maximum=512)
        _require_sha256(
            self.window_title_sha256,
            "window_title_sha256",
        )
        _require_int(self.left_px, "left_px")
        _require_int(self.top_px, "top_px")
        _require_int(self.width_px, "width_px", minimum=1)
        _require_int(self.height_px, "height_px", minimum=1)
        _require_int(
            self.display_scale_percent,
            "display_scale_percent",
            minimum=50,
            maximum=500,
        )
        if not isinstance(self.foreground, bool):
            raise InteractionGuardContractError(
                "foreground must be Boolean"
            )
        _require_timestamp(self.captured_at, "captured_at")
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise InteractionGuardContractError(
                "WindowFrame cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "process_id": self.process_id,
            "window_title_sha256": self.window_title_sha256,
            "left_px": self.left_px,
            "top_px": self.top_px,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "display_scale_percent": self.display_scale_percent,
            "foreground": self.foreground,
            "captured_at": self.captured_at,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def frame_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())


@dataclass(frozen=True, slots=True)
class PixelAnchor:
    anchor_id: str
    source_frame_sha256: str
    process_id: str
    window_title_sha256: str
    x_ppm: int
    y_ppm: int
    observed_x_px: int
    observed_y_px: int
    semantic_hint: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = PIXEL_ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PIXEL_ANCHOR_SCHEMA_VERSION:
            raise InteractionGuardContractError(
                "unsupported pixel anchor schema"
            )
        _require_text(self.anchor_id, "anchor_id", maximum=512)
        _require_sha256(
            self.source_frame_sha256,
            "source_frame_sha256",
        )
        _require_text(self.process_id, "process_id", maximum=512)
        _require_sha256(
            self.window_title_sha256,
            "window_title_sha256",
        )
        _require_int(self.x_ppm, "x_ppm", minimum=0, maximum=PPM_SCALE)
        _require_int(self.y_ppm, "y_ppm", minimum=0, maximum=PPM_SCALE)
        _require_int(self.observed_x_px, "observed_x_px")
        _require_int(self.observed_y_px, "observed_y_px")
        if self.semantic_hint is not None:
            _require_text(
                self.semantic_hint,
                "semantic_hint",
                maximum=1024,
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise InteractionGuardContractError(
                "PixelAnchor cannot carry authority"
            )

    @classmethod
    def from_observed_click(
        cls,
        *,
        anchor_id: str,
        frame: WindowFrame,
        x_px: int,
        y_px: int,
        semantic_hint: str | None = None,
    ) -> "PixelAnchor":
        _require_int(x_px, "x_px")
        _require_int(y_px, "y_px")
        if not (
            frame.left_px <= x_px < frame.left_px + frame.width_px
            and frame.top_px <= y_px < frame.top_px + frame.height_px
        ):
            raise InteractionGuardContractError(
                "observed click is outside source window frame"
            )
        relative_x = x_px - frame.left_px
        relative_y = y_px - frame.top_px
        x_ppm = round(relative_x * PPM_SCALE / frame.width_px)
        y_ppm = round(relative_y * PPM_SCALE / frame.height_px)
        return cls(
            anchor_id=anchor_id,
            source_frame_sha256=frame.frame_sha256,
            process_id=frame.process_id,
            window_title_sha256=frame.window_title_sha256,
            x_ppm=x_ppm,
            y_ppm=y_ppm,
            observed_x_px=x_px,
            observed_y_px=y_px,
            semantic_hint=semantic_hint,
        )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "anchor_id": self.anchor_id,
            "source_frame_sha256": self.source_frame_sha256,
            "process_id": self.process_id,
            "window_title_sha256": self.window_title_sha256,
            "x_ppm": self.x_ppm,
            "y_ppm": self.y_ppm,
            "observed_x_px": self.observed_x_px,
            "observed_y_px": self.observed_y_px,
            "semantic_hint": self.semantic_hint,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def anchor_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def resolve(self, frame: WindowFrame) -> tuple[int, int]:
        x_px = frame.left_px + round(
            frame.width_px * self.x_ppm / PPM_SCALE
        )
        y_px = frame.top_px + round(
            frame.height_px * self.y_ppm / PPM_SCALE
        )
        return x_px, y_px


@dataclass(frozen=True, slots=True)
class InteractionSnapshot:
    frame: WindowFrame
    pointer_x_px: int
    pointer_y_px: int
    pointer_moved_since_anchor: bool
    operator_input_detected: bool
    unexpected_overlay_detected: bool

    def __post_init__(self) -> None:
        _require_int(self.pointer_x_px, "pointer_x_px")
        _require_int(self.pointer_y_px, "pointer_y_px")
        for field, value in (
            ("pointer_moved_since_anchor", self.pointer_moved_since_anchor),
            ("operator_input_detected", self.operator_input_detected),
            (
                "unexpected_overlay_detected",
                self.unexpected_overlay_detected,
            ),
        ):
            if not isinstance(value, bool):
                raise InteractionGuardContractError(
                    f"{field} must be Boolean"
                )


@dataclass(frozen=True, slots=True)
class InteractionGuardReceipt:
    anchor_sha256: str
    frame_sha256: str
    decision: GuardDecision
    reasons: tuple[GuardReason, ...]
    resolved_x_px: int | None
    resolved_y_px: int | None
    observed_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = INTERACTION_GUARD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INTERACTION_GUARD_SCHEMA_VERSION:
            raise InteractionGuardContractError(
                "unsupported interaction guard receipt schema"
            )
        _require_sha256(self.anchor_sha256, "anchor_sha256")
        _require_sha256(self.frame_sha256, "frame_sha256")
        if not self.reasons:
            raise InteractionGuardContractError(
                "interaction guard receipt requires reasons"
            )
        if tuple(sorted(set(self.reasons), key=lambda x: x.value)) != (
            self.reasons
        ):
            raise InteractionGuardContractError(
                "guard reasons must be sorted and unique"
            )
        _require_timestamp(self.observed_at, "observed_at")
        if self.decision is GuardDecision.CLEAR:
            if (
                self.resolved_x_px is None
                or self.resolved_y_px is None
            ):
                raise InteractionGuardContractError(
                    "CLEAR guard receipt requires resolved coordinates"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise InteractionGuardContractError(
                "InteractionGuardReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "anchor_sha256": self.anchor_sha256,
            "frame_sha256": self.frame_sha256,
            "decision": self.decision.value,
            "reasons": [item.value for item in self.reasons],
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


class InteractionGuard:
    """Revalidate one ghost-walk pixel anchor before adapter execution."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise InteractionGuardContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger

    def assess(
        self,
        *,
        anchor: PixelAnchor,
        snapshot: InteractionSnapshot,
        observed_at: str,
    ) -> InteractionGuardReceipt:
        frame = snapshot.frame
        reasons: set[GuardReason] = set()

        if frame.process_id != anchor.process_id:
            reasons.add(GuardReason.PROCESS_MISMATCH)
        if frame.window_title_sha256 != anchor.window_title_sha256:
            reasons.add(GuardReason.WINDOW_MISMATCH)
        if not frame.foreground:
            reasons.add(GuardReason.NOT_FOREGROUND)
        if snapshot.unexpected_overlay_detected:
            reasons.add(GuardReason.OVERLAY_DETECTED)
        if snapshot.operator_input_detected:
            reasons.add(GuardReason.OPERATOR_INPUT_DETECTED)
        if snapshot.pointer_moved_since_anchor:
            reasons.add(GuardReason.POINTER_MOVED)

        resolved_x: int | None = None
        resolved_y: int | None = None
        if not reasons:
            candidate_x, candidate_y = anchor.resolve(frame)
            if not (
                frame.left_px
                <= candidate_x
                < frame.left_px + frame.width_px
                and frame.top_px
                <= candidate_y
                < frame.top_px + frame.height_px
            ):
                reasons.add(GuardReason.COORDINATE_OUT_OF_BOUNDS)
            else:
                reasons.add(GuardReason.FRAME_MATCH)
                resolved_x = candidate_x
                resolved_y = candidate_y

        decision = (
            GuardDecision.CLEAR
            if reasons == {GuardReason.FRAME_MATCH}
            else GuardDecision.HOLD
        )
        ordered = tuple(sorted(reasons, key=lambda item: item.value))
        receipt = InteractionGuardReceipt(
            anchor_sha256=anchor.anchor_sha256,
            frame_sha256=frame.frame_sha256,
            decision=decision,
            reasons=ordered,
            resolved_x_px=resolved_x,
            resolved_y_px=resolved_y,
            observed_at=observed_at,
        )
        self._ledger.append_interaction_guard_receipt(receipt)
        return receipt
