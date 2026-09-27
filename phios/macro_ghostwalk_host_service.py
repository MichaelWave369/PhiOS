"""Long-running Ghost-Walk host service for Macro Runtime v0.24.

The host owns listener lifecycle, bounded baseline-service ticking, outcome
delivery, clean shutdown, health reporting, and restart evidence. Persisted
history may recover lifecycle context, but no baseline is ever resurrected after
process restart.
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

from phios.macro_baseline_refresh_service import (
    BaselineHealthSnapshot,
    BaselineRefreshStatus,
    BaselineServiceCoordinationOutcome,
    BaselineServiceTickOutcome,
    GhostWalkBaselineRefreshService,
)
from phios.macro_ghostwalk_listener import GhostWalkListenerOutcome
from phios.spine.ledger import RealityLedger

GHOSTWALK_HOST_RECEIPT_SCHEMA_VERSION = "phios.ghostwalk_host_receipt.v0.24"
GHOSTWALK_HOST_HEALTH_SCHEMA_VERSION = "phios.ghostwalk_host_health.v0.24"
DEFAULT_HOST_TICK_INTERVAL_MS = 100
MIN_HOST_TICK_INTERVAL_MS = 25
MAX_HOST_TICK_INTERVAL_MS = 1000
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
MAX_SHUTDOWN_TIMEOUT_SECONDS = 30.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkHostContractError(ValueError):
    """Raised when Ghost-Walk host state or evidence is malformed."""


class GhostWalkHostStatus(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class GhostWalkHostEventKind(StrEnum):
    RECOVERY = "RECOVERY"
    START = "START"
    TICK = "TICK"
    LISTENER = "LISTENER"
    STOP = "STOP"
    FAILURE = "FAILURE"


class GhostWalkHostReason(StrEnum):
    PRIOR_RUN_ABANDONED = "PRIOR_RUN_ABANDONED"
    STARTED_FRESH = "STARTED_FRESH"
    STARTED_DEGRADED = "STARTED_DEGRADED"
    TICK_FRESH = "TICK_FRESH"
    TICK_DEGRADED = "TICK_DEGRADED"
    LISTENER_OUTCOME_HANDLED = "LISTENER_OUTCOME_HANDLED"
    LISTENER_FAILED = "LISTENER_FAILED"
    LISTENER_STOPPED_UNEXPECTEDLY = "LISTENER_STOPPED_UNEXPECTEDLY"
    TICK_FAILED = "TICK_FAILED"
    STOP_REQUESTED = "STOP_REQUESTED"
    STOPPED_CLEAN = "STOPPED_CLEAN"
    SHUTDOWN_INCOMPLETE = "SHUTDOWN_INCOMPLETE"


class HostListener(Protocol):
    def run(self, *, session_id: str) -> None: ...

    def stop(self) -> None: ...


class HostBaselineService(Protocol):
    refresh_interval_ms: int

    @property
    def armed_session_id(self) -> str | None: ...

    def arm(self, *, session_id: str) -> BaselineServiceTickOutcome: ...

    def tick(self) -> BaselineServiceTickOutcome: ...

    def handle_listener_outcome(
        self,
        outcome: GhostWalkListenerOutcome,
    ) -> BaselineServiceCoordinationOutcome: ...

    def disarm(self) -> BaselineServiceTickOutcome: ...

    def health(self, *, observed_at: str) -> BaselineHealthSnapshot: ...


ListenerFactory = Callable[
    [Callable[[GhostWalkListenerOutcome], object]],
    HostListener,
]


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkHostContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkHostContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkHostContractError(
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
        raise GhostWalkHostContractError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise GhostWalkHostContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise GhostWalkHostContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkHostContractError(f"{field} must be Boolean")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkHostContractError(
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
        raise GhostWalkHostContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkHostContractError(
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
        raise GhostWalkHostContractError(
            "Ghost-Walk host payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class GhostWalkHostReceipt:
    host_id: str
    sequence: int
    run_generation: int
    event_kind: GhostWalkHostEventKind
    session_id: str | None
    status: GhostWalkHostStatus
    reason: GhostWalkHostReason
    observed_at: str
    baseline_service_receipt_sha256: str | None
    transition_coordinator_receipt_sha256: str | None
    listener_receipt_sha256: str | None
    baseline_sha256: str | None
    baseline_age_ms: int | None
    listener_alive: bool
    tick_alive: bool
    recovered_prior_run: bool
    error_type: str | None = None
    previous_receipt_sha256: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_HOST_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_HOST_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkHostContractError(
                "unsupported Ghost-Walk host receipt schema"
            )
        _require_text(self.host_id, "host_id", maximum=512)
        _require_int(self.sequence, "sequence", minimum=0)
        _require_int(self.run_generation, "run_generation", minimum=0)
        if self.session_id is not None:
            _require_text(self.session_id, "session_id", maximum=512)
        _require_timestamp(self.observed_at, "observed_at")
        for field, value in (
            (
                "baseline_service_receipt_sha256",
                self.baseline_service_receipt_sha256,
            ),
            (
                "transition_coordinator_receipt_sha256",
                self.transition_coordinator_receipt_sha256,
            ),
            ("listener_receipt_sha256", self.listener_receipt_sha256),
            ("baseline_sha256", self.baseline_sha256),
        ):
            if value is not None:
                _require_sha256(value, field)
        if self.baseline_age_ms is not None:
            _require_int(
                self.baseline_age_ms,
                "baseline_age_ms",
                minimum=0,
            )
        _require_bool(self.listener_alive, "listener_alive")
        _require_bool(self.tick_alive, "tick_alive")
        _require_bool(self.recovered_prior_run, "recovered_prior_run")
        if self.error_type is not None:
            _require_text(self.error_type, "error_type", maximum=256)
        if self.sequence == 0:
            if self.previous_receipt_sha256 is not None:
                raise GhostWalkHostContractError(
                    "first host receipt cannot reference prior history"
                )
        else:
            if self.previous_receipt_sha256 is None:
                raise GhostWalkHostContractError(
                    "later host receipt requires previous receipt hash"
                )
            _require_sha256(
                self.previous_receipt_sha256,
                "previous_receipt_sha256",
            )
        if self.event_kind is GhostWalkHostEventKind.RECOVERY:
            if (
                self.reason
                is not GhostWalkHostReason.PRIOR_RUN_ABANDONED
                or not self.recovered_prior_run
            ):
                raise GhostWalkHostContractError(
                    "RECOVERY receipt must identify abandoned prior run"
                )
        if self.status is GhostWalkHostStatus.STOPPED:
            if self.listener_alive or self.tick_alive:
                raise GhostWalkHostContractError(
                    "STOPPED host cannot claim live worker threads"
                )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkHostContractError(
                "GhostWalkHostReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "host_id": self.host_id,
            "sequence": self.sequence,
            "run_generation": self.run_generation,
            "event_kind": self.event_kind.value,
            "session_id": self.session_id,
            "status": self.status.value,
            "reason": self.reason.value,
            "observed_at": self.observed_at,
            "baseline_service_receipt_sha256": (
                self.baseline_service_receipt_sha256
            ),
            "transition_coordinator_receipt_sha256": (
                self.transition_coordinator_receipt_sha256
            ),
            "listener_receipt_sha256": self.listener_receipt_sha256,
            "baseline_sha256": self.baseline_sha256,
            "baseline_age_ms": self.baseline_age_ms,
            "listener_alive": self.listener_alive,
            "tick_alive": self.tick_alive,
            "recovered_prior_run": self.recovered_prior_run,
            "error_type": self.error_type,
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

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "GhostWalkHostReceipt":
        claimed = _require_sha256(
            payload.get("receipt_sha256"),
            "receipt_sha256",
        )
        try:
            event_kind = GhostWalkHostEventKind(
                _require_text(payload.get("event_kind"), "event_kind")
            )
            status = GhostWalkHostStatus(
                _require_text(payload.get("status"), "status")
            )
            reason = GhostWalkHostReason(
                _require_text(payload.get("reason"), "reason")
            )
        except ValueError as exc:
            raise GhostWalkHostContractError(
                "unsupported Ghost-Walk host enum value"
            ) from exc

        receipt = cls(
            host_id=_require_text(payload.get("host_id"), "host_id"),
            sequence=_require_int(payload.get("sequence"), "sequence", minimum=0),
            run_generation=_require_int(
                payload.get("run_generation"),
                "run_generation",
                minimum=0,
            ),
            event_kind=event_kind,
            session_id=(
                None
                if payload.get("session_id") is None
                else _require_text(payload.get("session_id"), "session_id")
            ),
            status=status,
            reason=reason,
            observed_at=_require_timestamp(
                payload.get("observed_at"),
                "observed_at",
            ),
            baseline_service_receipt_sha256=_optional_sha256(
                payload.get("baseline_service_receipt_sha256"),
                "baseline_service_receipt_sha256",
            ),
            transition_coordinator_receipt_sha256=_optional_sha256(
                payload.get("transition_coordinator_receipt_sha256"),
                "transition_coordinator_receipt_sha256",
            ),
            listener_receipt_sha256=_optional_sha256(
                payload.get("listener_receipt_sha256"),
                "listener_receipt_sha256",
            ),
            baseline_sha256=_optional_sha256(
                payload.get("baseline_sha256"),
                "baseline_sha256",
            ),
            baseline_age_ms=(
                None
                if payload.get("baseline_age_ms") is None
                else _require_int(
                    payload.get("baseline_age_ms"),
                    "baseline_age_ms",
                    minimum=0,
                )
            ),
            listener_alive=_require_bool(
                payload.get("listener_alive"),
                "listener_alive",
            ),
            tick_alive=_require_bool(
                payload.get("tick_alive"),
                "tick_alive",
            ),
            recovered_prior_run=_require_bool(
                payload.get("recovered_prior_run"),
                "recovered_prior_run",
            ),
            error_type=(
                None
                if payload.get("error_type") is None
                else _require_text(payload.get("error_type"), "error_type")
            ),
            previous_receipt_sha256=_optional_sha256(
                payload.get("previous_receipt_sha256"),
                "previous_receipt_sha256",
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
            ),
        )
        if receipt.receipt_sha256 != claimed:
            raise GhostWalkHostContractError(
                "Ghost-Walk host receipt hash mismatch"
            )
        return receipt


@dataclass(frozen=True, slots=True)
class GhostWalkHostHealth:
    host_id: str
    status: GhostWalkHostStatus
    run_generation: int
    session_id: str | None
    listener_alive: bool
    tick_alive: bool
    baseline_armed: bool
    baseline_sha256: str | None
    baseline_age_ms: int | None
    baseline_refresh_due: bool
    error_type: str | None
    observed_at: str
    schema_version: str = GHOSTWALK_HOST_HEALTH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_HOST_HEALTH_SCHEMA_VERSION:
            raise GhostWalkHostContractError(
                "unsupported Ghost-Walk host health schema"
            )
        _require_text(self.host_id, "host_id", maximum=512)
        _require_int(self.run_generation, "run_generation", minimum=0)
        if self.session_id is not None:
            _require_text(self.session_id, "session_id", maximum=512)
        _require_bool(self.listener_alive, "listener_alive")
        _require_bool(self.tick_alive, "tick_alive")
        _require_bool(self.baseline_armed, "baseline_armed")
        if self.baseline_sha256 is not None:
            _require_sha256(self.baseline_sha256, "baseline_sha256")
        if self.baseline_age_ms is not None:
            _require_int(
                self.baseline_age_ms,
                "baseline_age_ms",
                minimum=0,
            )
        _require_bool(self.baseline_refresh_due, "baseline_refresh_due")
        if self.error_type is not None:
            _require_text(self.error_type, "error_type", maximum=256)
        _require_timestamp(self.observed_at, "observed_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "host_id": self.host_id,
            "status": self.status.value,
            "run_generation": self.run_generation,
            "session_id": self.session_id,
            "listener_alive": self.listener_alive,
            "tick_alive": self.tick_alive,
            "baseline_armed": self.baseline_armed,
            "baseline_sha256": self.baseline_sha256,
            "baseline_age_ms": self.baseline_age_ms,
            "baseline_refresh_due": self.baseline_refresh_due,
            "error_type": self.error_type,
            "observed_at": self.observed_at,
        }


class GhostWalkHostService:
    """Own one long-running Ghost-Walk listener + refresh lifecycle."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        baseline_service: HostBaselineService,
        listener_factory: ListenerFactory,
        host_id: str,
        tick_interval_ms: int = DEFAULT_HOST_TICK_INTERVAL_MS,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkHostContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._baseline_service = baseline_service
        self._listener_factory = listener_factory
        self.host_id = _require_text(host_id, "host_id", maximum=512)
        self.tick_interval_ms = _require_int(
            tick_interval_ms,
            "tick_interval_ms",
            minimum=MIN_HOST_TICK_INTERVAL_MS,
            maximum=MAX_HOST_TICK_INTERVAL_MS,
        )
        if self.tick_interval_ms > baseline_service.refresh_interval_ms:
            raise GhostWalkHostContractError(
                "host tick interval cannot exceed baseline refresh interval"
            )
        if (
            not isinstance(shutdown_timeout_seconds, (int, float))
            or isinstance(shutdown_timeout_seconds, bool)
            or shutdown_timeout_seconds <= 0
            or shutdown_timeout_seconds > MAX_SHUTDOWN_TIMEOUT_SECONDS
        ):
            raise GhostWalkHostContractError(
                "shutdown timeout must be within (0, 30] seconds"
            )
        self.shutdown_timeout_seconds = float(shutdown_timeout_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._listener: HostListener | None = None
        self._listener_thread: threading.Thread | None = None
        self._tick_thread: threading.Thread | None = None
        self._status = GhostWalkHostStatus.STOPPED
        self._session_id: str | None = None
        self._run_generation = self._next_run_generation()
        self._error_type: str | None = None

    @classmethod
    def from_windows(
        cls,
        *,
        ledger: RealityLedger,
        host_id: str,
        baseline_service_id: str,
        coordinator_id: str,
        listener_id: str,
        operator_author_id: str,
        tick_interval_ms: int = DEFAULT_HOST_TICK_INTERVAL_MS,
    ) -> "GhostWalkHostService":
        from phios.macro_ghostwalk_capture import (
            GhostWalkCaptureAdapter,
            WindowsWindowFrameProvider,
        )
        from phios.macro_ghostwalk_listener import (
            GhostWalkListenerBridge,
            WindowsGhostWalkListener,
        )
        from phios.macro_windows_uia import WindowsUiaSemanticProvider

        baseline_service = GhostWalkBaselineRefreshService.from_windows(
            ledger=ledger,
            service_id=baseline_service_id,
            coordinator_id=coordinator_id,
            operator_author_id=operator_author_id,
        )

        def listener_factory(
            handler: Callable[[GhostWalkListenerOutcome], object],
        ) -> HostListener:
            capture = GhostWalkCaptureAdapter(
                ledger=ledger,
                window_provider=WindowsWindowFrameProvider(),
                semantic_provider=WindowsUiaSemanticProvider.from_system(
                    ledger=ledger
                ),
            )
            bridge = GhostWalkListenerBridge(
                ledger=ledger,
                capture_adapter=capture,
                listener_id=listener_id,
            )
            return WindowsGhostWalkListener(
                bridge=bridge,
                outcome_handler=handler,
            )

        return cls(
            ledger=ledger,
            baseline_service=baseline_service,
            listener_factory=listener_factory,
            host_id=host_id,
            tick_interval_ms=tick_interval_ms,
        )

    @property
    def running(self) -> bool:
        return self._status in {
            GhostWalkHostStatus.STARTING,
            GhostWalkHostStatus.RUNNING,
            GhostWalkHostStatus.DEGRADED,
            GhostWalkHostStatus.STOPPING,
        }

    @property
    def active(self) -> bool:
        return bool(
            self.running
            or self._listener_thread is not None
            or self._tick_thread is not None
            or self._session_id is not None
        )

    def start(self, *, session_id: str) -> GhostWalkHostHealth:
        session_id = _require_text(
            session_id,
            "session_id",
            maximum=512,
        )
        with self._lock:
            if self.running:
                raise GhostWalkHostContractError(
                    "Ghost-Walk host is already running"
                )
            self._validate_and_recover_history()
            self._run_generation = self._next_run_generation()
            self._session_id = session_id
            self._error_type = None
            self._stop_event.clear()
            self._status = GhostWalkHostStatus.STARTING

            arm = self._baseline_service.arm(session_id=session_id)
            self._listener = self._listener_factory(
                self._handle_listener_outcome
            )
            self._listener_thread = threading.Thread(
                target=self._listener_main,
                name=f"PhiOS-GhostWalk-Listener-{self.host_id}",
                daemon=True,
            )
            self._tick_thread = threading.Thread(
                target=self._tick_main,
                name=f"PhiOS-GhostWalk-Tick-{self.host_id}",
                daemon=True,
            )
            self._listener_thread.start()
            self._tick_thread.start()

            self._status = (
                GhostWalkHostStatus.RUNNING
                if arm.receipt.status is BaselineRefreshStatus.FRESH
                else GhostWalkHostStatus.DEGRADED
            )
            self._append_receipt(
                event_kind=GhostWalkHostEventKind.START,
                reason=(
                    GhostWalkHostReason.STARTED_FRESH
                    if self._status is GhostWalkHostStatus.RUNNING
                    else GhostWalkHostReason.STARTED_DEGRADED
                ),
                baseline_service_receipt_sha256=arm.receipt.receipt_sha256,
                transition_coordinator_receipt_sha256=None,
                listener_receipt_sha256=None,
                baseline_health=arm.health,
                recovered_prior_run=False,
                error_type=None,
            )
            return self.health()

    def stop(self) -> GhostWalkHostHealth:
        with self._lock:
            if not self.active:
                return self.health()
            self._status = GhostWalkHostStatus.STOPPING
            self._append_receipt(
                event_kind=GhostWalkHostEventKind.STOP,
                reason=GhostWalkHostReason.STOP_REQUESTED,
                baseline_service_receipt_sha256=None,
                transition_coordinator_receipt_sha256=None,
                listener_receipt_sha256=None,
                baseline_health=self._safe_baseline_health(),
                recovered_prior_run=False,
                error_type=self._error_type,
            )
            self._stop_event.set()
            listener = self._listener
            listener_thread = self._listener_thread
            tick_thread = self._tick_thread

        if listener is not None:
            listener.stop()
        if listener_thread is not None:
            listener_thread.join(timeout=self.shutdown_timeout_seconds)
        if tick_thread is not None:
            tick_thread.join(timeout=self.shutdown_timeout_seconds)

        with self._lock:
            incomplete = bool(
                (listener_thread is not None and listener_thread.is_alive())
                or (tick_thread is not None and tick_thread.is_alive())
            )
            disarm = self._baseline_service.disarm()
            self._status = (
                GhostWalkHostStatus.FAILED
                if incomplete
                else GhostWalkHostStatus.STOPPED
            )
            if incomplete and self._error_type is None:
                self._error_type = "ShutdownTimeout"
            self._append_receipt(
                event_kind=GhostWalkHostEventKind.STOP,
                reason=(
                    GhostWalkHostReason.SHUTDOWN_INCOMPLETE
                    if incomplete
                    else GhostWalkHostReason.STOPPED_CLEAN
                ),
                baseline_service_receipt_sha256=disarm.receipt.receipt_sha256,
                transition_coordinator_receipt_sha256=None,
                listener_receipt_sha256=None,
                baseline_health=disarm.health,
                recovered_prior_run=False,
                error_type=self._error_type,
            )
            self._session_id = None
            self._listener = None
            self._listener_thread = None
            self._tick_thread = None
            return self.health()

    def arm_baseline(self) -> GhostWalkHostHealth:
        """Arm a fresh learning baseline through the host lifecycle boundary."""

        with self._lock:
            if self._session_id is None or self._status not in {
                GhostWalkHostStatus.RUNNING,
                GhostWalkHostStatus.DEGRADED,
            }:
                raise GhostWalkHostContractError(
                    "Ghost-Walk host must be running before baseline arm"
                )
            outcome = self._baseline_service.arm(
                session_id=self._session_id
            )
            self._status = (
                GhostWalkHostStatus.RUNNING
                if outcome.receipt.status is BaselineRefreshStatus.FRESH
                else GhostWalkHostStatus.DEGRADED
            )
            return self.health()

    def disarm_baseline(self) -> GhostWalkHostHealth:
        """Pause learning-state capture without stopping the host listener."""

        with self._lock:
            if self._session_id is None or self._status not in {
                GhostWalkHostStatus.RUNNING,
                GhostWalkHostStatus.DEGRADED,
            }:
                raise GhostWalkHostContractError(
                    "Ghost-Walk host must be running before baseline disarm"
                )
            self._baseline_service.disarm()
            self._status = GhostWalkHostStatus.DEGRADED
            return self.health()

    def health(self) -> GhostWalkHostHealth:
        observed_at = _require_timestamp(
            self._clock(),
            "health_observed_at",
        )
        baseline = self._safe_baseline_health(observed_at=observed_at)
        listener_alive = bool(
            self._listener_thread is not None
            and self._listener_thread.is_alive()
        )
        tick_alive = bool(
            self._tick_thread is not None
            and self._tick_thread.is_alive()
        )
        return GhostWalkHostHealth(
            host_id=self.host_id,
            status=self._status,
            run_generation=self._run_generation,
            session_id=self._session_id,
            listener_alive=listener_alive,
            tick_alive=tick_alive,
            baseline_armed=baseline.baseline_sha256 is not None,
            baseline_sha256=baseline.baseline_sha256,
            baseline_age_ms=baseline.baseline_age_ms,
            baseline_refresh_due=baseline.refresh_due,
            error_type=self._error_type,
            observed_at=observed_at,
        )

    def _listener_main(self) -> None:
        listener = self._listener
        session_id = self._session_id
        if listener is None or session_id is None:
            return
        try:
            listener.run(session_id=session_id)
        except Exception as exc:
            self._record_failure(
                reason=GhostWalkHostReason.LISTENER_FAILED,
                error=exc,
            )
            return
        if not self._stop_event.is_set():
            self._record_failure(
                reason=GhostWalkHostReason.LISTENER_STOPPED_UNEXPECTEDLY,
                error=RuntimeError("listener returned without stop request"),
            )

    def _tick_main(self) -> None:
        interval_seconds = self.tick_interval_ms / 1000.0
        while not self._stop_event.wait(interval_seconds):
            try:
                tick = self._baseline_service.tick()
            except Exception as exc:
                self._record_failure(
                    reason=GhostWalkHostReason.TICK_FAILED,
                    error=exc,
                )
                listener = self._listener
                if listener is not None:
                    try:
                        listener.stop()
                    except Exception:
                        pass
                return

            with self._lock:
                if self._stop_event.is_set():
                    return
                self._status = (
                    GhostWalkHostStatus.RUNNING
                    if tick.receipt.status is BaselineRefreshStatus.FRESH
                    else GhostWalkHostStatus.DEGRADED
                )
                self._append_receipt(
                    event_kind=GhostWalkHostEventKind.TICK,
                    reason=(
                        GhostWalkHostReason.TICK_FRESH
                        if self._status is GhostWalkHostStatus.RUNNING
                        else GhostWalkHostReason.TICK_DEGRADED
                    ),
                    baseline_service_receipt_sha256=tick.receipt.receipt_sha256,
                    transition_coordinator_receipt_sha256=None,
                    listener_receipt_sha256=None,
                    baseline_health=tick.health,
                    recovered_prior_run=False,
                    error_type=None,
                )

    def _handle_listener_outcome(
        self,
        outcome: GhostWalkListenerOutcome,
    ) -> object:
        try:
            coordinated = self._baseline_service.handle_listener_outcome(
                outcome
            )
        except Exception as exc:
            self._record_failure(
                reason=GhostWalkHostReason.LISTENER_FAILED,
                error=exc,
            )
            raise

        with self._lock:
            if self._stop_event.is_set():
                return coordinated
            self._status = (
                GhostWalkHostStatus.RUNNING
                if coordinated.service_receipt.status
                is BaselineRefreshStatus.FRESH
                else GhostWalkHostStatus.DEGRADED
            )
            self._append_receipt(
                event_kind=GhostWalkHostEventKind.LISTENER,
                reason=GhostWalkHostReason.LISTENER_OUTCOME_HANDLED,
                baseline_service_receipt_sha256=(
                    coordinated.service_receipt.receipt_sha256
                ),
                transition_coordinator_receipt_sha256=(
                    coordinated.coordination.receipt.receipt_sha256
                ),
                listener_receipt_sha256=outcome.receipt.receipt_sha256,
                baseline_health=coordinated.health,
                recovered_prior_run=False,
                error_type=None,
            )
        return coordinated

    def _record_failure(
        self,
        *,
        reason: GhostWalkHostReason,
        error: Exception,
    ) -> None:
        with self._lock:
            if self._status is GhostWalkHostStatus.FAILED:
                return
            self._error_type = type(error).__name__
            self._status = GhostWalkHostStatus.FAILED
            self._stop_event.set()
            self._append_receipt(
                event_kind=GhostWalkHostEventKind.FAILURE,
                reason=reason,
                baseline_service_receipt_sha256=None,
                transition_coordinator_receipt_sha256=None,
                listener_receipt_sha256=None,
                baseline_health=self._safe_baseline_health(),
                recovered_prior_run=False,
                error_type=self._error_type,
            )

    def _validate_and_recover_history(self) -> None:
        rows = self._ledger.ghostwalk_host_receipts(host_id=self.host_id)
        previous: GhostWalkHostReceipt | None = None
        for expected_sequence, row in enumerate(rows):
            receipt = GhostWalkHostReceipt.from_dict(row)
            if receipt.host_id != self.host_id:
                raise GhostWalkHostContractError(
                    "persisted host identity changed"
                )
            if receipt.sequence != expected_sequence:
                raise GhostWalkHostContractError(
                    "persisted host sequences are not contiguous"
                )
            expected_previous = (
                None if previous is None else previous.receipt_sha256
            )
            if receipt.previous_receipt_sha256 != expected_previous:
                raise GhostWalkHostContractError(
                    "persisted host receipt hash chain mismatch"
                )
            previous = receipt

        if previous is None:
            return
        if previous.status in {
            GhostWalkHostStatus.STARTING,
            GhostWalkHostStatus.RUNNING,
            GhostWalkHostStatus.DEGRADED,
            GhostWalkHostStatus.STOPPING,
        }:
            self._run_generation = previous.run_generation
            self._session_id = previous.session_id
            self._status = GhostWalkHostStatus.STOPPED
            self._append_receipt(
                event_kind=GhostWalkHostEventKind.RECOVERY,
                reason=GhostWalkHostReason.PRIOR_RUN_ABANDONED,
                baseline_service_receipt_sha256=None,
                transition_coordinator_receipt_sha256=None,
                listener_receipt_sha256=None,
                baseline_health=None,
                recovered_prior_run=True,
                error_type=None,
            )
            self._session_id = None

    def _next_run_generation(self) -> int:
        rows = self._ledger.ghostwalk_host_receipts(host_id=self.host_id)
        if not rows:
            return 0
        generations: list[int] = []
        for row in rows:
            value = row.get("run_generation")
            if isinstance(value, bool) or not isinstance(value, int):
                raise GhostWalkHostContractError(
                    "persisted run_generation must be an integer"
                )
            generations.append(value)
        return max(generations) + 1

    def _safe_baseline_health(
        self,
        *,
        observed_at: str | None = None,
    ) -> BaselineHealthSnapshot:
        timestamp = (
            _require_timestamp(observed_at, "observed_at")
            if observed_at is not None
            else _require_timestamp(self._clock(), "baseline_health_at")
        )
        return self._baseline_service.health(observed_at=timestamp)

    def _append_receipt(
        self,
        *,
        event_kind: GhostWalkHostEventKind,
        reason: GhostWalkHostReason,
        baseline_service_receipt_sha256: str | None,
        transition_coordinator_receipt_sha256: str | None,
        listener_receipt_sha256: str | None,
        baseline_health: BaselineHealthSnapshot | None,
        recovered_prior_run: bool,
        error_type: str | None,
    ) -> GhostWalkHostReceipt:
        sequence = self._ledger.next_ghostwalk_host_sequence(
            host_id=self.host_id
        )
        previous_sha = self._ledger.latest_ghostwalk_host_receipt_sha256(
            host_id=self.host_id
        )
        observed_at = _require_timestamp(
            self._clock(),
            "host_receipt_observed_at",
        )
        baseline_sha = (
            None if baseline_health is None else baseline_health.baseline_sha256
        )
        baseline_age = (
            None if baseline_health is None else baseline_health.baseline_age_ms
        )
        receipt = GhostWalkHostReceipt(
            host_id=self.host_id,
            sequence=sequence,
            run_generation=self._run_generation,
            event_kind=event_kind,
            session_id=self._session_id,
            status=self._status,
            reason=reason,
            observed_at=observed_at,
            baseline_service_receipt_sha256=baseline_service_receipt_sha256,
            transition_coordinator_receipt_sha256=(
                transition_coordinator_receipt_sha256
            ),
            listener_receipt_sha256=listener_receipt_sha256,
            baseline_sha256=baseline_sha,
            baseline_age_ms=baseline_age,
            listener_alive=bool(
                self._listener_thread is not None
                and self._listener_thread.is_alive()
            ),
            tick_alive=bool(
                self._tick_thread is not None
                and self._tick_thread.is_alive()
            ),
            recovered_prior_run=recovered_prior_run,
            error_type=error_type,
            previous_receipt_sha256=previous_sha,
        )
        self._ledger.append_ghostwalk_host_receipt(receipt)
        return receipt
