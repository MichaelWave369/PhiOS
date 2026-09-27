"""Post-action observable-state verification for Macro Runtime v0.19.

This layer verifies that a declared observable desktop state is present after a
governed interaction. It does not prove causation and it carries no authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Mapping, Protocol

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import WindowFrame
from phios.macro_uia_revalidation import (
    SemanticReplayRevalidator,
    SemanticRevalidationDecision,
    SemanticRevalidationReason,
)
from phios.spine.ledger import RealityLedger

POST_ACTION_EXPECTATION_SCHEMA_VERSION = (
    "phios.post_action_expectation.v0.19"
)
POST_ACTION_OBSERVATION_SCHEMA_VERSION = (
    "phios.post_action_observation.v0.19"
)
POST_ACTION_VERIFICATION_RECEIPT_SCHEMA_VERSION = (
    "phios.post_action_verification_receipt.v0.19"
)
MAX_POST_ACTION_OBSERVATIONS = 10
MAX_POST_ACTION_INTERVAL_MS = 2000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PID_RE = re.compile(r"^pid:([1-9][0-9]*)$")


class PostActionVerificationContractError(ValueError):
    """Raised when a post-action verification contract is malformed."""


class PostActionExpectationKind(StrEnum):
    WINDOW_TITLE_EQUALS = "WINDOW_TITLE_EQUALS"
    WINDOW_TITLE_CHANGED = "WINDOW_TITLE_CHANGED"
    SEMANTIC_PRESENT = "SEMANTIC_PRESENT"
    SEMANTIC_ABSENT = "SEMANTIC_ABSENT"


class PostActionObservationStatus(StrEnum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    INDETERMINATE = "INDETERMINATE"


class PostActionVerificationDecision(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INDETERMINATE = "INDETERMINATE"


class PostActionVerificationReason(StrEnum):
    EXPECTATION_MATCHED = "EXPECTATION_MATCHED"
    EXPECTATION_NOT_OBSERVED = "EXPECTATION_NOT_OBSERVED"
    OBSERVATION_INDETERMINATE = "OBSERVATION_INDETERMINATE"
    FRAME_UNAVAILABLE = "FRAME_UNAVAILABLE"
    PROCESS_MISMATCH = "PROCESS_MISMATCH"
    WINDOW_TITLE_MATCHED = "WINDOW_TITLE_MATCHED"
    WINDOW_TITLE_UNCHANGED = "WINDOW_TITLE_UNCHANGED"
    WINDOW_TITLE_DIFFERENT = "WINDOW_TITLE_DIFFERENT"
    SEMANTIC_PRESENT = "SEMANTIC_PRESENT"
    SEMANTIC_MISSING = "SEMANTIC_MISSING"
    SEMANTIC_AMBIGUOUS = "SEMANTIC_AMBIGUOUS"
    SEMANTIC_BACKEND_ERROR = "SEMANTIC_BACKEND_ERROR"
    SEMANTIC_SCOPE_UNCERTAIN = "SEMANTIC_SCOPE_UNCERTAIN"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise PostActionVerificationContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise PostActionVerificationContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise PostActionVerificationContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise PostActionVerificationContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PostActionVerificationContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise PostActionVerificationContractError(
            f"{field} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise PostActionVerificationContractError(
            f"{field} must be at most {maximum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise PostActionVerificationContractError(
            f"{field} must be Boolean"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PostActionVerificationContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise PostActionVerificationContractError(
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
        raise PostActionVerificationContractError(
            "post-action payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_pid(value: str) -> int:
    text = _require_text(value, "expected_process_id", maximum=128)
    match = _PID_RE.fullmatch(text)
    if match is None:
        raise PostActionVerificationContractError(
            "expected_process_id must use pid:<positive-int>"
        )
    return int(match.group(1))


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class PostActionExpectation:
    """One exact observable state the macro expects after an interaction."""

    kind: PostActionExpectationKind
    expected_process_id: str
    source_window_title_sha256: str
    expected_window_title_sha256: str | None = None
    semantic_target: SemanticTarget | None = None
    max_observations: int = 3
    interval_ms: int = 50
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = POST_ACTION_EXPECTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != POST_ACTION_EXPECTATION_SCHEMA_VERSION:
            raise PostActionVerificationContractError(
                "unsupported post-action expectation schema"
            )
        _parse_pid(self.expected_process_id)
        _require_sha256(
            self.source_window_title_sha256,
            "source_window_title_sha256",
        )
        _require_int(
            self.max_observations,
            "max_observations",
            minimum=1,
            maximum=MAX_POST_ACTION_OBSERVATIONS,
        )
        _require_int(
            self.interval_ms,
            "interval_ms",
            minimum=0,
            maximum=MAX_POST_ACTION_INTERVAL_MS,
        )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise PostActionVerificationContractError(
                "PostActionExpectation cannot carry authority"
            )

        if self.kind is PostActionExpectationKind.WINDOW_TITLE_EQUALS:
            _require_sha256(
                self.expected_window_title_sha256,
                "expected_window_title_sha256",
            )
            if self.semantic_target is not None:
                raise PostActionVerificationContractError(
                    "WINDOW_TITLE_EQUALS cannot carry semantic target"
                )
        elif self.kind is PostActionExpectationKind.WINDOW_TITLE_CHANGED:
            if self.expected_window_title_sha256 is not None:
                raise PostActionVerificationContractError(
                    "WINDOW_TITLE_CHANGED cannot carry expected title hash"
                )
            if self.semantic_target is not None:
                raise PostActionVerificationContractError(
                    "WINDOW_TITLE_CHANGED cannot carry semantic target"
                )
        elif self.kind in {
            PostActionExpectationKind.SEMANTIC_PRESENT,
            PostActionExpectationKind.SEMANTIC_ABSENT,
        }:
            _require_sha256(
                self.expected_window_title_sha256,
                "expected_window_title_sha256",
            )
            if self.semantic_target is None:
                raise PostActionVerificationContractError(
                    "semantic expectation requires SemanticTarget"
                )
        else:  # pragma: no cover - enum exhaustiveness
            raise PostActionVerificationContractError(
                "unsupported post-action expectation kind"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "expected_process_id": self.expected_process_id,
            "source_window_title_sha256": (
                self.source_window_title_sha256
            ),
            "expected_window_title_sha256": (
                self.expected_window_title_sha256
            ),
            "semantic_target": (
                None
                if self.semantic_target is None
                else self.semantic_target.to_dict()
            ),
            "max_observations": self.max_observations,
            "interval_ms": self.interval_ms,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def expectation_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["expectation_sha256"] = self.expectation_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> "PostActionExpectation":
        if not isinstance(value, Mapping):
            raise PostActionVerificationContractError(
                "post_action_expectation must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "kind",
            "expected_process_id",
            "source_window_title_sha256",
            "expected_window_title_sha256",
            "semantic_target",
            "max_observations",
            "interval_ms",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "expectation_sha256",
        }
        if set(data) != expected:
            raise PostActionVerificationContractError(
                "post-action expectation fields mismatch"
            )

        semantic_raw = data["semantic_target"]
        if semantic_raw is not None and not isinstance(
            semantic_raw,
            Mapping,
        ):
            raise PostActionVerificationContractError(
                "semantic_target must be object or null"
            )
        try:
            kind = PostActionExpectationKind(
                _require_text(data["kind"], "kind", maximum=64)
            )
        except ValueError as exc:
            raise PostActionVerificationContractError(
                "unsupported post-action expectation kind"
            ) from exc

        expectation = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=128,
            ),
            kind=kind,
            expected_process_id=_require_text(
                data["expected_process_id"],
                "expected_process_id",
                maximum=128,
            ),
            source_window_title_sha256=_require_sha256(
                data["source_window_title_sha256"],
                "source_window_title_sha256",
            ),
            expected_window_title_sha256=_optional_sha256(
                data["expected_window_title_sha256"],
                "expected_window_title_sha256",
            ),
            semantic_target=(
                None
                if semantic_raw is None
                else SemanticTarget.from_dict(semantic_raw)
            ),
            max_observations=_require_int(
                data["max_observations"],
                "max_observations",
                minimum=1,
                maximum=MAX_POST_ACTION_OBSERVATIONS,
            ),
            interval_ms=_require_int(
                data["interval_ms"],
                "interval_ms",
                minimum=0,
                maximum=MAX_POST_ACTION_INTERVAL_MS,
            ),
            operational_authority=_require_bool(
                data["operational_authority"],
                "operational_authority",
            ),
            action_authority=_require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=_require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if (
            _require_sha256(
                data["expectation_sha256"],
                "expectation_sha256",
            )
            != expectation.expectation_sha256
        ):
            raise PostActionVerificationContractError(
                "post-action expectation hash mismatch"
            )
        return expectation


@dataclass(frozen=True, slots=True)
class PostActionObservation:
    index: int
    status: PostActionObservationStatus
    reason: PostActionVerificationReason
    observed_at: str
    frame_sha256: str | None
    semantic_revalidation_receipt_sha256: str | None
    schema_version: str = POST_ACTION_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != POST_ACTION_OBSERVATION_SCHEMA_VERSION:
            raise PostActionVerificationContractError(
                "unsupported post-action observation schema"
            )
        _require_int(self.index, "index", minimum=0)
        _require_timestamp(self.observed_at, "observed_at")
        if self.frame_sha256 is not None:
            _require_sha256(self.frame_sha256, "frame_sha256")
        if self.semantic_revalidation_receipt_sha256 is not None:
            _require_sha256(
                self.semantic_revalidation_receipt_sha256,
                "semantic_revalidation_receipt_sha256",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "index": self.index,
            "status": self.status.value,
            "reason": self.reason.value,
            "observed_at": self.observed_at,
            "frame_sha256": self.frame_sha256,
            "semantic_revalidation_receipt_sha256": (
                self.semantic_revalidation_receipt_sha256
            ),
        }


@dataclass(frozen=True, slots=True)
class PostActionVerificationReceipt:
    desktop_interaction_receipt_sha256: str
    operation_payload_sha256: str
    expectation_sha256: str
    decision: PostActionVerificationDecision
    reason: PostActionVerificationReason
    observations: tuple[PostActionObservation, ...]
    verified_at: str
    causation_proven: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = POST_ACTION_VERIFICATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != POST_ACTION_VERIFICATION_RECEIPT_SCHEMA_VERSION
        ):
            raise PostActionVerificationContractError(
                "unsupported post-action verification receipt schema"
            )
        _require_sha256(
            self.desktop_interaction_receipt_sha256,
            "desktop_interaction_receipt_sha256",
        )
        _require_sha256(
            self.operation_payload_sha256,
            "operation_payload_sha256",
        )
        _require_sha256(
            self.expectation_sha256,
            "expectation_sha256",
        )
        if not self.observations:
            raise PostActionVerificationContractError(
                "post-action verification requires observations"
            )
        for index, observation in enumerate(self.observations):
            if observation.index != index:
                raise PostActionVerificationContractError(
                    "post-action observation indexes must be contiguous"
                )
        _require_timestamp(self.verified_at, "verified_at")
        if self.causation_proven:
            raise PostActionVerificationContractError(
                "v0.19 cannot claim causal proof"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise PostActionVerificationContractError(
                "PostActionVerificationReceipt cannot carry authority"
            )
        if self.decision is PostActionVerificationDecision.VERIFIED:
            if self.reason is not PostActionVerificationReason.EXPECTATION_MATCHED:
                raise PostActionVerificationContractError(
                    "VERIFIED requires EXPECTATION_MATCHED"
                )
            if not any(
                item.status is PostActionObservationStatus.MATCH
                for item in self.observations
            ):
                raise PostActionVerificationContractError(
                    "VERIFIED receipt requires matching observation"
                )
        elif self.decision is PostActionVerificationDecision.NOT_VERIFIED:
            if (
                self.reason
                is not PostActionVerificationReason.EXPECTATION_NOT_OBSERVED
            ):
                raise PostActionVerificationContractError(
                    "NOT_VERIFIED requires EXPECTATION_NOT_OBSERVED"
                )
        elif self.decision is PostActionVerificationDecision.INDETERMINATE:
            if (
                self.reason
                is not PostActionVerificationReason.OBSERVATION_INDETERMINATE
            ):
                raise PostActionVerificationContractError(
                    "INDETERMINATE requires OBSERVATION_INDETERMINATE"
                )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "desktop_interaction_receipt_sha256": (
                self.desktop_interaction_receipt_sha256
            ),
            "operation_payload_sha256": self.operation_payload_sha256,
            "expectation_sha256": self.expectation_sha256,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "observations": [
                observation.to_dict()
                for observation in self.observations
            ],
            "verified_at": self.verified_at,
            "causation_proven": self.causation_proven,
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


class PostActionFrameProvider(Protocol):
    provider_id: str

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None: ...


class PostActionVerifier:
    """Bounded synchronous post-action observer."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        frame_provider: PostActionFrameProvider,
        semantic_revalidator: SemanticReplayRevalidator,
        clock: Callable[[], str] = _utc_now_iso,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise PostActionVerificationContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._frame_provider = frame_provider
        self._semantic_revalidator = semantic_revalidator
        self._clock = clock
        self._pause = pause

    def verify(
        self,
        *,
        desktop_interaction_receipt_sha256: str,
        operation_payload_sha256: str,
        expectation: PostActionExpectation,
    ) -> PostActionVerificationReceipt:
        interaction_sha = _require_sha256(
            desktop_interaction_receipt_sha256,
            "desktop_interaction_receipt_sha256",
        )
        payload_sha = _require_sha256(
            operation_payload_sha256,
            "operation_payload_sha256",
        )
        observations: list[PostActionObservation] = []

        for index in range(expectation.max_observations):
            observed_at = _require_timestamp(
                self._clock(),
                "observed_at",
            )
            frame = self._frame_provider.current_frame(
                observed_at=observed_at
            )
            observation = self._observe(
                index=index,
                expectation=expectation,
                frame=frame,
                observed_at=observed_at,
            )
            observations.append(observation)
            if observation.status is PostActionObservationStatus.MATCH:
                return self._finish(
                    interaction_sha=interaction_sha,
                    payload_sha=payload_sha,
                    expectation=expectation,
                    observations=tuple(observations),
                    decision=PostActionVerificationDecision.VERIFIED,
                    reason=PostActionVerificationReason.EXPECTATION_MATCHED,
                )
            if index + 1 < expectation.max_observations:
                self._pause(expectation.interval_ms / 1000.0)

        decision = (
            PostActionVerificationDecision.INDETERMINATE
            if any(
                item.status
                is PostActionObservationStatus.INDETERMINATE
                for item in observations
            )
            else PostActionVerificationDecision.NOT_VERIFIED
        )
        reason = (
            PostActionVerificationReason.OBSERVATION_INDETERMINATE
            if decision
            is PostActionVerificationDecision.INDETERMINATE
            else PostActionVerificationReason.EXPECTATION_NOT_OBSERVED
        )
        return self._finish(
            interaction_sha=interaction_sha,
            payload_sha=payload_sha,
            expectation=expectation,
            observations=tuple(observations),
            decision=decision,
            reason=reason,
        )

    def _observe(
        self,
        *,
        index: int,
        expectation: PostActionExpectation,
        frame: WindowFrame | None,
        observed_at: str,
    ) -> PostActionObservation:
        if frame is None:
            return PostActionObservation(
                index=index,
                status=PostActionObservationStatus.INDETERMINATE,
                reason=PostActionVerificationReason.FRAME_UNAVAILABLE,
                observed_at=observed_at,
                frame_sha256=None,
                semantic_revalidation_receipt_sha256=None,
            )
        if (
            frame.process_id != expectation.expected_process_id
            or not frame.foreground
        ):
            return PostActionObservation(
                index=index,
                status=PostActionObservationStatus.INDETERMINATE,
                reason=PostActionVerificationReason.PROCESS_MISMATCH,
                observed_at=observed_at,
                frame_sha256=frame.frame_sha256,
                semantic_revalidation_receipt_sha256=None,
            )

        if (
            expectation.kind
            is PostActionExpectationKind.WINDOW_TITLE_EQUALS
        ):
            assert expectation.expected_window_title_sha256 is not None
            matched = (
                frame.window_title_sha256
                == expectation.expected_window_title_sha256
            )
            return PostActionObservation(
                index=index,
                status=(
                    PostActionObservationStatus.MATCH
                    if matched
                    else PostActionObservationStatus.NO_MATCH
                ),
                reason=(
                    PostActionVerificationReason.WINDOW_TITLE_MATCHED
                    if matched
                    else PostActionVerificationReason.WINDOW_TITLE_DIFFERENT
                ),
                observed_at=observed_at,
                frame_sha256=frame.frame_sha256,
                semantic_revalidation_receipt_sha256=None,
            )

        if (
            expectation.kind
            is PostActionExpectationKind.WINDOW_TITLE_CHANGED
        ):
            changed = (
                frame.window_title_sha256
                != expectation.source_window_title_sha256
            )
            return PostActionObservation(
                index=index,
                status=(
                    PostActionObservationStatus.MATCH
                    if changed
                    else PostActionObservationStatus.NO_MATCH
                ),
                reason=(
                    PostActionVerificationReason.WINDOW_TITLE_DIFFERENT
                    if changed
                    else PostActionVerificationReason.WINDOW_TITLE_UNCHANGED
                ),
                observed_at=observed_at,
                frame_sha256=frame.frame_sha256,
                semantic_revalidation_receipt_sha256=None,
            )

        assert expectation.semantic_target is not None
        assert expectation.expected_window_title_sha256 is not None
        if (
            frame.window_title_sha256
            != expectation.expected_window_title_sha256
        ):
            return PostActionObservation(
                index=index,
                status=PostActionObservationStatus.INDETERMINATE,
                reason=PostActionVerificationReason.SEMANTIC_SCOPE_UNCERTAIN,
                observed_at=observed_at,
                frame_sha256=frame.frame_sha256,
                semantic_revalidation_receipt_sha256=None,
            )

        semantic = self._semantic_revalidator.assess(
            target=expectation.semantic_target,
            expected_process_id=expectation.expected_process_id,
            expected_window_title_sha256=(
                expectation.expected_window_title_sha256
            ),
            frame=frame,
            observed_at=observed_at,
        )
        semantic_sha = semantic.receipt_sha256

        if (
            expectation.kind
            is PostActionExpectationKind.SEMANTIC_PRESENT
        ):
            if (
                semantic.decision
                is SemanticRevalidationDecision.CLEAR
            ):
                status = PostActionObservationStatus.MATCH
                reason = PostActionVerificationReason.SEMANTIC_PRESENT
            elif (
                semantic.reason
                is SemanticRevalidationReason.TARGET_MISSING
            ):
                status = PostActionObservationStatus.NO_MATCH
                reason = PostActionVerificationReason.SEMANTIC_MISSING
            else:
                status = PostActionObservationStatus.INDETERMINATE
                reason = self._semantic_indeterminate_reason(semantic.reason)
        else:
            if (
                semantic.reason
                is SemanticRevalidationReason.TARGET_MISSING
            ):
                status = PostActionObservationStatus.MATCH
                reason = PostActionVerificationReason.SEMANTIC_MISSING
            elif (
                semantic.decision
                is SemanticRevalidationDecision.CLEAR
            ):
                status = PostActionObservationStatus.NO_MATCH
                reason = PostActionVerificationReason.SEMANTIC_PRESENT
            else:
                status = PostActionObservationStatus.INDETERMINATE
                reason = self._semantic_indeterminate_reason(semantic.reason)

        return PostActionObservation(
            index=index,
            status=status,
            reason=reason,
            observed_at=observed_at,
            frame_sha256=frame.frame_sha256,
            semantic_revalidation_receipt_sha256=semantic_sha,
        )

    @staticmethod
    def _semantic_indeterminate_reason(
        reason: SemanticRevalidationReason,
    ) -> PostActionVerificationReason:
        if reason is SemanticRevalidationReason.TARGET_AMBIGUOUS:
            return PostActionVerificationReason.SEMANTIC_AMBIGUOUS
        if reason is SemanticRevalidationReason.BACKEND_ERROR:
            return PostActionVerificationReason.SEMANTIC_BACKEND_ERROR
        return PostActionVerificationReason.SEMANTIC_SCOPE_UNCERTAIN

    def _finish(
        self,
        *,
        interaction_sha: str,
        payload_sha: str,
        expectation: PostActionExpectation,
        observations: tuple[PostActionObservation, ...],
        decision: PostActionVerificationDecision,
        reason: PostActionVerificationReason,
    ) -> PostActionVerificationReceipt:
        receipt = PostActionVerificationReceipt(
            desktop_interaction_receipt_sha256=interaction_sha,
            operation_payload_sha256=payload_sha,
            expectation_sha256=expectation.expectation_sha256,
            decision=decision,
            reason=reason,
            observations=observations,
            verified_at=_require_timestamp(
                self._clock(),
                "verified_at",
            ),
        )
        self._ledger.append_post_action_verification_receipt(receipt)
        return receipt
