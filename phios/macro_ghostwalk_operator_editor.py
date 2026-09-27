"""Human-governed OperatorLog editing for Ghost-Walk v0.28.

This service edits only the append-only OperatorLog annotation chain attached to
an immutable transition-inference receipt. It never mutates inference evidence,
desktop state, or execution authority.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from phios.macro_operator_log import (
    OperatorLog,
    OperatorLogContractError,
    OperatorLogRevision,
    OperatorNoteStatus,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_OPERATOR_NOTE_SCHEMA_VERSION = (
    "phios.ghostwalk_operator_note.v0.28"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_TAGS = (
    "ghostwalk",
    "operator-interpretation",
    "transition-inference",
)


class GhostWalkOperatorEditorError(ValueError):
    """Raised when a Ghost-Walk annotation edit cannot be trusted."""


class GhostWalkOperatorEditResult(StrEnum):
    APPLIED = "APPLIED"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 16384,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkOperatorEditorError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkOperatorEditorError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise GhostWalkOperatorEditorError(
            f"{field} contains unsupported control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkOperatorEditorError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkOperatorEditorError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkOperatorEditorError(
            f"{field} must include a timezone"
        )
    return text


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GhostWalkOperatorNoteView:
    target_inference_receipt_sha256: str
    note_id: str
    revision: int
    revision_sha256: str
    author_id: str
    body: str
    tags: tuple[str, ...]
    status: OperatorNoteStatus
    created_at: str
    supersedes_revision_sha256: str | None
    inference_status: str
    session_id: str
    action_observation_sha256: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_OPERATOR_NOTE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_OPERATOR_NOTE_SCHEMA_VERSION:
            raise GhostWalkOperatorEditorError(
                "unsupported Ghost-Walk operator-note schema"
            )
        _require_sha256(
            self.target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        _require_text(self.note_id, "note_id", maximum=512)
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise GhostWalkOperatorEditorError(
                "revision must be a positive integer"
            )
        _require_sha256(self.revision_sha256, "revision_sha256")
        _require_text(self.author_id, "author_id", maximum=512)
        _require_text(self.body, "body")
        for tag in self.tags:
            _require_text(tag, "tag", maximum=128)
        if tuple(sorted(set(self.tags))) != self.tags:
            raise GhostWalkOperatorEditorError(
                "tags must be sorted and unique"
            )
        _require_timestamp(self.created_at, "created_at")
        if self.supersedes_revision_sha256 is not None:
            _require_sha256(
                self.supersedes_revision_sha256,
                "supersedes_revision_sha256",
            )
        _require_text(self.inference_status, "inference_status", maximum=64)
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(
            self.action_observation_sha256,
            "action_observation_sha256",
        )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkOperatorEditorError(
                "GhostWalkOperatorNoteView cannot carry authority"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "note_id": self.note_id,
            "revision": self.revision,
            "revision_sha256": self.revision_sha256,
            "author_id": self.author_id,
            "body": self.body,
            "tags": list(self.tags),
            "status": self.status.value,
            "created_at": self.created_at,
            "supersedes_revision_sha256": (
                self.supersedes_revision_sha256
            ),
            "inference_status": self.inference_status,
            "session_id": self.session_id,
            "action_observation_sha256": (
                self.action_observation_sha256
            ),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True, slots=True)
class GhostWalkOperatorEditOutcome:
    result: GhostWalkOperatorEditResult
    note: GhostWalkOperatorNoteView

    def to_dict(self) -> dict[str, object]:
        return {
            "result": self.result.value,
            "note": self.note.to_dict(),
            "annotation_mutation": True,
            "desktop_effect_performed": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }


class GhostWalkOperatorEditor:
    """Serialize append-only human interpretation revisions by inference."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        author_id: str,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkOperatorEditorError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self.author_id = _require_text(
            author_id,
            "author_id",
            maximum=512,
        )
        self._lock = threading.RLock()

    def view(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkOperatorNoteView:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        with self._lock:
            inference = self._inference(target)
            revision = self._current_revision(target)
            return self._view(
                inference=inference,
                revision=revision,
            )

    def edit(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_current_revision_sha256: str,
        body: str,
        status: OperatorNoteStatus = OperatorNoteStatus.ACTIVE,
        created_at: str | None = None,
    ) -> GhostWalkOperatorEditOutcome:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        expected = _require_sha256(
            expected_current_revision_sha256,
            "expected_current_revision_sha256",
        )
        body = _require_text(body, "body")
        timestamp = _require_timestamp(
            _utc_now() if created_at is None else created_at,
            "created_at",
        )

        with self._lock:
            inference = self._inference(target)
            current = self._current_revision(target)
            if current.revision_sha256 != expected:
                raise GhostWalkOperatorEditorError(
                    "operator note revision changed before edit"
                )
            tags = tuple(
                sorted(set(current.tags).union(_REQUIRED_TAGS))
            )
            try:
                revision = OperatorLog(self._ledger).edit(
                    note_id=current.note_id,
                    expected_current_revision_sha256=expected,
                    author_id=self.author_id,
                    body=body,
                    created_at=timestamp,
                    tags=tags,
                    status=status,
                )
            except OperatorLogContractError as exc:
                raise GhostWalkOperatorEditorError(str(exc)) from exc

            return GhostWalkOperatorEditOutcome(
                result=GhostWalkOperatorEditResult.APPLIED,
                note=self._view(
                    inference=inference,
                    revision=revision,
                ),
            )

    def _inference(
        self,
        target_sha256: str,
    ) -> dict[str, object]:
        row = self._ledger.transition_inference_receipt(
            receipt_sha256=target_sha256
        )
        if row is None:
            raise GhostWalkOperatorEditorError(
                "transition inference receipt does not exist"
            )
        return row

    def _current_revision(
        self,
        target_sha256: str,
    ) -> OperatorLogRevision:
        rows = [
            row
            for row in self._ledger.operator_log_revisions()
            if row.get("target_sha256") == target_sha256
        ]
        if not rows:
            raise GhostWalkOperatorEditorError(
                "operator note does not exist for transition inference"
            )

        note_ids = {
            row.get("note_id")
            for row in rows
            if isinstance(row.get("note_id"), str)
        }
        if len(note_ids) != 1:
            raise GhostWalkOperatorEditorError(
                "transition inference has ambiguous operator-note chains"
            )
        note_id = next(iter(note_ids))
        try:
            return OperatorLog(self._ledger).current(note_id=note_id)
        except OperatorLogContractError as exc:
            raise GhostWalkOperatorEditorError(str(exc)) from exc

    @staticmethod
    def _view(
        *,
        inference: dict[str, object],
        revision: OperatorLogRevision,
    ) -> GhostWalkOperatorNoteView:
        status = _require_text(
            inference.get("status"),
            "inference_status",
            maximum=64,
        )
        session_id = _require_text(
            inference.get("session_id"),
            "session_id",
            maximum=512,
        )
        action_observation_sha256 = _require_sha256(
            inference.get("action_observation_sha256"),
            "action_observation_sha256",
        )
        target = _require_sha256(
            inference.get("receipt_sha256"),
            "inference_receipt_sha256",
        )
        if revision.target_sha256 != target:
            raise GhostWalkOperatorEditorError(
                "operator note target does not match inference"
            )
        return GhostWalkOperatorNoteView(
            target_inference_receipt_sha256=target,
            note_id=revision.note_id,
            revision=revision.revision,
            revision_sha256=revision.revision_sha256,
            author_id=revision.author_id,
            body=revision.body,
            tags=revision.tags,
            status=revision.status,
            created_at=revision.created_at,
            supersedes_revision_sha256=(
                revision.supersedes_revision_sha256
            ),
            inference_status=status,
            session_id=session_id,
            action_observation_sha256=action_observation_sha256,
        )
