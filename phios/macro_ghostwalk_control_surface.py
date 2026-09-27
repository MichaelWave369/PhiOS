"""Operator-facing Ghost-Walk control surface for Macro Runtime v0.25.

This facade presents a compact read/control model for PhiShell and Vessie while
keeping UI callers away from listener, UIA, baseline-service, coordinator, and
execution-authority internals.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

from phios.macro_ghostwalk_host_service import (
    GhostWalkHostHealth,
    GhostWalkHostStatus,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_CONTROL_SNAPSHOT_SCHEMA_VERSION = (
    "phios.ghostwalk_control_snapshot.v0.25"
)
GHOSTWALK_CONTROL_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_control_receipt.v0.25"
)
DEFAULT_RECENT_TRANSITIONS = 5
DEFAULT_RECENT_ISSUES = 8
MAX_RECENT_ITEMS = 25
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkControlContractError(ValueError):
    """Raised when control-surface state or evidence is malformed."""


class GhostWalkControlAction(StrEnum):
    STATUS = "STATUS"
    START = "START"
    STOP = "STOP"
    ARM = "ARM"
    DISARM = "DISARM"


class GhostWalkControlResult(StrEnum):
    OBSERVED = "OBSERVED"
    APPLIED = "APPLIED"
    NOOP = "NOOP"
    REJECTED = "REJECTED"


class GhostWalkControlReason(StrEnum):
    STATUS_OBSERVED = "STATUS_OBSERVED"
    HOST_STARTED = "HOST_STARTED"
    HOST_STOPPED = "HOST_STOPPED"
    BASELINE_ARMED = "BASELINE_ARMED"
    BASELINE_DISARMED = "BASELINE_DISARMED"
    ALREADY_STOPPED = "ALREADY_STOPPED"
    ACTION_NOT_AVAILABLE = "ACTION_NOT_AVAILABLE"
    HOST_REJECTED = "HOST_REJECTED"


class GhostWalkRecoveryState(StrEnum):
    NONE = "NONE"
    PRIOR_RUN_ABANDONED = "PRIOR_RUN_ABANDONED"


class GhostWalkControlHost(Protocol):
    host_id: str

    def start(self, *, session_id: str) -> GhostWalkHostHealth: ...

    def stop(self) -> GhostWalkHostHealth: ...

    def arm_baseline(self) -> GhostWalkHostHealth: ...

    def disarm_baseline(self) -> GhostWalkHostHealth: ...

    def health(self) -> GhostWalkHostHealth: ...


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkControlContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkControlContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkControlContractError(
            f"{field} contains control characters"
        )
    return value


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GhostWalkControlContractError(
            f"{field} must be an integer"
        )
    if value < minimum:
        raise GhostWalkControlContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise GhostWalkControlContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkControlContractError(
            f"{field} must be Boolean"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkControlContractError(
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
        raise GhostWalkControlContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkControlContractError(
            f"{field} must include a timezone"
        )
    return text


def _timestamp_key(value: str) -> datetime:
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
        raise GhostWalkControlContractError(
            "Ghost-Walk control payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class LearnedTransitionSummary:
    inference_receipt_sha256: str
    session_id: str
    action_observation_sha256: str
    status: str
    candidate_kinds: tuple[str, ...]
    inferred_at: str
    operator_note_revision_sha256: str | None
    operator_note_revision: int | None
    operator_note_status: str | None

    def __post_init__(self) -> None:
        _require_sha256(
            self.inference_receipt_sha256,
            "inference_receipt_sha256",
        )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.action_observation_sha256,
            "action_observation_sha256",
        )
        _require_text(self.status, "status", maximum=64)
        if self.candidate_kinds != tuple(sorted(self.candidate_kinds)):
            raise GhostWalkControlContractError(
                "candidate kinds must be sorted"
            )
        for kind in self.candidate_kinds:
            _require_text(kind, "candidate_kind", maximum=128)
        _require_timestamp(self.inferred_at, "inferred_at")
        if self.operator_note_revision_sha256 is not None:
            _require_sha256(
                self.operator_note_revision_sha256,
                "operator_note_revision_sha256",
            )
        if self.operator_note_revision is not None:
            _require_int(
                self.operator_note_revision,
                "operator_note_revision",
                minimum=1,
            )
        if self.operator_note_status is not None:
            _require_text(
                self.operator_note_status,
                "operator_note_status",
                maximum=64,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "inference_receipt_sha256": self.inference_receipt_sha256,
            "session_id": self.session_id,
            "action_observation_sha256": self.action_observation_sha256,
            "status": self.status,
            "candidate_kinds": list(self.candidate_kinds),
            "inferred_at": self.inferred_at,
            "operator_note_revision_sha256": (
                self.operator_note_revision_sha256
            ),
            "operator_note_revision": self.operator_note_revision,
            "operator_note_status": self.operator_note_status,
        }


@dataclass(frozen=True, slots=True)
class GhostWalkIssueSummary:
    source: str
    status: str
    reason: str
    observed_at: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.source, "source", maximum=128)
        _require_text(self.status, "status", maximum=64)
        _require_text(self.reason, "reason", maximum=128)
        _require_timestamp(self.observed_at, "observed_at")
        _require_sha256(self.receipt_sha256, "receipt_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class GhostWalkControlSnapshot:
    surface_id: str
    host_id: str
    host_status: GhostWalkHostStatus
    run_generation: int
    session_id: str | None
    listener_alive: bool
    tick_alive: bool
    baseline_armed: bool
    baseline_sha256: str | None
    baseline_age_ms: int | None
    baseline_refresh_due: bool
    error_type: str | None
    recovery_state: GhostWalkRecoveryState
    recovery_receipt_sha256: str | None
    available_actions: tuple[GhostWalkControlAction, ...]
    last_action_observation_sha256: str | None
    learned_transitions: tuple[LearnedTransitionSummary, ...]
    recent_issues: tuple[GhostWalkIssueSummary, ...]
    observed_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_CONTROL_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_CONTROL_SNAPSHOT_SCHEMA_VERSION:
            raise GhostWalkControlContractError(
                "unsupported Ghost-Walk control snapshot schema"
            )
        _require_text(self.surface_id, "surface_id", maximum=512)
        _require_text(self.host_id, "host_id", maximum=512)
        _require_int(self.run_generation, "run_generation")
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
            )
        _require_bool(self.baseline_refresh_due, "baseline_refresh_due")
        if self.error_type is not None:
            _require_text(self.error_type, "error_type", maximum=256)
        if self.recovery_receipt_sha256 is not None:
            _require_sha256(
                self.recovery_receipt_sha256,
                "recovery_receipt_sha256",
            )
        if self.available_actions != tuple(
            sorted(self.available_actions, key=lambda item: item.value)
        ):
            raise GhostWalkControlContractError(
                "available actions must be sorted"
            )
        if len(set(self.available_actions)) != len(self.available_actions):
            raise GhostWalkControlContractError(
                "available actions must be unique"
            )
        if self.last_action_observation_sha256 is not None:
            _require_sha256(
                self.last_action_observation_sha256,
                "last_action_observation_sha256",
            )
        _require_timestamp(self.observed_at, "observed_at")
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkControlContractError(
                "GhostWalkControlSnapshot cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface_id": self.surface_id,
            "host_id": self.host_id,
            "host_status": self.host_status.value,
            "run_generation": self.run_generation,
            "session_id": self.session_id,
            "listener_alive": self.listener_alive,
            "tick_alive": self.tick_alive,
            "baseline_armed": self.baseline_armed,
            "baseline_sha256": self.baseline_sha256,
            "baseline_age_ms": self.baseline_age_ms,
            "baseline_refresh_due": self.baseline_refresh_due,
            "error_type": self.error_type,
            "recovery_state": self.recovery_state.value,
            "recovery_receipt_sha256": self.recovery_receipt_sha256,
            "available_actions": [
                action.value for action in self.available_actions
            ],
            "last_action_observation_sha256": (
                self.last_action_observation_sha256
            ),
            "learned_transitions": [
                item.to_dict() for item in self.learned_transitions
            ],
            "recent_issues": [
                item.to_dict() for item in self.recent_issues
            ],
            "observed_at": self.observed_at,
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


@dataclass(frozen=True, slots=True)
class GhostWalkControlReceipt:
    surface_id: str
    sequence: int
    action: GhostWalkControlAction
    requested_session_id: str | None
    result: GhostWalkControlResult
    reason: GhostWalkControlReason
    before_snapshot_sha256: str
    after_snapshot_sha256: str
    applied_at: str
    error_type: str | None = None
    previous_receipt_sha256: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_CONTROL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_CONTROL_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkControlContractError(
                "unsupported Ghost-Walk control receipt schema"
            )
        _require_text(self.surface_id, "surface_id", maximum=512)
        _require_int(self.sequence, "sequence")
        if self.requested_session_id is not None:
            _require_text(
                self.requested_session_id,
                "requested_session_id",
                maximum=512,
            )
        _require_sha256(
            self.before_snapshot_sha256,
            "before_snapshot_sha256",
        )
        _require_sha256(
            self.after_snapshot_sha256,
            "after_snapshot_sha256",
        )
        _require_timestamp(self.applied_at, "applied_at")
        if self.error_type is not None:
            _require_text(self.error_type, "error_type", maximum=256)
        if self.sequence == 0:
            if self.previous_receipt_sha256 is not None:
                raise GhostWalkControlContractError(
                    "first control receipt cannot reference prior history"
                )
        else:
            if self.previous_receipt_sha256 is None:
                raise GhostWalkControlContractError(
                    "later control receipt requires prior receipt hash"
                )
            _require_sha256(
                self.previous_receipt_sha256,
                "previous_receipt_sha256",
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkControlContractError(
                "GhostWalkControlReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface_id": self.surface_id,
            "sequence": self.sequence,
            "action": self.action.value,
            "requested_session_id": self.requested_session_id,
            "result": self.result.value,
            "reason": self.reason.value,
            "before_snapshot_sha256": self.before_snapshot_sha256,
            "after_snapshot_sha256": self.after_snapshot_sha256,
            "applied_at": self.applied_at,
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


@dataclass(frozen=True, slots=True)
class GhostWalkControlOutcome:
    receipt: GhostWalkControlReceipt
    snapshot: GhostWalkControlSnapshot


class GhostWalkControlSurface:
    """Zero-authority UI facade over one v0.24 Ghost-Walk host."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        host: GhostWalkControlHost,
        surface_id: str,
        recent_transitions: int = DEFAULT_RECENT_TRANSITIONS,
        recent_issues: int = DEFAULT_RECENT_ISSUES,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkControlContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._host = host
        self.surface_id = _require_text(
            surface_id,
            "surface_id",
            maximum=512,
        )
        self._recent_transitions = _require_int(
            recent_transitions,
            "recent_transitions",
            maximum=MAX_RECENT_ITEMS,
        )
        self._recent_issues = _require_int(
            recent_issues,
            "recent_issues",
            maximum=MAX_RECENT_ITEMS,
        )
        self._clock = clock

    def snapshot(self) -> GhostWalkControlSnapshot:
        host = self._host.health()
        observed_at = _require_timestamp(
            self._clock(),
            "control_snapshot_observed_at",
        )
        recovery_state, recovery_sha = self._recovery_state()
        return GhostWalkControlSnapshot(
            surface_id=self.surface_id,
            host_id=host.host_id,
            host_status=host.status,
            run_generation=host.run_generation,
            session_id=host.session_id,
            listener_alive=host.listener_alive,
            tick_alive=host.tick_alive,
            baseline_armed=host.baseline_armed,
            baseline_sha256=host.baseline_sha256,
            baseline_age_ms=host.baseline_age_ms,
            baseline_refresh_due=host.baseline_refresh_due,
            error_type=host.error_type,
            recovery_state=recovery_state,
            recovery_receipt_sha256=recovery_sha,
            available_actions=self._available_actions(host),
            last_action_observation_sha256=(
                self._last_action_observation_sha256()
            ),
            learned_transitions=self._learned_transitions(),
            recent_issues=self._issues(),
            observed_at=observed_at,
        )

    def apply(
        self,
        *,
        action: GhostWalkControlAction,
        session_id: str | None = None,
    ) -> GhostWalkControlOutcome:
        before = self.snapshot()
        requested_session = (
            None
            if session_id is None
            else _require_text(session_id, "session_id", maximum=512)
        )
        result = GhostWalkControlResult.APPLIED
        reason: GhostWalkControlReason
        error_type: str | None = None

        if action not in before.available_actions:
            if (
                action is GhostWalkControlAction.STOP
                and before.host_status is GhostWalkHostStatus.STOPPED
            ):
                result = GhostWalkControlResult.NOOP
                reason = GhostWalkControlReason.ALREADY_STOPPED
            else:
                result = GhostWalkControlResult.REJECTED
                reason = GhostWalkControlReason.ACTION_NOT_AVAILABLE
        else:
            try:
                if action is GhostWalkControlAction.STATUS:
                    result = GhostWalkControlResult.OBSERVED
                    reason = GhostWalkControlReason.STATUS_OBSERVED
                elif action is GhostWalkControlAction.START:
                    if requested_session is None:
                        raise GhostWalkControlContractError(
                            "START requires session_id"
                        )
                    self._host.start(session_id=requested_session)
                    reason = GhostWalkControlReason.HOST_STARTED
                elif action is GhostWalkControlAction.STOP:
                    self._host.stop()
                    reason = GhostWalkControlReason.HOST_STOPPED
                elif action is GhostWalkControlAction.ARM:
                    self._host.arm_baseline()
                    reason = GhostWalkControlReason.BASELINE_ARMED
                else:
                    self._host.disarm_baseline()
                    reason = GhostWalkControlReason.BASELINE_DISARMED
            except Exception as exc:
                result = GhostWalkControlResult.REJECTED
                reason = GhostWalkControlReason.HOST_REJECTED
                error_type = type(exc).__name__

        after = self.snapshot()
        receipt = self._append_receipt(
            action=action,
            requested_session_id=requested_session,
            result=result,
            reason=reason,
            before_snapshot_sha256=before.snapshot_sha256,
            after_snapshot_sha256=after.snapshot_sha256,
            error_type=error_type,
        )
        return GhostWalkControlOutcome(receipt=receipt, snapshot=after)

    @staticmethod
    def _available_actions(
        host: GhostWalkHostHealth,
    ) -> tuple[GhostWalkControlAction, ...]:
        actions = {GhostWalkControlAction.STATUS}
        if host.status is GhostWalkHostStatus.STOPPED:
            actions.add(GhostWalkControlAction.START)
        elif host.status in {
            GhostWalkHostStatus.RUNNING,
            GhostWalkHostStatus.DEGRADED,
            GhostWalkHostStatus.FAILED,
        }:
            actions.add(GhostWalkControlAction.STOP)
            if host.status in {
                GhostWalkHostStatus.RUNNING,
                GhostWalkHostStatus.DEGRADED,
            }:
                if host.baseline_armed:
                    actions.add(GhostWalkControlAction.DISARM)
                else:
                    actions.add(GhostWalkControlAction.ARM)
        return tuple(sorted(actions, key=lambda item: item.value))

    def _recovery_state(
        self,
    ) -> tuple[GhostWalkRecoveryState, str | None]:
        rows = self._ledger.ghostwalk_host_receipts(
            host_id=self._host.host_id
        )
        for row in reversed(rows):
            if row.get("event_kind") != "RECOVERY":
                continue
            receipt_sha = _require_sha256(
                row.get("receipt_sha256"),
                "recovery_receipt_sha256",
            )
            if row.get("reason") == "PRIOR_RUN_ABANDONED":
                return (
                    GhostWalkRecoveryState.PRIOR_RUN_ABANDONED,
                    receipt_sha,
                )
        return GhostWalkRecoveryState.NONE, None

    def _last_action_observation_sha256(self) -> str | None:
        rows = self._ledger.ghostwalk_observations()
        if not rows:
            return None
        return _require_sha256(
            rows[-1].get("observation_sha256"),
            "observation_sha256",
        )

    def _learned_transitions(
        self,
    ) -> tuple[LearnedTransitionSummary, ...]:
        if self._recent_transitions == 0:
            return ()
        notes = self._current_note_by_target()
        rows = self._ledger.recent_transition_inference_receipts(
            self._recent_transitions
        )
        summaries: list[LearnedTransitionSummary] = []
        for row in reversed(rows):
            candidates_raw = row.get("candidates")
            if not isinstance(candidates_raw, list):
                raise GhostWalkControlContractError(
                    "persisted transition candidates must be a list"
                )
            kinds: list[str] = []
            for candidate in candidates_raw:
                if not isinstance(candidate, dict):
                    raise GhostWalkControlContractError(
                        "persisted transition candidate must be an object"
                    )
                expectation = candidate.get("expectation")
                if not isinstance(expectation, dict):
                    raise GhostWalkControlContractError(
                        "persisted candidate expectation must be an object"
                    )
                kinds.append(
                    _require_text(
                        expectation.get("kind"),
                        "candidate expectation kind",
                        maximum=128,
                    )
                )
            receipt_sha = _require_sha256(
                row.get("receipt_sha256"),
                "inference_receipt_sha256",
            )
            note = notes.get(receipt_sha)
            summaries.append(
                LearnedTransitionSummary(
                    inference_receipt_sha256=receipt_sha,
                    session_id=_require_text(
                        row.get("session_id"),
                        "transition session_id",
                        maximum=512,
                    ),
                    action_observation_sha256=_require_sha256(
                        row.get("action_observation_sha256"),
                        "action_observation_sha256",
                    ),
                    status=_require_text(
                        row.get("status"),
                        "transition status",
                        maximum=64,
                    ),
                    candidate_kinds=tuple(sorted(kinds)),
                    inferred_at=_require_timestamp(
                        row.get("inferred_at"),
                        "inferred_at",
                    ),
                    operator_note_revision_sha256=(
                        None
                        if note is None
                        else _require_sha256(
                            note.get("revision_sha256"),
                            "operator_note_revision_sha256",
                        )
                    ),
                    operator_note_revision=(
                        None
                        if note is None
                        else _require_int(
                            note.get("revision"),
                            "operator_note_revision",
                            minimum=1,
                        )
                    ),
                    operator_note_status=(
                        None
                        if note is None
                        else _require_text(
                            note.get("status"),
                            "operator_note_status",
                            maximum=64,
                        )
                    ),
                )
            )
        return tuple(summaries)

    def _current_note_by_target(
        self,
    ) -> dict[str, dict[str, object]]:
        current: dict[str, dict[str, object]] = {}
        for row in self._ledger.operator_log_revisions():
            target = _require_sha256(
                row.get("target_sha256"),
                "operator note target_sha256",
            )
            revision = _require_int(
                row.get("revision"),
                "operator note revision",
                minimum=1,
            )
            prior = current.get(target)
            if prior is None:
                current[target] = row
                continue
            prior_revision = _require_int(
                prior.get("revision"),
                "prior operator note revision",
                minimum=1,
            )
            if revision > prior_revision:
                current[target] = row
        return current

    def _issues(self) -> tuple[GhostWalkIssueSummary, ...]:
        if self._recent_issues == 0:
            return ()
        issues: list[GhostWalkIssueSummary] = []
        for row in self._ledger.ghostwalk_host_receipts(
            host_id=self._host.host_id
        )[-MAX_RECENT_ITEMS:]:
            status = _require_text(
                row.get("status"),
                "host issue status",
                maximum=64,
            )
            reason = _require_text(
                row.get("reason"),
                "host issue reason",
                maximum=128,
            )
            if status not in {"DEGRADED", "FAILED"} and reason not in {
                "PRIOR_RUN_ABANDONED",
                "SHUTDOWN_INCOMPLETE",
            }:
                continue
            issues.append(
                GhostWalkIssueSummary(
                    source="HOST",
                    status=status,
                    reason=reason,
                    observed_at=_require_timestamp(
                        row.get("observed_at"),
                        "host issue observed_at",
                    ),
                    receipt_sha256=_require_sha256(
                        row.get("receipt_sha256"),
                        "host issue receipt_sha256",
                    ),
                )
            )

        for row in self._ledger.recent_transition_coordinator_receipts(
            MAX_RECENT_ITEMS
        ):
            status = _require_text(
                row.get("status"),
                "coordinator issue status",
                maximum=64,
            )
            if status != "HELD":
                continue
            issues.append(
                GhostWalkIssueSummary(
                    source="TRANSITION_COORDINATOR",
                    status=status,
                    reason=_require_text(
                        row.get("reason"),
                        "coordinator issue reason",
                        maximum=128,
                    ),
                    observed_at=_require_timestamp(
                        row.get("coordinated_at"),
                        "coordinator issue observed_at",
                    ),
                    receipt_sha256=_require_sha256(
                        row.get("receipt_sha256"),
                        "coordinator issue receipt_sha256",
                    ),
                )
            )

        for row in self._ledger.baseline_refresh_receipts()[
            -MAX_RECENT_ITEMS:
        ]:
            status = _require_text(
                row.get("status"),
                "refresh issue status",
                maximum=64,
            )
            if status != "DEGRADED":
                continue
            issues.append(
                GhostWalkIssueSummary(
                    source="BASELINE_REFRESH",
                    status=status,
                    reason=_require_text(
                        row.get("reason"),
                        "refresh issue reason",
                        maximum=128,
                    ),
                    observed_at=_require_timestamp(
                        row.get("observed_at"),
                        "refresh issue observed_at",
                    ),
                    receipt_sha256=_require_sha256(
                        row.get("receipt_sha256"),
                        "refresh issue receipt_sha256",
                    ),
                )
            )

        issues.sort(
            key=lambda item: _timestamp_key(item.observed_at),
            reverse=True,
        )
        return tuple(issues[: self._recent_issues])

    def _append_receipt(
        self,
        *,
        action: GhostWalkControlAction,
        requested_session_id: str | None,
        result: GhostWalkControlResult,
        reason: GhostWalkControlReason,
        before_snapshot_sha256: str,
        after_snapshot_sha256: str,
        error_type: str | None,
    ) -> GhostWalkControlReceipt:
        sequence = self._ledger.next_ghostwalk_control_sequence(
            surface_id=self.surface_id
        )
        previous_sha = self._ledger.latest_ghostwalk_control_receipt_sha256(
            surface_id=self.surface_id
        )
        receipt = GhostWalkControlReceipt(
            surface_id=self.surface_id,
            sequence=sequence,
            action=action,
            requested_session_id=requested_session_id,
            result=result,
            reason=reason,
            before_snapshot_sha256=before_snapshot_sha256,
            after_snapshot_sha256=after_snapshot_sha256,
            applied_at=_require_timestamp(
                self._clock(),
                "control_action_applied_at",
            ),
            error_type=error_type,
            previous_receipt_sha256=previous_sha,
        )
        self._ledger.append_ghostwalk_control_receipt(receipt)
        return receipt
