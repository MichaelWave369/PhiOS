"""Ghost-Walk before/after transition inference for Macro Runtime v0.20.

This layer compares immutable demonstrated UI state snapshots and proposes
zero-authority post-action expectations. Proposals are evidence-backed but do
not claim human intent or causation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_operator_log import OperatorLog, OperatorLogRevision
from phios.macro_post_action_verification import (
    PostActionExpectation,
    PostActionExpectationKind,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_STATE_SNAPSHOT_SCHEMA_VERSION = (
    "phios.ghostwalk_ui_state_snapshot.v0.20"
)
TRANSITION_CANDIDATE_SCHEMA_VERSION = (
    "phios.ghostwalk_transition_candidate.v0.20"
)
TRANSITION_INFERENCE_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_transition_inference_receipt.v0.20"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TransitionInferenceContractError(ValueError):
    """Raised when transition inference evidence cannot be trusted."""


class SnapshotPhase(StrEnum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"


class TransitionBasis(StrEnum):
    WINDOW_TITLE_CHANGED = "WINDOW_TITLE_CHANGED"
    SEMANTIC_APPEARED = "SEMANTIC_APPEARED"
    SEMANTIC_DISAPPEARED = "SEMANTIC_DISAPPEARED"


class TransitionInferenceStatus(StrEnum):
    CANDIDATES = "CANDIDATES"
    NO_OBSERVABLE_CHANGE = "NO_OBSERVABLE_CHANGE"
    SCOPE_CHANGED = "SCOPE_CHANGED"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise TransitionInferenceContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise TransitionInferenceContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise TransitionInferenceContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise TransitionInferenceContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransitionInferenceContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise TransitionInferenceContractError(
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
        raise TransitionInferenceContractError(
            "transition inference payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GhostWalkUiStateSnapshot:
    """Immutable zero-authority UI state around one demonstrated action."""

    session_id: str
    action_observation_sha256: str
    phase: SnapshotPhase
    process_id: str
    window_title_sha256: str
    frame_sha256: str
    semantic_targets: tuple[SemanticTarget, ...]
    observed_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_STATE_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_STATE_SNAPSHOT_SCHEMA_VERSION:
            raise TransitionInferenceContractError(
                "unsupported Ghost-Walk state snapshot schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.action_observation_sha256,
            "action_observation_sha256",
        )
        _require_text(self.process_id, "process_id", maximum=512)
        _require_sha256(
            self.window_title_sha256,
            "window_title_sha256",
        )
        _require_sha256(self.frame_sha256, "frame_sha256")
        _require_timestamp(self.observed_at, "observed_at")
        hashes = tuple(
            target.target_sha256 for target in self.semantic_targets
        )
        if hashes != tuple(sorted(hashes)):
            raise TransitionInferenceContractError(
                "semantic targets must be sorted by target SHA-256"
            )
        if len(set(hashes)) != len(hashes):
            raise TransitionInferenceContractError(
                "semantic targets must be unique"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise TransitionInferenceContractError(
                "GhostWalkUiStateSnapshot cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "action_observation_sha256": (
                self.action_observation_sha256
            ),
            "phase": self.phase.value,
            "process_id": self.process_id,
            "window_title_sha256": self.window_title_sha256,
            "frame_sha256": self.frame_sha256,
            "semantic_targets": [
                target.to_dict()
                for target in self.semantic_targets
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
class TransitionCandidate:
    """One inferred postcondition proposal, not accepted human intent."""

    candidate_id: str
    basis: TransitionBasis
    expectation: PostActionExpectation
    before_snapshot_sha256: str
    after_snapshot_sha256: str
    human_intent_confirmed: bool = False
    causation_proven: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = TRANSITION_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_CANDIDATE_SCHEMA_VERSION:
            raise TransitionInferenceContractError(
                "unsupported transition candidate schema"
            )
        _require_text(self.candidate_id, "candidate_id", maximum=512)
        _require_sha256(
            self.before_snapshot_sha256,
            "before_snapshot_sha256",
        )
        _require_sha256(
            self.after_snapshot_sha256,
            "after_snapshot_sha256",
        )
        if self.human_intent_confirmed:
            raise TransitionInferenceContractError(
                "inferred candidate cannot claim confirmed human intent"
            )
        if self.causation_proven:
            raise TransitionInferenceContractError(
                "inferred candidate cannot claim causation"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise TransitionInferenceContractError(
                "TransitionCandidate cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "basis": self.basis.value,
            "expectation": self.expectation.to_dict(),
            "before_snapshot_sha256": self.before_snapshot_sha256,
            "after_snapshot_sha256": self.after_snapshot_sha256,
            "human_intent_confirmed": self.human_intent_confirmed,
            "causation_proven": self.causation_proven,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def candidate_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["candidate_sha256"] = self.candidate_sha256
        return payload


@dataclass(frozen=True, slots=True)
class TransitionInferenceReceipt:
    session_id: str
    action_observation_sha256: str
    before_snapshot_sha256: str
    after_snapshot_sha256: str
    status: TransitionInferenceStatus
    candidates: tuple[TransitionCandidate, ...]
    inferred_at: str
    human_intent_confirmed: bool = False
    causation_proven: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = TRANSITION_INFERENCE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_INFERENCE_RECEIPT_SCHEMA_VERSION:
            raise TransitionInferenceContractError(
                "unsupported transition inference receipt schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.action_observation_sha256,
            "action_observation_sha256",
        )
        _require_sha256(
            self.before_snapshot_sha256,
            "before_snapshot_sha256",
        )
        _require_sha256(
            self.after_snapshot_sha256,
            "after_snapshot_sha256",
        )
        _require_timestamp(self.inferred_at, "inferred_at")
        ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if ids != tuple(sorted(ids)):
            raise TransitionInferenceContractError(
                "transition candidates must be sorted by candidate_id"
            )
        if len(set(ids)) != len(ids):
            raise TransitionInferenceContractError(
                "transition candidate IDs must be unique"
            )
        if (
            self.status is TransitionInferenceStatus.CANDIDATES
            and not self.candidates
        ):
            raise TransitionInferenceContractError(
                "CANDIDATES status requires at least one candidate"
            )
        if (
            self.status is not TransitionInferenceStatus.CANDIDATES
            and self.candidates
        ):
            raise TransitionInferenceContractError(
                "non-candidate status cannot carry candidates"
            )
        if self.human_intent_confirmed or self.causation_proven:
            raise TransitionInferenceContractError(
                "inference receipt cannot claim intent or causation"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise TransitionInferenceContractError(
                "TransitionInferenceReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "action_observation_sha256": (
                self.action_observation_sha256
            ),
            "before_snapshot_sha256": self.before_snapshot_sha256,
            "after_snapshot_sha256": self.after_snapshot_sha256,
            "status": self.status.value,
            "candidates": [
                candidate.to_dict()
                for candidate in self.candidates
            ],
            "inferred_at": self.inferred_at,
            "human_intent_confirmed": self.human_intent_confirmed,
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


class GhostWalkTransitionInferer:
    """Deterministic zero-authority before/after difference engine."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise TransitionInferenceContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger

    def infer(
        self,
        *,
        before: GhostWalkUiStateSnapshot,
        after: GhostWalkUiStateSnapshot,
        inferred_at: str,
    ) -> TransitionInferenceReceipt:
        inferred_at = _require_timestamp(inferred_at, "inferred_at")
        self._validate_pair(before=before, after=after)
        self._ledger.append_ghostwalk_state_snapshot(before)
        self._ledger.append_ghostwalk_state_snapshot(after)

        if before.process_id != after.process_id:
            receipt = TransitionInferenceReceipt(
                session_id=before.session_id,
                action_observation_sha256=(
                    before.action_observation_sha256
                ),
                before_snapshot_sha256=before.snapshot_sha256,
                after_snapshot_sha256=after.snapshot_sha256,
                status=TransitionInferenceStatus.SCOPE_CHANGED,
                candidates=(),
                inferred_at=inferred_at,
            )
            self._ledger.append_transition_inference_receipt(receipt)
            return receipt

        candidates: list[TransitionCandidate] = []

        if before.window_title_sha256 != after.window_title_sha256:
            candidates.append(
                self._candidate(
                    candidate_id="window-title-changed",
                    basis=TransitionBasis.WINDOW_TITLE_CHANGED,
                    expectation=PostActionExpectation(
                        kind=(
                            PostActionExpectationKind.WINDOW_TITLE_CHANGED
                        ),
                        expected_process_id=after.process_id,
                        source_window_title_sha256=(
                            before.window_title_sha256
                        ),
                    ),
                    before=before,
                    after=after,
                )
            )

        before_targets = {
            target.target_sha256: target
            for target in before.semantic_targets
        }
        after_targets = {
            target.target_sha256: target
            for target in after.semantic_targets
        }

        for target_sha in sorted(after_targets.keys() - before_targets.keys()):
            target = after_targets[target_sha]
            candidates.append(
                self._candidate(
                    candidate_id=f"semantic-present:{target_sha}",
                    basis=TransitionBasis.SEMANTIC_APPEARED,
                    expectation=PostActionExpectation(
                        kind=PostActionExpectationKind.SEMANTIC_PRESENT,
                        expected_process_id=after.process_id,
                        source_window_title_sha256=(
                            before.window_title_sha256
                        ),
                        expected_window_title_sha256=(
                            after.window_title_sha256
                        ),
                        semantic_target=target,
                    ),
                    before=before,
                    after=after,
                )
            )

        for target_sha in sorted(before_targets.keys() - after_targets.keys()):
            target = before_targets[target_sha]
            candidates.append(
                self._candidate(
                    candidate_id=f"semantic-absent:{target_sha}",
                    basis=TransitionBasis.SEMANTIC_DISAPPEARED,
                    expectation=PostActionExpectation(
                        kind=PostActionExpectationKind.SEMANTIC_ABSENT,
                        expected_process_id=after.process_id,
                        source_window_title_sha256=(
                            before.window_title_sha256
                        ),
                        expected_window_title_sha256=(
                            after.window_title_sha256
                        ),
                        semantic_target=target,
                    ),
                    before=before,
                    after=after,
                )
            )

        ordered = tuple(sorted(candidates, key=lambda item: item.candidate_id))
        status = (
            TransitionInferenceStatus.CANDIDATES
            if ordered
            else TransitionInferenceStatus.NO_OBSERVABLE_CHANGE
        )
        receipt = TransitionInferenceReceipt(
            session_id=before.session_id,
            action_observation_sha256=before.action_observation_sha256,
            before_snapshot_sha256=before.snapshot_sha256,
            after_snapshot_sha256=after.snapshot_sha256,
            status=status,
            candidates=ordered,
            inferred_at=inferred_at,
        )
        self._ledger.append_transition_inference_receipt(receipt)
        return receipt

    def publish_editable_operator_log(
        self,
        *,
        receipt: TransitionInferenceReceipt,
        note_id: str,
        author_id: str,
        created_at: str,
    ) -> OperatorLogRevision:
        """Publish a human-editable summary without mutating inference evidence."""

        created_at = _require_timestamp(created_at, "created_at")
        body = self._operator_log_body(receipt)
        return OperatorLog(self._ledger).create(
            note_id=note_id,
            target_sha256=receipt.receipt_sha256,
            author_id=author_id,
            body=body,
            created_at=created_at,
            tags=(
                "ghostwalk",
                "postcondition-candidates",
                "transition-inference",
            ),
        )

    @staticmethod
    def _validate_pair(
        *,
        before: GhostWalkUiStateSnapshot,
        after: GhostWalkUiStateSnapshot,
    ) -> None:
        if before.phase is not SnapshotPhase.BEFORE:
            raise TransitionInferenceContractError(
                "before snapshot must use BEFORE phase"
            )
        if after.phase is not SnapshotPhase.AFTER:
            raise TransitionInferenceContractError(
                "after snapshot must use AFTER phase"
            )
        if before.session_id != after.session_id:
            raise TransitionInferenceContractError(
                "snapshot session IDs differ"
            )
        if (
            before.action_observation_sha256
            != after.action_observation_sha256
        ):
            raise TransitionInferenceContractError(
                "snapshots refer to different demonstrated actions"
            )
        before_time = datetime.fromisoformat(
            before.observed_at.replace("Z", "+00:00")
        )
        after_time = datetime.fromisoformat(
            after.observed_at.replace("Z", "+00:00")
        )
        if after_time <= before_time:
            raise TransitionInferenceContractError(
                "after snapshot must occur after before snapshot"
            )

    @staticmethod
    def _candidate(
        *,
        candidate_id: str,
        basis: TransitionBasis,
        expectation: PostActionExpectation,
        before: GhostWalkUiStateSnapshot,
        after: GhostWalkUiStateSnapshot,
    ) -> TransitionCandidate:
        return TransitionCandidate(
            candidate_id=candidate_id,
            basis=basis,
            expectation=expectation,
            before_snapshot_sha256=before.snapshot_sha256,
            after_snapshot_sha256=after.snapshot_sha256,
        )

    @staticmethod
    def _operator_log_body(
        receipt: TransitionInferenceReceipt,
    ) -> str:
        lines = [
            "Ghost-Walk inferred postcondition candidates",
            "",
            f"status: {receipt.status.value}",
            f"inference_receipt_sha256: {receipt.receipt_sha256}",
            "human_intent_confirmed: false",
            "causation_proven: false",
            "",
        ]
        if not receipt.candidates:
            lines.append("No candidate postconditions were inferred.")
            return "\n".join(lines)

        lines.append("Candidates:")
        for index, candidate in enumerate(receipt.candidates, start=1):
            target = candidate.expectation.semantic_target
            hint = (
                ""
                if target is None or target.name_hint is None
                else f" name_hint={target.name_hint!r}"
            )
            lines.append(
                f"{index}. {candidate.candidate_id} "
                f"[{candidate.basis.value}] "
                f"expectation={candidate.expectation.kind.value}{hint}"
            )
        lines.extend(
            [
                "",
                "This note is editable human context only.",
                "Editing it does not alter the immutable inference receipt.",
                "No candidate is accepted as human intent by this note alone.",
            ]
        )
        return "\n".join(lines)
