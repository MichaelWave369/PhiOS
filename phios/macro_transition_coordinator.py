"""Ghost-Walk demonstration transition coordinator for Macro Runtime v0.22.

This host-side layer maintains one fresh pre-action semantic baseline outside
WH_MOUSE_LL, binds it to the next observed click, captures post-action state,
runs v0.20 transition inference, and publishes the existing editable OperatorLog
summary. It never performs desktop input and never grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

from phios.macro_desktop_interaction import WindowsDesktopFrameProvider
from phios.macro_ghostwalk_capture import CaptureStatus
from phios.macro_ghostwalk_listener import GhostWalkListenerOutcome
from phios.macro_interaction_guard import WindowFrame
from phios.macro_operator_log import OperatorLogRevision
from phios.macro_transition_inference import (
    GhostWalkTransitionInferer,
    GhostWalkUiStateSnapshot,
    SnapshotPhase,
    TransitionInferenceReceipt,
)
from phios.macro_uia_state_observer import (
    GhostWalkUiaStateObserver,
    UiaStateObservationOutcome,
)
from phios.spine.ledger import RealityLedger

TRANSITION_BASELINE_SCHEMA_VERSION = "phios.ghostwalk_transition_baseline.v0.22"
TRANSITION_COORDINATOR_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_transition_coordinator_receipt.v0.22"
)
DEFAULT_MAX_BASELINE_AGE_MS = 1500
MAX_BASELINE_AGE_MS = 5000
DEFAULT_POST_ACTION_DELAY_MS = 75
MAX_POST_ACTION_DELAY_MS = 2000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TransitionCoordinatorContractError(ValueError):
    """Raised when transition-coordinator evidence cannot be trusted."""


class TransitionCoordinatorStatus(StrEnum):
    COMPLETED = "COMPLETED"
    HELD = "HELD"
    IGNORED = "IGNORED"


class TransitionCoordinatorReason(StrEnum):
    INFERENCE_RECORDED = "INFERENCE_RECORDED"
    INJECTED_EVENT = "INJECTED_EVENT"
    CAPTURE_NOT_RECORDED = "CAPTURE_NOT_RECORDED"
    NO_BASELINE = "NO_BASELINE"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    BASELINE_TIME_INVALID = "BASELINE_TIME_INVALID"
    BASELINE_STALE = "BASELINE_STALE"
    BASELINE_SCOPE_DRIFT = "BASELINE_SCOPE_DRIFT"
    CLICK_FRAME_UNAVAILABLE = "CLICK_FRAME_UNAVAILABLE"
    AFTER_FRAME_UNAVAILABLE = "AFTER_FRAME_UNAVAILABLE"
    AFTER_STATE_HELD = "AFTER_STATE_HELD"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise TransitionCoordinatorContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise TransitionCoordinatorContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise TransitionCoordinatorContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise TransitionCoordinatorContractError(
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
        raise TransitionCoordinatorContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise TransitionCoordinatorContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise TransitionCoordinatorContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransitionCoordinatorContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise TransitionCoordinatorContractError(
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
        raise TransitionCoordinatorContractError(
            "transition-coordinator payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(
        _require_timestamp(value, "timestamp").replace("Z", "+00:00")
    )


def _stable_frame_body(frame: WindowFrame) -> dict[str, object]:
    return {
        "process_id": frame.process_id,
        "window_title_sha256": frame.window_title_sha256,
        "left_px": frame.left_px,
        "top_px": frame.top_px,
        "width_px": frame.width_px,
        "height_px": frame.height_px,
        "display_scale_percent": frame.display_scale_percent,
        "foreground": frame.foreground,
    }


def _same_frame_scope(first: WindowFrame, second: WindowFrame) -> bool:
    return _stable_frame_body(first) == _stable_frame_body(second)


class TransitionFrameProvider(Protocol):
    provider_id: str

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None: ...


@dataclass(frozen=True, slots=True)
class GhostWalkTransitionBaseline:
    """One single-use pre-action baseline captured outside the mouse hook."""

    session_id: str
    baseline_binding_sha256: str
    frame: WindowFrame
    state_observation_receipt_sha256: str
    state_snapshot: GhostWalkUiStateSnapshot
    captured_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = TRANSITION_BASELINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_BASELINE_SCHEMA_VERSION:
            raise TransitionCoordinatorContractError(
                "unsupported transition baseline schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.baseline_binding_sha256,
            "baseline_binding_sha256",
        )
        _require_sha256(
            self.state_observation_receipt_sha256,
            "state_observation_receipt_sha256",
        )
        _require_timestamp(self.captured_at, "captured_at")
        if self.state_snapshot.session_id != self.session_id:
            raise TransitionCoordinatorContractError(
                "baseline snapshot session differs from baseline"
            )
        if (
            self.state_snapshot.action_observation_sha256
            != self.baseline_binding_sha256
        ):
            raise TransitionCoordinatorContractError(
                "baseline snapshot binding hash mismatch"
            )
        if self.state_snapshot.phase is not SnapshotPhase.BEFORE:
            raise TransitionCoordinatorContractError(
                "baseline snapshot must use BEFORE phase"
            )
        if self.state_snapshot.frame_sha256 != self.frame.frame_sha256:
            raise TransitionCoordinatorContractError(
                "baseline snapshot frame hash mismatch"
            )
        if self.state_snapshot.process_id != self.frame.process_id:
            raise TransitionCoordinatorContractError(
                "baseline process differs from frame"
            )
        if (
            self.state_snapshot.window_title_sha256
            != self.frame.window_title_sha256
        ):
            raise TransitionCoordinatorContractError(
                "baseline title differs from frame"
            )
        if self.state_snapshot.observed_at != self.captured_at:
            raise TransitionCoordinatorContractError(
                "baseline timestamps differ"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise TransitionCoordinatorContractError(
                "GhostWalkTransitionBaseline cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "baseline_binding_sha256": self.baseline_binding_sha256,
            "frame": {
                **self.frame.body_dict(),
                "frame_sha256": self.frame.frame_sha256,
            },
            "state_observation_receipt_sha256": (
                self.state_observation_receipt_sha256
            ),
            "state_snapshot": self.state_snapshot.to_dict(),
            "captured_at": self.captured_at,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def baseline_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["baseline_sha256"] = self.baseline_sha256
        return payload


@dataclass(frozen=True, slots=True)
class TransitionCoordinatorReceipt:
    coordinator_id: str
    session_id: str
    listener_receipt_sha256: str
    pointer_event_sha256: str
    action_observation_sha256: str | None
    baseline_sha256: str | None
    baseline_state_observation_receipt_sha256: str | None
    baseline_age_ms: int | None
    rebound_before_snapshot_sha256: str | None
    after_state_observation_receipt_sha256: str | None
    after_snapshot_sha256: str | None
    inference_receipt_sha256: str | None
    operator_note_revision_sha256: str | None
    status: TransitionCoordinatorStatus
    reason: TransitionCoordinatorReason
    baseline_consumed: bool
    coordinated_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = TRANSITION_COORDINATOR_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != TRANSITION_COORDINATOR_RECEIPT_SCHEMA_VERSION
        ):
            raise TransitionCoordinatorContractError(
                "unsupported transition coordinator receipt schema"
            )
        _require_text(self.coordinator_id, "coordinator_id", maximum=512)
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.listener_receipt_sha256,
            "listener_receipt_sha256",
        )
        _require_sha256(
            self.pointer_event_sha256,
            "pointer_event_sha256",
        )
        for field, value in (
            ("action_observation_sha256", self.action_observation_sha256),
            ("baseline_sha256", self.baseline_sha256),
            (
                "baseline_state_observation_receipt_sha256",
                self.baseline_state_observation_receipt_sha256,
            ),
            (
                "rebound_before_snapshot_sha256",
                self.rebound_before_snapshot_sha256,
            ),
            (
                "after_state_observation_receipt_sha256",
                self.after_state_observation_receipt_sha256,
            ),
            ("after_snapshot_sha256", self.after_snapshot_sha256),
            ("inference_receipt_sha256", self.inference_receipt_sha256),
            (
                "operator_note_revision_sha256",
                self.operator_note_revision_sha256,
            ),
        ):
            if value is not None:
                _require_sha256(value, field)
        if self.baseline_age_ms is not None:
            _require_int(
                self.baseline_age_ms,
                "baseline_age_ms",
                minimum=0,
            )
        _require_timestamp(self.coordinated_at, "coordinated_at")
        if self.status is TransitionCoordinatorStatus.COMPLETED:
            if (
                self.reason
                is not TransitionCoordinatorReason.INFERENCE_RECORDED
                or self.action_observation_sha256 is None
                or self.baseline_sha256 is None
                or self.rebound_before_snapshot_sha256 is None
                or self.after_state_observation_receipt_sha256 is None
                or self.after_snapshot_sha256 is None
                or self.inference_receipt_sha256 is None
                or self.operator_note_revision_sha256 is None
                or not self.baseline_consumed
            ):
                raise TransitionCoordinatorContractError(
                    "COMPLETED coordinator receipt is incomplete"
                )
        if self.status is TransitionCoordinatorStatus.IGNORED:
            if self.reason is not TransitionCoordinatorReason.INJECTED_EVENT:
                raise TransitionCoordinatorContractError(
                    "IGNORED coordinator receipt requires injected event"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise TransitionCoordinatorContractError(
                "TransitionCoordinatorReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "coordinator_id": self.coordinator_id,
            "session_id": self.session_id,
            "listener_receipt_sha256": self.listener_receipt_sha256,
            "pointer_event_sha256": self.pointer_event_sha256,
            "action_observation_sha256": self.action_observation_sha256,
            "baseline_sha256": self.baseline_sha256,
            "baseline_state_observation_receipt_sha256": (
                self.baseline_state_observation_receipt_sha256
            ),
            "baseline_age_ms": self.baseline_age_ms,
            "rebound_before_snapshot_sha256": (
                self.rebound_before_snapshot_sha256
            ),
            "after_state_observation_receipt_sha256": (
                self.after_state_observation_receipt_sha256
            ),
            "after_snapshot_sha256": self.after_snapshot_sha256,
            "inference_receipt_sha256": self.inference_receipt_sha256,
            "operator_note_revision_sha256": (
                self.operator_note_revision_sha256
            ),
            "status": self.status.value,
            "reason": self.reason.value,
            "baseline_consumed": self.baseline_consumed,
            "coordinated_at": self.coordinated_at,
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
class TransitionCoordinationOutcome:
    receipt: TransitionCoordinatorReceipt
    inference: TransitionInferenceReceipt | None
    operator_note: OperatorLogRevision | None


class GhostWalkTransitionCoordinator:
    """Single-use baseline coordinator for real before/action/after learning."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        state_observer: GhostWalkUiaStateObserver,
        frame_provider: TransitionFrameProvider,
        transition_inferer: GhostWalkTransitionInferer,
        coordinator_id: str,
        operator_author_id: str,
        max_baseline_age_ms: int = DEFAULT_MAX_BASELINE_AGE_MS,
        post_action_delay_ms: int = DEFAULT_POST_ACTION_DELAY_MS,
        clock: Callable[[], str] = _utc_now_iso,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise TransitionCoordinatorContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._state_observer = state_observer
        self._frame_provider = frame_provider
        self._transition_inferer = transition_inferer
        self.coordinator_id = _require_text(
            coordinator_id,
            "coordinator_id",
            maximum=512,
        )
        self.operator_author_id = _require_text(
            operator_author_id,
            "operator_author_id",
            maximum=512,
        )
        self.max_baseline_age_ms = _require_int(
            max_baseline_age_ms,
            "max_baseline_age_ms",
            minimum=1,
            maximum=MAX_BASELINE_AGE_MS,
        )
        self.post_action_delay_ms = _require_int(
            post_action_delay_ms,
            "post_action_delay_ms",
            minimum=0,
            maximum=MAX_POST_ACTION_DELAY_MS,
        )
        self._clock = clock
        self._pause = pause
        self._baseline: GhostWalkTransitionBaseline | None = None

    @classmethod
    def from_windows(
        cls,
        *,
        ledger: RealityLedger,
        coordinator_id: str,
        operator_author_id: str,
        max_baseline_age_ms: int = DEFAULT_MAX_BASELINE_AGE_MS,
        post_action_delay_ms: int = DEFAULT_POST_ACTION_DELAY_MS,
    ) -> "GhostWalkTransitionCoordinator":
        frame_provider = WindowsDesktopFrameProvider()
        return cls(
            ledger=ledger,
            state_observer=GhostWalkUiaStateObserver.from_windows(
                ledger=ledger
            ),
            frame_provider=frame_provider,
            transition_inferer=GhostWalkTransitionInferer(ledger),
            coordinator_id=coordinator_id,
            operator_author_id=operator_author_id,
            max_baseline_age_ms=max_baseline_age_ms,
            post_action_delay_ms=post_action_delay_ms,
        )

    @property
    def baseline(self) -> GhostWalkTransitionBaseline | None:
        return self._baseline

    def clear_baseline(self) -> None:
        self._baseline = None

    def refresh_baseline(
        self,
        *,
        session_id: str,
    ) -> GhostWalkTransitionBaseline | None:
        session_id = _require_text(
            session_id,
            "session_id",
            maximum=512,
        )
        observed_at = _require_timestamp(
            self._clock(),
            "baseline_observed_at",
        )
        frame = self._frame_provider.current_frame(
            observed_at=observed_at
        )
        if frame is None or not frame.foreground:
            self._baseline = None
            return None

        baseline_binding_sha256 = _canonical_sha256(
            {
                "schema": "phios.ghostwalk_baseline_binding.v0.22",
                "coordinator_id": self.coordinator_id,
                "session_id": session_id,
                "frame_scope": _stable_frame_body(frame),
                "observed_at": observed_at,
            }
        )
        state = self._state_observer.capture(
            session_id=session_id,
            action_observation_sha256=baseline_binding_sha256,
            phase=SnapshotPhase.BEFORE,
            frame=frame,
            observed_at=observed_at,
        )
        if state.snapshot is None:
            self._baseline = None
            return None

        baseline = GhostWalkTransitionBaseline(
            session_id=session_id,
            baseline_binding_sha256=baseline_binding_sha256,
            frame=frame,
            state_observation_receipt_sha256=(
                state.receipt.receipt_sha256
            ),
            state_snapshot=state.snapshot,
            captured_at=observed_at,
        )
        self._baseline = baseline
        return baseline

    def handle_listener_outcome(
        self,
        outcome: GhostWalkListenerOutcome,
    ) -> TransitionCoordinationOutcome:
        coordinated_at = _require_timestamp(
            self._clock(),
            "coordinated_at",
        )
        baseline = self._baseline
        self._baseline = None
        baseline_consumed = baseline is not None
        if outcome.receipt.injected:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.IGNORED,
                reason=TransitionCoordinatorReason.INJECTED_EVENT,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=baseline_consumed,
            )

        capture = outcome.capture_outcome
        observation = capture.observation
        click_frame = capture.frame
        if (
            outcome.receipt.capture_status is not CaptureStatus.RECORDED
            or observation is None
        ):
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.CAPTURE_NOT_RECORDED,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=baseline_consumed,
            )
        if click_frame is None:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.CLICK_FRAME_UNAVAILABLE,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=baseline_consumed,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )
        if baseline is None:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.NO_BASELINE,
                coordinated_at=coordinated_at,
                baseline=None,
                baseline_consumed=False,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )
        if baseline.session_id != outcome.receipt.session_id:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.SESSION_MISMATCH,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=True,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )

        age_ms = self._baseline_age_ms(
            baseline=baseline,
            click_observed_at=outcome.pointer_event.observed_at,
        )
        if age_ms is None:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.BASELINE_TIME_INVALID,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=True,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )
        if age_ms > self.max_baseline_age_ms:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.BASELINE_STALE,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=True,
                baseline_age_ms=age_ms,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )
        if not _same_frame_scope(baseline.frame, click_frame):
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.BASELINE_SCOPE_DRIFT,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=True,
                baseline_age_ms=age_ms,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
            )

        rebound_before = GhostWalkUiStateSnapshot(
            session_id=baseline.session_id,
            action_observation_sha256=observation.observation_sha256,
            phase=SnapshotPhase.BEFORE,
            process_id=baseline.state_snapshot.process_id,
            window_title_sha256=(
                baseline.state_snapshot.window_title_sha256
            ),
            frame_sha256=baseline.state_snapshot.frame_sha256,
            semantic_targets=baseline.state_snapshot.semantic_targets,
            observed_at=baseline.state_snapshot.observed_at,
        )

        if self.post_action_delay_ms:
            self._pause(self.post_action_delay_ms / 1000.0)
        after_observed_at = _require_timestamp(
            self._clock(),
            "after_observed_at",
        )
        after_frame = self._frame_provider.current_frame(
            observed_at=after_observed_at
        )
        if after_frame is None:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.AFTER_FRAME_UNAVAILABLE,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=True,
                baseline_age_ms=age_ms,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
                rebound_before_snapshot_sha256=(
                    rebound_before.snapshot_sha256
                ),
            )

        after_state = self._state_observer.capture(
            session_id=baseline.session_id,
            action_observation_sha256=observation.observation_sha256,
            phase=SnapshotPhase.AFTER,
            frame=after_frame,
            observed_at=after_observed_at,
        )
        if after_state.snapshot is None:
            return self._finish(
                outcome=outcome,
                status=TransitionCoordinatorStatus.HELD,
                reason=TransitionCoordinatorReason.AFTER_STATE_HELD,
                coordinated_at=coordinated_at,
                baseline=baseline,
                baseline_consumed=True,
                baseline_age_ms=age_ms,
                action_observation_sha256=(
                    observation.observation_sha256
                ),
                rebound_before_snapshot_sha256=(
                    rebound_before.snapshot_sha256
                ),
                after_state=after_state,
            )

        inference = self._transition_inferer.infer(
            before=rebound_before,
            after=after_state.snapshot,
            inferred_at=_require_timestamp(
                self._clock(),
                "inferred_at",
            ),
        )
        note = self._transition_inferer.publish_editable_operator_log(
            receipt=inference,
            note_id=(
                "ghostwalk-transition:"
                f"{observation.observation_sha256}"
            ),
            author_id=self.operator_author_id,
            created_at=_require_timestamp(
                self._clock(),
                "operator_note_created_at",
            ),
        )
        return self._finish(
            outcome=outcome,
            status=TransitionCoordinatorStatus.COMPLETED,
            reason=TransitionCoordinatorReason.INFERENCE_RECORDED,
            coordinated_at=coordinated_at,
            baseline=baseline,
            baseline_consumed=True,
            baseline_age_ms=age_ms,
            action_observation_sha256=observation.observation_sha256,
            rebound_before_snapshot_sha256=(
                rebound_before.snapshot_sha256
            ),
            after_state=after_state,
            inference=inference,
            note=note,
        )

    @staticmethod
    def _baseline_age_ms(
        *,
        baseline: GhostWalkTransitionBaseline,
        click_observed_at: str,
    ) -> int | None:
        delta = _timestamp(click_observed_at) - _timestamp(
            baseline.captured_at
        )
        milliseconds = int(delta.total_seconds() * 1000)
        if milliseconds < 0:
            return None
        return milliseconds

    def _finish(
        self,
        *,
        outcome: GhostWalkListenerOutcome,
        status: TransitionCoordinatorStatus,
        reason: TransitionCoordinatorReason,
        coordinated_at: str,
        baseline: GhostWalkTransitionBaseline | None,
        baseline_consumed: bool,
        action_observation_sha256: str | None = None,
        baseline_age_ms: int | None = None,
        rebound_before_snapshot_sha256: str | None = None,
        after_state: UiaStateObservationOutcome | None = None,
        inference: TransitionInferenceReceipt | None = None,
        note: OperatorLogRevision | None = None,
    ) -> TransitionCoordinationOutcome:
        receipt = TransitionCoordinatorReceipt(
            coordinator_id=self.coordinator_id,
            session_id=outcome.receipt.session_id,
            listener_receipt_sha256=outcome.receipt.receipt_sha256,
            pointer_event_sha256=outcome.pointer_event.event_sha256,
            action_observation_sha256=action_observation_sha256,
            baseline_sha256=(
                None if baseline is None else baseline.baseline_sha256
            ),
            baseline_state_observation_receipt_sha256=(
                None
                if baseline is None
                else baseline.state_observation_receipt_sha256
            ),
            baseline_age_ms=baseline_age_ms,
            rebound_before_snapshot_sha256=(
                rebound_before_snapshot_sha256
            ),
            after_state_observation_receipt_sha256=(
                None
                if after_state is None
                else after_state.receipt.receipt_sha256
            ),
            after_snapshot_sha256=(
                None
                if after_state is None or after_state.snapshot is None
                else after_state.snapshot.snapshot_sha256
            ),
            inference_receipt_sha256=(
                None if inference is None else inference.receipt_sha256
            ),
            operator_note_revision_sha256=(
                None if note is None else note.revision_sha256
            ),
            status=status,
            reason=reason,
            baseline_consumed=baseline_consumed,
            coordinated_at=coordinated_at,
        )
        self._ledger.append_transition_coordinator_receipt(receipt)
        return TransitionCoordinationOutcome(
            receipt=receipt,
            inference=inference,
            operator_note=note,
        )
