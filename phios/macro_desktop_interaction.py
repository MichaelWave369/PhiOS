"""Governed desktop interaction adapter for Macro Runtime v0.18.

This is the first Macro Runtime layer that can perform one bounded desktop
interaction. Authority still comes exclusively from the existing PhiOS Spine,
PlanActionBinding, and single-use ActionLease path.

The executor revalidates the target immediately before injection and fails
closed on target drift, operator input, foreground-window drift, overlay drift,
or unknown target state.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping, Protocol

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import (
    GuardDecision,
    InteractionGuard,
    InteractionSnapshot,
    PixelAnchor,
    WindowFrame,
)
from phios.macro_uia_revalidation import (
    SemanticReplayRevalidator,
    SemanticRevalidationDecision,
)
from phios.spine.executor import ArtifactResult, OutcomeUnknownError
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine

DESKTOP_CLICK_CAPABILITY_ID = "desktop.interaction.click"
DESKTOP_CLICK_CAPABILITY_VERSION = "0.18.0"
DESKTOP_INTERACTION_RECEIPT_SCHEMA_VERSION = (
    "phios.desktop_interaction_receipt.v0.18"
)
DESKTOP_CLICK_REQUEST_SCHEMA_VERSION = "phios.desktop_click_request.v0.18"
EXPECTED_SENDINPUT_EVENTS = 3
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DesktopInteractionContractError(ValueError):
    """Raised when a desktop interaction contract is malformed."""


class DesktopInteractionHeldError(RuntimeError):
    """Raised when a final desktop safety check refuses the interaction."""


class DesktopTargetMode(StrEnum):
    SEMANTIC = "SEMANTIC"
    WINDOW_RELATIVE_PIXEL = "WINDOW_RELATIVE_PIXEL"


class DesktopInteractionOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    HELD = "HELD"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise DesktopInteractionContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise DesktopInteractionContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise DesktopInteractionContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise DesktopInteractionContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise DesktopInteractionContractError(
            f"{field} must be Boolean"
        )
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DesktopInteractionContractError(
            f"{field} must be an integer"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DesktopInteractionContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise DesktopInteractionContractError(
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
        raise DesktopInteractionContractError(
            "desktop interaction payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _pixel_anchor_from_dict(payload: Mapping[str, object]) -> PixelAnchor:
    claimed = _require_sha256(
        payload.get("anchor_sha256"),
        "anchor_sha256",
    )
    hint_raw = payload.get("semantic_hint")
    anchor = PixelAnchor(
        anchor_id=_require_text(
            payload.get("anchor_id"),
            "anchor_id",
            maximum=512,
        ),
        source_frame_sha256=_require_sha256(
            payload.get("source_frame_sha256"),
            "source_frame_sha256",
        ),
        process_id=_require_text(
            payload.get("process_id"),
            "process_id",
            maximum=512,
        ),
        window_title_sha256=_require_sha256(
            payload.get("window_title_sha256"),
            "window_title_sha256",
        ),
        x_ppm=_require_int(payload.get("x_ppm"), "x_ppm"),
        y_ppm=_require_int(payload.get("y_ppm"), "y_ppm"),
        observed_x_px=_require_int(
            payload.get("observed_x_px"),
            "observed_x_px",
        ),
        observed_y_px=_require_int(
            payload.get("observed_y_px"),
            "observed_y_px",
        ),
        semantic_hint=(
            None
            if hint_raw is None
            else _require_text(
                hint_raw,
                "semantic_hint",
                maximum=1024,
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
    if anchor.anchor_sha256 != claimed:
        raise DesktopInteractionContractError(
            "pixel anchor hash mismatch"
        )
    return anchor


@dataclass(frozen=True, slots=True)
class DesktopClickRequest:
    """Exact v0.13 Ghost-Walk click inputs, revalidated for execution."""

    observation_sha256: str
    target_mode: DesktopTargetMode
    process_id: str
    window_title_sha256: str
    pixel_anchor: PixelAnchor
    semantic_target: SemanticTarget | None
    absolute_pixel_is_evidence_only: bool
    guard_required: bool
    schema_version: str = DESKTOP_CLICK_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_CLICK_REQUEST_SCHEMA_VERSION:
            raise DesktopInteractionContractError(
                "unsupported desktop click request schema"
            )
        _require_sha256(
            self.observation_sha256,
            "observation_sha256",
        )
        _require_text(self.process_id, "process_id", maximum=512)
        _require_sha256(
            self.window_title_sha256,
            "window_title_sha256",
        )
        if self.pixel_anchor.process_id != self.process_id:
            raise DesktopInteractionContractError(
                "pixel anchor process differs from request"
            )
        if (
            self.pixel_anchor.window_title_sha256
            != self.window_title_sha256
        ):
            raise DesktopInteractionContractError(
                "pixel anchor window differs from request"
            )
        if not self.absolute_pixel_is_evidence_only:
            raise DesktopInteractionContractError(
                "absolute desktop pixel must remain evidence-only"
            )
        if not self.guard_required:
            raise DesktopInteractionContractError(
                "desktop click request requires guard"
            )
        if (
            self.target_mode is DesktopTargetMode.SEMANTIC
            and self.semantic_target is None
        ):
            raise DesktopInteractionContractError(
                "SEMANTIC target mode requires semantic target"
            )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "DesktopClickRequest":
        expected_keys = {
            "observation_sha256",
            "preferred_strategy",
            "process_id",
            "window_title_sha256",
            "pixel_anchor",
            "semantic_target",
            "absolute_pixel_is_evidence_only",
            "guard_required",
        }
        if set(payload) != expected_keys:
            raise DesktopInteractionContractError(
                "desktop click payload shape does not match Ghost-Walk contract"
            )
        try:
            target_mode = DesktopTargetMode(
                _require_text(
                    payload.get("preferred_strategy"),
                    "preferred_strategy",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise DesktopInteractionContractError(
                "unsupported desktop target strategy"
            ) from exc

        anchor_raw = payload.get("pixel_anchor")
        if not isinstance(anchor_raw, Mapping):
            raise DesktopInteractionContractError(
                "pixel_anchor must be an object"
            )
        semantic_raw = payload.get("semantic_target")
        if (
            semantic_raw is not None
            and not isinstance(semantic_raw, Mapping)
        ):
            raise DesktopInteractionContractError(
                "semantic_target must be object or null"
            )

        return cls(
            observation_sha256=_require_sha256(
                payload.get("observation_sha256"),
                "observation_sha256",
            ),
            target_mode=target_mode,
            process_id=_require_text(
                payload.get("process_id"),
                "process_id",
                maximum=512,
            ),
            window_title_sha256=_require_sha256(
                payload.get("window_title_sha256"),
                "window_title_sha256",
            ),
            pixel_anchor=_pixel_anchor_from_dict(anchor_raw),
            semantic_target=(
                None
                if semantic_raw is None
                else SemanticTarget.from_dict(semantic_raw)
            ),
            absolute_pixel_is_evidence_only=_require_bool(
                payload.get("absolute_pixel_is_evidence_only"),
                "absolute_pixel_is_evidence_only",
            ),
            guard_required=_require_bool(
                payload.get("guard_required"),
                "guard_required",
            ),
        )

    def body_dict(self) -> dict[str, object]:
        pixel = self.pixel_anchor.body_dict()
        pixel["anchor_sha256"] = self.pixel_anchor.anchor_sha256
        return {
            "schema_version": self.schema_version,
            "observation_sha256": self.observation_sha256,
            "target_mode": self.target_mode.value,
            "process_id": self.process_id,
            "window_title_sha256": self.window_title_sha256,
            "pixel_anchor": pixel,
            "semantic_target": (
                None
                if self.semantic_target is None
                else self.semantic_target.to_dict()
            ),
            "absolute_pixel_is_evidence_only": (
                self.absolute_pixel_is_evidence_only
            ),
            "guard_required": self.guard_required,
        }

    @property
    def request_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())


@dataclass(frozen=True, slots=True)
class OperatorInputSnapshot:
    token: int
    pointer_x_px: int
    pointer_y_px: int

    def __post_init__(self) -> None:
        _require_int(self.token, "token")
        _require_int(self.pointer_x_px, "pointer_x_px")
        _require_int(self.pointer_y_px, "pointer_y_px")


@dataclass(frozen=True, slots=True)
class MouseInjectionResult:
    inserted_events: int
    expected_events: int = EXPECTED_SENDINPUT_EVENTS

    def __post_init__(self) -> None:
        _require_int(self.inserted_events, "inserted_events")
        _require_int(self.expected_events, "expected_events")
        if self.inserted_events < 0:
            raise DesktopInteractionContractError(
                "inserted_events must be non-negative"
            )
        if self.expected_events <= 0:
            raise DesktopInteractionContractError(
                "expected_events must be positive"
            )
        if self.inserted_events > self.expected_events:
            raise DesktopInteractionContractError(
                "inserted_events cannot exceed expected_events"
            )


class DesktopFrameProvider(Protocol):
    provider_id: str

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None: ...

    def frame_at_point(
        self,
        *,
        x_px: int,
        y_px: int,
        observed_at: str,
    ) -> WindowFrame | None: ...


class OperatorInputProbe(Protocol):
    probe_id: str

    def snapshot(self) -> OperatorInputSnapshot: ...


class MouseInjector(Protocol):
    injector_id: str

    def click(
        self,
        *,
        x_px: int,
        y_px: int,
    ) -> MouseInjectionResult: ...


@dataclass(frozen=True, slots=True)
class DesktopInteractionReceipt:
    request_sha256: str
    target_mode: DesktopTargetMode
    proof_receipt_sha256: str | None
    frame_before_sha256: str | None
    frame_final_sha256: str | None
    frame_after_sha256: str | None
    frame_provider_id: str
    input_probe_id: str
    injector_id: str
    input_token_before: int
    input_token_final: int
    pointer_before_x_px: int
    pointer_before_y_px: int
    pointer_final_x_px: int
    pointer_final_y_px: int
    resolved_x_px: int | None
    resolved_y_px: int | None
    inserted_events: int | None
    outcome: DesktopInteractionOutcome
    reason: str
    attempted_at: str
    effect_performed: bool | None
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = DESKTOP_INTERACTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_INTERACTION_RECEIPT_SCHEMA_VERSION:
            raise DesktopInteractionContractError(
                "unsupported desktop interaction receipt schema"
            )
        _require_sha256(self.request_sha256, "request_sha256")
        if self.proof_receipt_sha256 is not None:
            _require_sha256(
                self.proof_receipt_sha256,
                "proof_receipt_sha256",
            )
        for field, value in (
            ("frame_before_sha256", self.frame_before_sha256),
            ("frame_final_sha256", self.frame_final_sha256),
            ("frame_after_sha256", self.frame_after_sha256),
        ):
            if value is not None:
                _require_sha256(value, field)
        _require_text(
            self.frame_provider_id,
            "frame_provider_id",
            maximum=256,
        )
        _require_text(
            self.input_probe_id,
            "input_probe_id",
            maximum=256,
        )
        _require_text(self.injector_id, "injector_id", maximum=256)
        _require_int(self.input_token_before, "input_token_before")
        _require_int(self.input_token_final, "input_token_final")
        _require_int(self.pointer_before_x_px, "pointer_before_x_px")
        _require_int(self.pointer_before_y_px, "pointer_before_y_px")
        _require_int(self.pointer_final_x_px, "pointer_final_x_px")
        _require_int(self.pointer_final_y_px, "pointer_final_y_px")
        if self.resolved_x_px is not None:
            _require_int(self.resolved_x_px, "resolved_x_px")
        if self.resolved_y_px is not None:
            _require_int(self.resolved_y_px, "resolved_y_px")
        if self.inserted_events is not None:
            _require_int(self.inserted_events, "inserted_events")
        _require_text(self.reason, "reason", maximum=512)
        _require_timestamp(self.attempted_at, "attempted_at")
        if self.effect_performed not in {True, False, None}:
            raise DesktopInteractionContractError(
                "effect_performed must be Boolean or null"
            )
        if self.action_authority or self.execution_authority:
            raise DesktopInteractionContractError(
                "desktop interaction receipt cannot grant authority"
            )
        if self.outcome is DesktopInteractionOutcome.SUCCEEDED:
            if (
                self.effect_performed is not True
                or self.inserted_events != EXPECTED_SENDINPUT_EVENTS
                or self.resolved_x_px is None
                or self.resolved_y_px is None
                or self.proof_receipt_sha256 is None
            ):
                raise DesktopInteractionContractError(
                    "SUCCEEDED interaction receipt is incomplete"
                )
        if self.outcome is DesktopInteractionOutcome.HELD:
            if self.effect_performed is not False:
                raise DesktopInteractionContractError(
                    "HELD interaction cannot claim an effect"
                )
        if self.outcome is DesktopInteractionOutcome.FAILED:
            if self.effect_performed is not False:
                raise DesktopInteractionContractError(
                    "FAILED interaction cannot claim a performed effect"
                )
        if self.outcome is DesktopInteractionOutcome.OUTCOME_UNKNOWN:
            if self.effect_performed is not None:
                raise DesktopInteractionContractError(
                    "OUTCOME_UNKNOWN effect state must remain unknown"
                )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "target_mode": self.target_mode.value,
            "proof_receipt_sha256": self.proof_receipt_sha256,
            "frame_before_sha256": self.frame_before_sha256,
            "frame_final_sha256": self.frame_final_sha256,
            "frame_after_sha256": self.frame_after_sha256,
            "frame_provider_id": self.frame_provider_id,
            "input_probe_id": self.input_probe_id,
            "injector_id": self.injector_id,
            "input_token_before": self.input_token_before,
            "input_token_final": self.input_token_final,
            "pointer_before_x_px": self.pointer_before_x_px,
            "pointer_before_y_px": self.pointer_before_y_px,
            "pointer_final_x_px": self.pointer_final_x_px,
            "pointer_final_y_px": self.pointer_final_y_px,
            "resolved_x_px": self.resolved_x_px,
            "resolved_y_px": self.resolved_y_px,
            "inserted_events": self.inserted_events,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "attempted_at": self.attempted_at,
            "effect_performed": self.effect_performed,
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
class _ResolvedTarget:
    proof_receipt_sha256: str
    x_px: int
    y_px: int


class GovernedDesktopClickExecutor:
    """One bounded left-click executor entered only after Spine authorization."""

    def __init__(
        self,
        *,
        spine: PhiOSSpine,
        frame_provider: DesktopFrameProvider,
        input_probe: OperatorInputProbe,
        injector: MouseInjector,
        semantic_revalidator: SemanticReplayRevalidator,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._spine = spine
        self._ledger = spine.ledger
        self._frame_provider = frame_provider
        self._input_probe = input_probe
        self._injector = injector
        self._semantic_revalidator = semantic_revalidator
        self._pixel_guard = InteractionGuard(spine.ledger)
        self._clock = clock

    @classmethod
    def from_windows(
        cls,
        *,
        spine: PhiOSSpine,
    ) -> "GovernedDesktopClickExecutor":
        if os.name != "nt":
            raise DesktopInteractionContractError(
                "Windows desktop interaction executor requires Windows"
            )
        return cls(
            spine=spine,
            frame_provider=WindowsDesktopFrameProvider(),
            input_probe=WindowsOperatorInputProbe(),
            injector=WindowsMouseInjector(),
            semantic_revalidator=(
                SemanticReplayRevalidator.from_system(
                    ledger=spine.ledger
                )
            ),
        )

    def execute(self, payload: dict[str, object]) -> ArtifactResult:
        request = DesktopClickRequest.from_payload(payload)
        attempted_at = _require_timestamp(
            self._clock(),
            "attempted_at",
        )
        before = self._input_probe.snapshot()
        frame_before = self._frame_provider.current_frame(
            observed_at=attempted_at
        )
        if frame_before is None:
            self._held(
                request=request,
                before=before,
                final=before,
                attempted_at=attempted_at,
                reason="foreground_window_unavailable",
            )

        assert frame_before is not None
        if (
            frame_before.process_id != request.process_id
            or frame_before.window_title_sha256
            != request.window_title_sha256
            or not frame_before.foreground
        ):
            self._held(
                request=request,
                before=before,
                final=before,
                attempted_at=attempted_at,
                reason="foreground_window_scope_mismatch",
                frame_before=frame_before,
            )

        resolved = self._resolve_target(
            request=request,
            frame=frame_before,
            before=before,
            attempted_at=attempted_at,
        )

        final = self._input_probe.snapshot()
        final_at = _require_timestamp(
            self._clock(),
            "final_observed_at",
        )
        frame_final = self._frame_provider.current_frame(
            observed_at=final_at
        )
        if frame_final is None:
            self._held(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                reason="foreground_window_lost_before_injection",
                frame_before=frame_before,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
            )

        assert frame_final is not None
        if frame_final.frame_sha256 != frame_before.frame_sha256:
            self._held(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                reason="foreground_frame_changed_before_injection",
                frame_before=frame_before,
                frame_final=frame_final,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
            )
        if (
            final.token != before.token
            or final.pointer_x_px != before.pointer_x_px
            or final.pointer_y_px != before.pointer_y_px
        ):
            self._held(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                reason="operator_input_changed_before_injection",
                frame_before=frame_before,
                frame_final=frame_final,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
            )
        if not (
            frame_final.left_px
            <= resolved.x_px
            < frame_final.left_px + frame_final.width_px
            and frame_final.top_px
            <= resolved.y_px
            < frame_final.top_px + frame_final.height_px
        ):
            self._held(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                reason="resolved_coordinate_outside_final_frame",
                frame_before=frame_before,
                frame_final=frame_final,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
            )

        point_frame = self._frame_provider.frame_at_point(
            x_px=resolved.x_px,
            y_px=resolved.y_px,
            observed_at=final_at,
        )
        if (
            point_frame is None
            or point_frame.process_id != request.process_id
            or point_frame.window_title_sha256
            != request.window_title_sha256
        ):
            self._held(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                reason="unexpected_overlay_at_resolved_target",
                frame_before=frame_before,
                frame_final=frame_final,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
            )

        try:
            injection = self._injector.click(
                x_px=resolved.x_px,
                y_px=resolved.y_px,
            )
        except Exception as exc:
            receipt = self._receipt(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                outcome=DesktopInteractionOutcome.FAILED,
                reason=f"injector_error:{type(exc).__name__}",
                effect_performed=False,
                frame_before=frame_before,
                frame_final=frame_final,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
                inserted_events=0,
            )
            self._ledger.append_desktop_interaction_receipt(receipt)
            raise

        post_at = _require_timestamp(
            self._clock(),
            "post_observed_at",
        )
        frame_after = self._frame_provider.current_frame(
            observed_at=post_at
        )

        if injection.inserted_events == 0:
            receipt = self._receipt(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                outcome=DesktopInteractionOutcome.FAILED,
                reason="injector_inserted_zero_events",
                effect_performed=False,
                frame_before=frame_before,
                frame_final=frame_final,
                frame_after=frame_after,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
                inserted_events=0,
            )
            self._ledger.append_desktop_interaction_receipt(receipt)
            raise RuntimeError(
                "desktop injector inserted zero events"
            )

        if injection.inserted_events != injection.expected_events:
            receipt = self._receipt(
                request=request,
                before=before,
                final=final,
                attempted_at=attempted_at,
                outcome=DesktopInteractionOutcome.OUTCOME_UNKNOWN,
                reason="injector_partial_event_sequence",
                effect_performed=None,
                frame_before=frame_before,
                frame_final=frame_final,
                frame_after=frame_after,
                proof_receipt_sha256=resolved.proof_receipt_sha256,
                resolved=resolved,
                inserted_events=injection.inserted_events,
            )
            self._ledger.append_desktop_interaction_receipt(receipt)
            raise OutcomeUnknownError(
                "desktop click inserted a partial input sequence",
                external_identifiers={
                    "desktop_interaction_receipt_sha256": (
                        receipt.receipt_sha256
                    ),
                    "inserted_events": str(injection.inserted_events),
                    "expected_events": str(injection.expected_events),
                },
            )

        receipt = self._receipt(
            request=request,
            before=before,
            final=final,
            attempted_at=attempted_at,
            outcome=DesktopInteractionOutcome.SUCCEEDED,
            reason="bounded_left_click_inserted",
            effect_performed=True,
            frame_before=frame_before,
            frame_final=frame_final,
            frame_after=frame_after,
            proof_receipt_sha256=resolved.proof_receipt_sha256,
            resolved=resolved,
            inserted_events=injection.inserted_events,
        )
        self._ledger.append_desktop_interaction_receipt(receipt)
        return self._artifact(receipt)

    def _resolve_target(
        self,
        *,
        request: DesktopClickRequest,
        frame: WindowFrame,
        before: OperatorInputSnapshot,
        attempted_at: str,
    ) -> _ResolvedTarget:
        if request.target_mode is DesktopTargetMode.SEMANTIC:
            assert request.semantic_target is not None
            semantic = self._semantic_revalidator.assess(
                target=request.semantic_target,
                expected_process_id=request.process_id,
                expected_window_title_sha256=(
                    request.window_title_sha256
                ),
                frame=frame,
                observed_at=attempted_at,
            )
            if semantic.decision is not SemanticRevalidationDecision.CLEAR:
                self._held(
                    request=request,
                    before=before,
                    final=self._input_probe.snapshot(),
                    attempted_at=attempted_at,
                    reason=(
                        "semantic_revalidation_"
                        + semantic.reason.value.lower()
                    ),
                    frame_before=frame,
                    proof_receipt_sha256=semantic.receipt_sha256,
                )
            assert semantic.resolved_x_px is not None
            assert semantic.resolved_y_px is not None
            return _ResolvedTarget(
                proof_receipt_sha256=semantic.receipt_sha256,
                x_px=semantic.resolved_x_px,
                y_px=semantic.resolved_y_px,
            )

        candidate_x, candidate_y = request.pixel_anchor.resolve(frame)
        point_frame = self._frame_provider.frame_at_point(
            x_px=candidate_x,
            y_px=candidate_y,
            observed_at=attempted_at,
        )
        current = self._input_probe.snapshot()
        overlay = (
            point_frame is None
            or point_frame.process_id != request.process_id
            or point_frame.window_title_sha256
            != request.window_title_sha256
        )
        snapshot = InteractionSnapshot(
            frame=frame,
            pointer_x_px=current.pointer_x_px,
            pointer_y_px=current.pointer_y_px,
            pointer_moved_since_anchor=(
                current.pointer_x_px != before.pointer_x_px
                or current.pointer_y_px != before.pointer_y_px
            ),
            operator_input_detected=(current.token != before.token),
            unexpected_overlay_detected=overlay,
        )
        guard = self._pixel_guard.assess(
            anchor=request.pixel_anchor,
            snapshot=snapshot,
            observed_at=attempted_at,
        )
        if guard.decision is not GuardDecision.CLEAR:
            self._held(
                request=request,
                before=before,
                final=current,
                attempted_at=attempted_at,
                reason="pixel_guard_hold",
                frame_before=frame,
                proof_receipt_sha256=guard.receipt_sha256,
            )
        assert guard.resolved_x_px is not None
        assert guard.resolved_y_px is not None
        return _ResolvedTarget(
            proof_receipt_sha256=guard.receipt_sha256,
            x_px=guard.resolved_x_px,
            y_px=guard.resolved_y_px,
        )

    def _held(
        self,
        *,
        request: DesktopClickRequest,
        before: OperatorInputSnapshot,
        final: OperatorInputSnapshot,
        attempted_at: str,
        reason: str,
        frame_before: WindowFrame | None = None,
        frame_final: WindowFrame | None = None,
        proof_receipt_sha256: str | None = None,
        resolved: _ResolvedTarget | None = None,
    ) -> None:
        receipt = self._receipt(
            request=request,
            before=before,
            final=final,
            attempted_at=attempted_at,
            outcome=DesktopInteractionOutcome.HELD,
            reason=reason,
            effect_performed=False,
            frame_before=frame_before,
            frame_final=frame_final,
            proof_receipt_sha256=proof_receipt_sha256,
            resolved=resolved,
            inserted_events=None,
        )
        self._ledger.append_desktop_interaction_receipt(receipt)
        raise DesktopInteractionHeldError(
            f"desktop interaction held: {reason}"
        )

    def _receipt(
        self,
        *,
        request: DesktopClickRequest,
        before: OperatorInputSnapshot,
        final: OperatorInputSnapshot,
        attempted_at: str,
        outcome: DesktopInteractionOutcome,
        reason: str,
        effect_performed: bool | None,
        frame_before: WindowFrame | None = None,
        frame_final: WindowFrame | None = None,
        frame_after: WindowFrame | None = None,
        proof_receipt_sha256: str | None = None,
        resolved: _ResolvedTarget | None = None,
        inserted_events: int | None = None,
    ) -> DesktopInteractionReceipt:
        return DesktopInteractionReceipt(
            request_sha256=request.request_sha256,
            target_mode=request.target_mode,
            proof_receipt_sha256=proof_receipt_sha256,
            frame_before_sha256=(
                None if frame_before is None else frame_before.frame_sha256
            ),
            frame_final_sha256=(
                None if frame_final is None else frame_final.frame_sha256
            ),
            frame_after_sha256=(
                None if frame_after is None else frame_after.frame_sha256
            ),
            frame_provider_id=self._frame_provider.provider_id,
            input_probe_id=self._input_probe.probe_id,
            injector_id=self._injector.injector_id,
            input_token_before=before.token,
            input_token_final=final.token,
            pointer_before_x_px=before.pointer_x_px,
            pointer_before_y_px=before.pointer_y_px,
            pointer_final_x_px=final.pointer_x_px,
            pointer_final_y_px=final.pointer_y_px,
            resolved_x_px=(
                None if resolved is None else resolved.x_px
            ),
            resolved_y_px=(
                None if resolved is None else resolved.y_px
            ),
            inserted_events=inserted_events,
            outcome=outcome,
            reason=reason,
            attempted_at=attempted_at,
            effect_performed=effect_performed,
        )

    def _artifact(
        self,
        receipt: DesktopInteractionReceipt,
    ) -> ArtifactResult:
        root = (
            self._spine.state_root
            / "artifacts"
            / "desktop-interaction"
        )
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{receipt.receipt_sha256}.json"
        encoded = (
            json.dumps(
                receipt.to_dict(),
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(encoded)
        return ArtifactResult(
            path=path,
            sha256=hashlib.sha256(encoded).hexdigest(),
        )


def install_desktop_click_capability(
    *,
    spine: PhiOSSpine,
    executor: GovernedDesktopClickExecutor,
) -> Capability:
    """Register the bounded desktop click capability and its executor."""

    capability = Capability(
        id=DESKTOP_CLICK_CAPABILITY_ID,
        name="Governed Desktop Click",
        description=(
            "Perform one revalidated bounded desktop left-click."
        ),
        permissions=("ui.interact",),
        effects=("display.control",),
        risk="high",
        version=DESKTOP_CLICK_CAPABILITY_VERSION,
    )
    spine.registry.register(capability)
    spine.executors.register(
        capability.id,
        executor.execute,
        effects=("display.control",),
    )
    return capability


class WindowsDesktopFrameProvider:
    """Read current foreground/root window state without changing the desktop."""

    provider_id = "windows.user32.desktop-frame.v0.18"

    def __init__(self) -> None:
        if os.name != "nt":
            raise DesktopInteractionContractError(
                "WindowsDesktopFrameProvider requires Windows"
            )

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None:
        observed_at = _require_timestamp(
            observed_at,
            "observed_at",
        )
        user32 = self._user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        return self._frame_from_hwnd(
            hwnd=hwnd,
            observed_at=observed_at,
            foreground=True,
        )

    def frame_at_point(
        self,
        *,
        x_px: int,
        y_px: int,
        observed_at: str,
    ) -> WindowFrame | None:
        _require_int(x_px, "x_px")
        _require_int(y_px, "y_px")
        observed_at = _require_timestamp(
            observed_at,
            "observed_at",
        )
        user32 = self._user32()
        hwnd = user32.WindowFromPoint(_POINT(x_px, y_px))
        if not hwnd:
            return None
        root = user32.GetAncestor(hwnd, 2) or hwnd
        foreground = user32.GetForegroundWindow()
        foreground_root = (
            user32.GetAncestor(foreground, 2)
            if foreground
            else None
        )
        return self._frame_from_hwnd(
            hwnd=root,
            observed_at=observed_at,
            foreground=(root == (foreground_root or foreground)),
        )

    @staticmethod
    def _user32():
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise DesktopInteractionContractError(
                "ctypes Windows API loader is unavailable"
            )
        user32 = windll.user32

        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = ctypes.c_void_p

        user32.WindowFromPoint.argtypes = [_POINT]
        user32.WindowFromPoint.restype = ctypes.c_void_p

        user32.GetAncestor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        user32.GetAncestor.restype = ctypes.c_void_p

        user32.GetWindowRect.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_RECT),
        ]
        user32.GetWindowRect.restype = ctypes.c_int

        user32.GetWindowThreadProcessId.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        user32.GetWindowThreadProcessId.restype = ctypes.c_uint32

        user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextLengthW.restype = ctypes.c_int

        user32.GetWindowTextW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        return user32

    def _frame_from_hwnd(
        self,
        *,
        hwnd,
        observed_at: str,
        foreground: bool,
    ) -> WindowFrame | None:
        user32 = self._user32()
        rect = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return None

        process_id = ctypes.c_uint32()
        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(process_id),
        )
        if process_id.value == 0:
            return None

        title_length = max(
            int(user32.GetWindowTextLengthW(hwnd)),
            0,
        )
        title_buffer = ctypes.create_unicode_buffer(
            title_length + 1
        )
        user32.GetWindowTextW(
            hwnd,
            title_buffer,
            title_length + 1,
        )
        title_sha256 = hashlib.sha256(
            title_buffer.value.encode("utf-8")
        ).hexdigest()

        dpi = 96
        get_dpi = getattr(user32, "GetDpiForWindow", None)
        if get_dpi is not None:
            get_dpi.argtypes = [ctypes.c_void_p]
            get_dpi.restype = ctypes.c_uint
            observed_dpi = int(get_dpi(hwnd))
            if observed_dpi > 0:
                dpi = observed_dpi
        scale = max(50, min(500, round(dpi * 100 / 96)))

        return WindowFrame(
            process_id=f"pid:{process_id.value}",
            window_title_sha256=title_sha256,
            left_px=int(rect.left),
            top_px=int(rect.top),
            width_px=width,
            height_px=height,
            display_scale_percent=scale,
            foreground=foreground,
            captured_at=observed_at,
        )


class WindowsOperatorInputProbe:
    """Observe last-user-input token and pointer position."""

    probe_id = "windows.user32.last-input.v0.18"

    def __init__(self) -> None:
        if os.name != "nt":
            raise DesktopInteractionContractError(
                "WindowsOperatorInputProbe requires Windows"
            )

    def snapshot(self) -> OperatorInputSnapshot:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise DesktopInteractionContractError(
                "ctypes Windows API loader is unavailable"
            )
        user32 = windll.user32

        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        user32.GetLastInputInfo.argtypes = [
            ctypes.POINTER(_LASTINPUTINFO),
        ]
        user32.GetLastInputInfo.restype = ctypes.c_int
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            raise DesktopInteractionContractError(
                "GetLastInputInfo failed"
            )

        point = _POINT()
        user32.GetCursorPos.argtypes = [
            ctypes.POINTER(_POINT),
        ]
        user32.GetCursorPos.restype = ctypes.c_int
        if not user32.GetCursorPos(ctypes.byref(point)):
            raise DesktopInteractionContractError(
                "GetCursorPos failed"
            )

        return OperatorInputSnapshot(
            token=int(info.dwTime),
            pointer_x_px=int(point.x),
            pointer_y_px=int(point.y),
        )


class WindowsMouseInjector:
    """Insert one absolute move + left-down + left-up sequence with SendInput."""

    injector_id = "windows.user32.sendinput-left-click.v0.18"

    def __init__(self) -> None:
        if os.name != "nt":
            raise DesktopInteractionContractError(
                "WindowsMouseInjector requires Windows"
            )

    def click(
        self,
        *,
        x_px: int,
        y_px: int,
    ) -> MouseInjectionResult:
        _require_int(x_px, "x_px")
        _require_int(y_px, "y_px")
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise DesktopInteractionContractError(
                "ctypes Windows API loader is unavailable"
            )
        user32 = windll.user32

        left = int(user32.GetSystemMetrics(76))
        top = int(user32.GetSystemMetrics(77))
        width = int(user32.GetSystemMetrics(78))
        height = int(user32.GetSystemMetrics(79))
        if width <= 1 or height <= 1:
            raise DesktopInteractionContractError(
                "virtual desktop geometry is invalid"
            )
        if not (
            left <= x_px < left + width
            and top <= y_px < top + height
        ):
            raise DesktopInteractionContractError(
                "click coordinate is outside virtual desktop"
            )

        normalized_x = round(
            (x_px - left) * 65535 / (width - 1)
        )
        normalized_y = round(
            (y_px - top) * 65535 / (height - 1)
        )

        move_flags = 0x0001 | 0x8000 | 0x4000
        left_down = 0x0002
        left_up = 0x0004
        inputs = (_INPUT * EXPECTED_SENDINPUT_EVENTS)(
            _mouse_input(
                dx=normalized_x,
                dy=normalized_y,
                flags=move_flags,
            ),
            _mouse_input(dx=0, dy=0, flags=left_down),
            _mouse_input(dx=0, dy=0, flags=left_up),
        )
        user32.SendInput.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(_INPUT),
            ctypes.c_int,
        ]
        user32.SendInput.restype = ctypes.c_uint
        inserted = int(
            user32.SendInput(
                EXPECTED_SENDINPUT_EVENTS,
                inputs,
                ctypes.sizeof(_INPUT),
            )
        )
        return MouseInjectionResult(
            inserted_events=inserted,
        )


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint),
        ("dwFlags", ctypes.c_uint),
        ("time", ctypes.c_uint),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.c_uint),
        ("u", _INPUT_UNION),
    ]


def _mouse_input(
    *,
    dx: int,
    dy: int,
    flags: int,
) -> _INPUT:
    item = _INPUT()
    item.type = 0
    item.mi = _MOUSEINPUT(
        dx=dx,
        dy=dy,
        mouseData=0,
        dwFlags=flags,
        time=0,
        dwExtraInfo=0,
    )
    return item
