"""Ghost-Walk baseline refresh service for Macro Runtime v0.23.

This host-driven service keeps one fresh v0.22 transition baseline armed while
Ghost-Walk is active. It never runs inside WH_MOUSE_LL and never grants
authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

from phios.macro_ghostwalk_listener import GhostWalkListenerOutcome
from phios.macro_interaction_guard import WindowFrame
from phios.macro_transition_coordinator import (
    GhostWalkTransitionBaseline,
    GhostWalkTransitionCoordinator,
    TransitionCoordinationOutcome,
    TransitionFrameProvider,
)
from phios.spine.ledger import RealityLedger

BASELINE_REFRESH_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_baseline_refresh_receipt.v0.23"
)
BASELINE_HEALTH_SCHEMA_VERSION = "phios.ghostwalk_baseline_health.v0.23"
DEFAULT_REFRESH_INTERVAL_MS = 500
MIN_REFRESH_INTERVAL_MS = 50
MAX_REFRESH_INTERVAL_MS = 2500
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BaselineRefreshContractError(ValueError):
    """Raised when baseline-refresh service evidence is malformed."""


class BaselineRefreshStatus(StrEnum):
    DISARMED = "DISARMED"
    FRESH = "FRESH"
    DEGRADED = "DEGRADED"


class BaselineRefreshReason(StrEnum):
    ARMED = "ARMED"
    BASELINE_RETAINED = "BASELINE_RETAINED"
    BASELINE_REFRESHED = "BASELINE_REFRESHED"
    SCOPE_DRIFT_REFRESHED = "SCOPE_DRIFT_REFRESHED"
    FRAME_UNAVAILABLE = "FRAME_UNAVAILABLE"
    BASELINE_CAPTURE_FAILED = "BASELINE_CAPTURE_FAILED"
    POST_ACTION_REARMED = "POST_ACTION_REARMED"
    POST_ACTION_REARM_FAILED = "POST_ACTION_REARM_FAILED"
    DISARMED = "DISARMED"


class BaselineRefreshEventKind(StrEnum):
    ARM = "ARM"
    TICK = "TICK"
    COORDINATION = "COORDINATION"
    DISARM = "DISARM"


class BaselineCoordinator(Protocol):
    coordinator_id: str
    max_baseline_age_ms: int

    @property
    def baseline(self) -> GhostWalkTransitionBaseline | None: ...

    def clear_baseline(self) -> None: ...

    def refresh_baseline(
        self,
        *,
        session_id: str,
    ) -> GhostWalkTransitionBaseline | None: ...

    def handle_listener_outcome(
        self,
        outcome: GhostWalkListenerOutcome,
    ) -> TransitionCoordinationOutcome: ...


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise BaselineRefreshContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise BaselineRefreshContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise BaselineRefreshContractError(
            f"{field} contains control characters"
        )
    return value


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BaselineRefreshContractError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise BaselineRefreshContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise BaselineRefreshContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise BaselineRefreshContractError(f"{field} must be Boolean")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise BaselineRefreshContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BaselineRefreshContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise BaselineRefreshContractError(
            f"{field} must include a timezone"
        )
    return text


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(
        _require_timestamp(value, "timestamp").replace("Z", "+00:00")
    )


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
        raise BaselineRefreshContractError(
            "baseline-refresh payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _scope_body(frame: WindowFrame) -> dict[str, object]:
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


def _same_scope(first: WindowFrame, second: WindowFrame) -> bool:
    return _scope_body(first) == _scope_body(second)


def _age_ms(
    *,
    captured_at: str,
    observed_at: str,
) -> int | None:
    delta = _timestamp(observed_at) - _timestamp(captured_at)
    milliseconds = int(delta.total_seconds() * 1000)
    if milliseconds < 0:
        return None
    return milliseconds


@dataclass(frozen=True, slots=True)
class BaselineHealthSnapshot:
    service_id: str
    armed: bool
    session_id: str | None
    baseline_sha256: str | None
    baseline_age_ms: int | None
    refresh_interval_ms: int
    max_baseline_age_ms: int
    refresh_due: bool
    observed_at: str
    schema_version: str = BASELINE_HEALTH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BASELINE_HEALTH_SCHEMA_VERSION:
            raise BaselineRefreshContractError(
                "unsupported baseline health schema"
            )
        _require_text(self.service_id, "service_id", maximum=512)
        if self.session_id is not None:
            _require_text(self.session_id, "session_id", maximum=512)
        if self.baseline_sha256 is not None:
            _require_sha256(self.baseline_sha256, "baseline_sha256")
        if self.baseline_age_ms is not None:
            _require_int(
                self.baseline_age_ms,
                "baseline_age_ms",
                minimum=0,
            )
        _require_int(
            self.refresh_interval_ms,
            "refresh_interval_ms",
            minimum=MIN_REFRESH_INTERVAL_MS,
            maximum=MAX_REFRESH_INTERVAL_MS,
        )
        _require_int(
            self.max_baseline_age_ms,
            "max_baseline_age_ms",
            minimum=1,
        )
        _require_timestamp(self.observed_at, "observed_at")
        if not self.armed and (
            self.session_id is not None
            or self.baseline_sha256 is not None
            or self.baseline_age_ms is not None
            or self.refresh_due
        ):
            raise BaselineRefreshContractError(
                "disarmed health cannot claim active baseline state"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_id": self.service_id,
            "armed": self.armed,
            "session_id": self.session_id,
            "baseline_sha256": self.baseline_sha256,
            "baseline_age_ms": self.baseline_age_ms,
            "refresh_interval_ms": self.refresh_interval_ms,
            "max_baseline_age_ms": self.max_baseline_age_ms,
            "refresh_due": self.refresh_due,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True)
class BaselineRefreshReceipt:
    service_id: str
    sequence: int
    event_kind: BaselineRefreshEventKind
    session_id: str | None
    status: BaselineRefreshStatus
    reason: BaselineRefreshReason
    observed_at: str
    current_frame_sha256: str | None
    baseline_sha256: str | None
    prior_baseline_sha256: str | None
    baseline_age_ms: int | None
    refreshed: bool
    invalidated: bool
    transition_coordinator_receipt_sha256: str | None = None
    previous_receipt_sha256: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = BASELINE_REFRESH_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BASELINE_REFRESH_RECEIPT_SCHEMA_VERSION:
            raise BaselineRefreshContractError(
                "unsupported baseline refresh receipt schema"
            )
        _require_text(self.service_id, "service_id", maximum=512)
        _require_int(self.sequence, "sequence", minimum=0)
        if self.session_id is not None:
            _require_text(self.session_id, "session_id", maximum=512)
        _require_timestamp(self.observed_at, "observed_at")
        for field, value in (
            ("current_frame_sha256", self.current_frame_sha256),
            ("baseline_sha256", self.baseline_sha256),
            ("prior_baseline_sha256", self.prior_baseline_sha256),
            (
                "transition_coordinator_receipt_sha256",
                self.transition_coordinator_receipt_sha256,
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
        _require_bool(self.refreshed, "refreshed")
        _require_bool(self.invalidated, "invalidated")
        if self.sequence == 0:
            if self.previous_receipt_sha256 is not None:
                raise BaselineRefreshContractError(
                    "first refresh receipt cannot reference prior history"
                )
        else:
            if self.previous_receipt_sha256 is None:
                raise BaselineRefreshContractError(
                    "later refresh receipt requires prior receipt hash"
                )
            _require_sha256(
                self.previous_receipt_sha256,
                "previous_receipt_sha256",
            )
        if self.status is BaselineRefreshStatus.DISARMED:
            if self.session_id is not None or self.baseline_sha256 is not None:
                raise BaselineRefreshContractError(
                    "DISARMED receipt cannot claim active session/baseline"
                )
        if self.status is BaselineRefreshStatus.FRESH:
            if self.session_id is None or self.baseline_sha256 is None:
                raise BaselineRefreshContractError(
                    "FRESH receipt requires session and baseline"
                )
        if self.reason is BaselineRefreshReason.BASELINE_RETAINED:
            if self.refreshed or self.invalidated:
                raise BaselineRefreshContractError(
                    "retained baseline cannot be refreshed/invalidated"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise BaselineRefreshContractError(
                "BaselineRefreshReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_id": self.service_id,
            "sequence": self.sequence,
            "event_kind": self.event_kind.value,
            "session_id": self.session_id,
            "status": self.status.value,
            "reason": self.reason.value,
            "observed_at": self.observed_at,
            "current_frame_sha256": self.current_frame_sha256,
            "baseline_sha256": self.baseline_sha256,
            "prior_baseline_sha256": self.prior_baseline_sha256,
            "baseline_age_ms": self.baseline_age_ms,
            "refreshed": self.refreshed,
            "invalidated": self.invalidated,
            "transition_coordinator_receipt_sha256": (
                self.transition_coordinator_receipt_sha256
            ),
            "previous_receipt_sha256": self.previous_receipt_sha256,
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
class BaselineServiceTickOutcome:
    receipt: BaselineRefreshReceipt
    health: BaselineHealthSnapshot
    baseline: GhostWalkTransitionBaseline | None


@dataclass(frozen=True, slots=True)
class BaselineServiceCoordinationOutcome:
    coordination: TransitionCoordinationOutcome
    service_receipt: BaselineRefreshReceipt
    health: BaselineHealthSnapshot
    baseline: GhostWalkTransitionBaseline | None


class GhostWalkBaselineRefreshService:
    """Serialize baseline refresh and click coordination across long runs."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        coordinator: BaselineCoordinator,
        frame_provider: TransitionFrameProvider,
        service_id: str,
        refresh_interval_ms: int = DEFAULT_REFRESH_INTERVAL_MS,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise BaselineRefreshContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._coordinator = coordinator
        self._frame_provider = frame_provider
        self.service_id = _require_text(
            service_id,
            "service_id",
            maximum=512,
        )
        self.refresh_interval_ms = _require_int(
            refresh_interval_ms,
            "refresh_interval_ms",
            minimum=MIN_REFRESH_INTERVAL_MS,
            maximum=MAX_REFRESH_INTERVAL_MS,
        )
        if self.refresh_interval_ms >= coordinator.max_baseline_age_ms:
            raise BaselineRefreshContractError(
                "refresh interval must be less than coordinator max baseline age"
            )
        self._clock = clock
        self._armed_session_id: str | None = None
        self._lock = threading.RLock()

    @classmethod
    def from_windows(
        cls,
        *,
        ledger: RealityLedger,
        service_id: str,
        coordinator_id: str,
        operator_author_id: str,
        refresh_interval_ms: int = DEFAULT_REFRESH_INTERVAL_MS,
    ) -> "GhostWalkBaselineRefreshService":
        from phios.macro_desktop_interaction import WindowsDesktopFrameProvider

        frame_provider = WindowsDesktopFrameProvider()
        coordinator = GhostWalkTransitionCoordinator.from_windows(
            ledger=ledger,
            coordinator_id=coordinator_id,
            operator_author_id=operator_author_id,
        )
        return cls(
            ledger=ledger,
            coordinator=coordinator,
            frame_provider=frame_provider,
            service_id=service_id,
            refresh_interval_ms=refresh_interval_ms,
        )

    @property
    def armed_session_id(self) -> str | None:
        return self._armed_session_id

    def arm(self, *, session_id: str) -> BaselineServiceTickOutcome:
        with self._lock:
            self._armed_session_id = _require_text(
                session_id,
                "session_id",
                maximum=512,
            )
            self._coordinator.clear_baseline()
            return self._refresh(
                event_kind=BaselineRefreshEventKind.ARM,
                reason=BaselineRefreshReason.ARMED,
                invalidated=False,
            )

    def disarm(self) -> BaselineServiceTickOutcome:
        with self._lock:
            observed_at = _require_timestamp(
                self._clock(),
                "disarmed_at",
            )
            prior = self._coordinator.baseline
            self._coordinator.clear_baseline()
            self._armed_session_id = None
            receipt = self._append_receipt(
                event_kind=BaselineRefreshEventKind.DISARM,
                session_id=None,
                status=BaselineRefreshStatus.DISARMED,
                reason=BaselineRefreshReason.DISARMED,
                observed_at=observed_at,
                current_frame_sha256=None,
                baseline=None,
                prior_baseline=prior,
                baseline_age_ms=None,
                refreshed=False,
                invalidated=prior is not None,
                coordinator_receipt_sha256=None,
            )
            health = self.health(observed_at=observed_at)
            return BaselineServiceTickOutcome(
                receipt=receipt,
                health=health,
                baseline=None,
            )

    def tick(self) -> BaselineServiceTickOutcome:
        with self._lock:
            if self._armed_session_id is None:
                observed_at = _require_timestamp(
                    self._clock(),
                    "tick_observed_at",
                )
                receipt = self._append_receipt(
                    event_kind=BaselineRefreshEventKind.TICK,
                    session_id=None,
                    status=BaselineRefreshStatus.DISARMED,
                    reason=BaselineRefreshReason.DISARMED,
                    observed_at=observed_at,
                    current_frame_sha256=None,
                    baseline=None,
                    prior_baseline=None,
                    baseline_age_ms=None,
                    refreshed=False,
                    invalidated=False,
                    coordinator_receipt_sha256=None,
                )
                return BaselineServiceTickOutcome(
                    receipt=receipt,
                    health=self.health(observed_at=observed_at),
                    baseline=None,
                )

            observed_at = _require_timestamp(
                self._clock(),
                "tick_observed_at",
            )
            frame = self._frame_provider.current_frame(
                observed_at=observed_at
            )
            baseline = self._coordinator.baseline

            if frame is None or not frame.foreground:
                self._coordinator.clear_baseline()
                receipt = self._append_receipt(
                    event_kind=BaselineRefreshEventKind.TICK,
                    session_id=self._armed_session_id,
                    status=BaselineRefreshStatus.DEGRADED,
                    reason=BaselineRefreshReason.FRAME_UNAVAILABLE,
                    observed_at=observed_at,
                    current_frame_sha256=(
                        None if frame is None else frame.frame_sha256
                    ),
                    baseline=None,
                    prior_baseline=baseline,
                    baseline_age_ms=(
                        None
                        if baseline is None
                        else _age_ms(
                            captured_at=baseline.captured_at,
                            observed_at=observed_at,
                        )
                    ),
                    refreshed=False,
                    invalidated=baseline is not None,
                    coordinator_receipt_sha256=None,
                )
                return BaselineServiceTickOutcome(
                    receipt=receipt,
                    health=self.health(observed_at=observed_at),
                    baseline=None,
                )

            if baseline is None:
                return self._refresh(
                    event_kind=BaselineRefreshEventKind.TICK,
                    reason=BaselineRefreshReason.BASELINE_REFRESHED,
                    invalidated=False,
                    current_frame_sha256=frame.frame_sha256,
                )

            age = _age_ms(
                captured_at=baseline.captured_at,
                observed_at=observed_at,
            )
            if (
                baseline.session_id != self._armed_session_id
                or not _same_scope(baseline.frame, frame)
            ):
                self._coordinator.clear_baseline()
                return self._refresh(
                    event_kind=BaselineRefreshEventKind.TICK,
                    reason=BaselineRefreshReason.SCOPE_DRIFT_REFRESHED,
                    invalidated=True,
                    prior_baseline=baseline,
                    current_frame_sha256=frame.frame_sha256,
                )

            if age is None or age >= self.refresh_interval_ms:
                return self._refresh(
                    event_kind=BaselineRefreshEventKind.TICK,
                    reason=BaselineRefreshReason.BASELINE_REFRESHED,
                    invalidated=age is None,
                    prior_baseline=baseline,
                    current_frame_sha256=frame.frame_sha256,
                )

            receipt = self._append_receipt(
                event_kind=BaselineRefreshEventKind.TICK,
                session_id=self._armed_session_id,
                status=BaselineRefreshStatus.FRESH,
                reason=BaselineRefreshReason.BASELINE_RETAINED,
                observed_at=observed_at,
                current_frame_sha256=frame.frame_sha256,
                baseline=baseline,
                prior_baseline=baseline,
                baseline_age_ms=age,
                refreshed=False,
                invalidated=False,
                coordinator_receipt_sha256=None,
            )
            return BaselineServiceTickOutcome(
                receipt=receipt,
                health=self.health(observed_at=observed_at),
                baseline=baseline,
            )

    def handle_listener_outcome(
        self,
        outcome: GhostWalkListenerOutcome,
    ) -> BaselineServiceCoordinationOutcome:
        with self._lock:
            coordination = self._coordinator.handle_listener_outcome(
                outcome
            )
            prior = self._coordinator.baseline
            session_id = self._armed_session_id
            if session_id is None:
                observed_at = _require_timestamp(
                    self._clock(),
                    "post_action_observed_at",
                )
                receipt = self._append_receipt(
                    event_kind=BaselineRefreshEventKind.COORDINATION,
                    session_id=None,
                    status=BaselineRefreshStatus.DISARMED,
                    reason=BaselineRefreshReason.DISARMED,
                    observed_at=observed_at,
                    current_frame_sha256=None,
                    baseline=None,
                    prior_baseline=prior,
                    baseline_age_ms=None,
                    refreshed=False,
                    invalidated=False,
                    coordinator_receipt_sha256=(
                        coordination.receipt.receipt_sha256
                    ),
                )
                return BaselineServiceCoordinationOutcome(
                    coordination=coordination,
                    service_receipt=receipt,
                    health=self.health(observed_at=observed_at),
                    baseline=None,
                )

            refreshed = self._coordinator.refresh_baseline(
                session_id=session_id
            )
            observed_at = _require_timestamp(
                self._clock(),
                "post_action_observed_at",
            )
            if refreshed is None:
                receipt = self._append_receipt(
                    event_kind=BaselineRefreshEventKind.COORDINATION,
                    session_id=session_id,
                    status=BaselineRefreshStatus.DEGRADED,
                    reason=BaselineRefreshReason.POST_ACTION_REARM_FAILED,
                    observed_at=observed_at,
                    current_frame_sha256=None,
                    baseline=None,
                    prior_baseline=prior,
                    baseline_age_ms=None,
                    refreshed=False,
                    invalidated=True,
                    coordinator_receipt_sha256=(
                        coordination.receipt.receipt_sha256
                    ),
                )
            else:
                receipt = self._append_receipt(
                    event_kind=BaselineRefreshEventKind.COORDINATION,
                    session_id=session_id,
                    status=BaselineRefreshStatus.FRESH,
                    reason=BaselineRefreshReason.POST_ACTION_REARMED,
                    observed_at=observed_at,
                    current_frame_sha256=refreshed.frame.frame_sha256,
                    baseline=refreshed,
                    prior_baseline=prior,
                    baseline_age_ms=0,
                    refreshed=True,
                    invalidated=True,
                    coordinator_receipt_sha256=(
                        coordination.receipt.receipt_sha256
                    ),
                )
            return BaselineServiceCoordinationOutcome(
                coordination=coordination,
                service_receipt=receipt,
                health=self.health(observed_at=observed_at),
                baseline=refreshed,
            )

    def health(self, *, observed_at: str) -> BaselineHealthSnapshot:
        observed_at = _require_timestamp(observed_at, "observed_at")
        session_id = self._armed_session_id
        baseline = self._coordinator.baseline
        if session_id is None:
            return BaselineHealthSnapshot(
                service_id=self.service_id,
                armed=False,
                session_id=None,
                baseline_sha256=None,
                baseline_age_ms=None,
                refresh_interval_ms=self.refresh_interval_ms,
                max_baseline_age_ms=self._coordinator.max_baseline_age_ms,
                refresh_due=False,
                observed_at=observed_at,
            )

        age = (
            None
            if baseline is None
            else _age_ms(
                captured_at=baseline.captured_at,
                observed_at=observed_at,
            )
        )
        return BaselineHealthSnapshot(
            service_id=self.service_id,
            armed=True,
            session_id=session_id,
            baseline_sha256=(
                None if baseline is None else baseline.baseline_sha256
            ),
            baseline_age_ms=age,
            refresh_interval_ms=self.refresh_interval_ms,
            max_baseline_age_ms=self._coordinator.max_baseline_age_ms,
            refresh_due=(
                baseline is None
                or age is None
                or age >= self.refresh_interval_ms
            ),
            observed_at=observed_at,
        )

    def _refresh(
        self,
        *,
        event_kind: BaselineRefreshEventKind,
        reason: BaselineRefreshReason,
        invalidated: bool,
        prior_baseline: GhostWalkTransitionBaseline | None = None,
        current_frame_sha256: str | None = None,
    ) -> BaselineServiceTickOutcome:
        session_id = self._armed_session_id
        if session_id is None:
            raise BaselineRefreshContractError(
                "cannot refresh while service is disarmed"
            )
        prior = (
            self._coordinator.baseline
            if prior_baseline is None
            else prior_baseline
        )
        refreshed = self._coordinator.refresh_baseline(
            session_id=session_id
        )
        observed_at = _require_timestamp(
            self._clock(),
            "refresh_observed_at",
        )
        if refreshed is None:
            receipt = self._append_receipt(
                event_kind=event_kind,
                session_id=session_id,
                status=BaselineRefreshStatus.DEGRADED,
                reason=BaselineRefreshReason.BASELINE_CAPTURE_FAILED,
                observed_at=observed_at,
                current_frame_sha256=current_frame_sha256,
                baseline=None,
                prior_baseline=prior,
                baseline_age_ms=None,
                refreshed=False,
                invalidated=invalidated or prior is not None,
                coordinator_receipt_sha256=None,
            )
            return BaselineServiceTickOutcome(
                receipt=receipt,
                health=self.health(observed_at=observed_at),
                baseline=None,
            )

        receipt = self._append_receipt(
            event_kind=event_kind,
            session_id=session_id,
            status=BaselineRefreshStatus.FRESH,
            reason=reason,
            observed_at=observed_at,
            current_frame_sha256=(
                refreshed.frame.frame_sha256
                if current_frame_sha256 is None
                else current_frame_sha256
            ),
            baseline=refreshed,
            prior_baseline=prior,
            baseline_age_ms=0,
            refreshed=True,
            invalidated=invalidated,
            coordinator_receipt_sha256=None,
        )
        return BaselineServiceTickOutcome(
            receipt=receipt,
            health=self.health(observed_at=observed_at),
            baseline=refreshed,
        )

    def _append_receipt(
        self,
        *,
        event_kind: BaselineRefreshEventKind,
        session_id: str | None,
        status: BaselineRefreshStatus,
        reason: BaselineRefreshReason,
        observed_at: str,
        current_frame_sha256: str | None,
        baseline: GhostWalkTransitionBaseline | None,
        prior_baseline: GhostWalkTransitionBaseline | None,
        baseline_age_ms: int | None,
        refreshed: bool,
        invalidated: bool,
        coordinator_receipt_sha256: str | None,
    ) -> BaselineRefreshReceipt:
        sequence = self._ledger.next_baseline_refresh_sequence(
            service_id=self.service_id
        )
        previous_sha = self._ledger.latest_baseline_refresh_receipt_sha256(
            service_id=self.service_id
        )
        receipt = BaselineRefreshReceipt(
            service_id=self.service_id,
            sequence=sequence,
            event_kind=event_kind,
            session_id=session_id,
            status=status,
            reason=reason,
            observed_at=observed_at,
            current_frame_sha256=current_frame_sha256,
            baseline_sha256=(
                None if baseline is None else baseline.baseline_sha256
            ),
            prior_baseline_sha256=(
                None
                if prior_baseline is None
                else prior_baseline.baseline_sha256
            ),
            baseline_age_ms=baseline_age_ms,
            refreshed=refreshed,
            invalidated=invalidated,
            transition_coordinator_receipt_sha256=(
                coordinator_receipt_sha256
            ),
            previous_receipt_sha256=previous_sha,
        )
        self._ledger.append_baseline_refresh_receipt(receipt)
        return receipt
