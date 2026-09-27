"""Human-accepted Ghost-Walk intent classifications for Macro Runtime v0.29.

Accepted intent is a separate append-only governance layer. It binds one typed
human declaration to an immutable transition inference and the exact active
OperatorLog revision used to interpret that transition.

Accepted intent is not execution policy and carries no execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_ghostwalk_operator_editor import (
    GhostWalkOperatorEditor,
    GhostWalkOperatorEditorError,
)
from phios.macro_operator_log import (
    OperatorLogContractError,
    OperatorLogRevision,
    OperatorNoteStatus,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_ACCEPTED_INTENT_SCHEMA_VERSION = (
    "phios.ghostwalk_accepted_intent_revision.v0.29"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INTENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


class GhostWalkAcceptedIntentError(ValueError):
    """Raised when accepted-intent evidence or revision history is invalid."""


class GhostWalkIntentFamily(StrEnum):
    NAVIGATE = "NAVIGATE"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    SELECT = "SELECT"
    TOGGLE = "TOGGLE"
    ENTER_TEXT = "ENTER_TEXT"
    SUBMIT = "SUBMIT"
    CONFIRM = "CONFIRM"
    CANCEL = "CANCEL"
    OTHER = "OTHER"


class GhostWalkAcceptedIntentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkAcceptedIntentError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkAcceptedIntentError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkAcceptedIntentError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkAcceptedIntentError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkAcceptedIntentError(
            f"{field} must be Boolean"
        )
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkAcceptedIntentError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkAcceptedIntentError(
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
        raise GhostWalkAcceptedIntentError(
            "accepted-intent payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _require_intent_code(
    family: GhostWalkIntentFamily,
    value: object,
) -> str:
    code = _require_text(value, "intent_code", maximum=128)
    if not _INTENT_CODE_RE.fullmatch(code):
        raise GhostWalkAcceptedIntentError(
            "intent_code must be an uppercase symbolic identifier"
        )
    if family is not GhostWalkIntentFamily.OTHER:
        prefix = f"{family.value}_"
        if not code.startswith(prefix):
            raise GhostWalkAcceptedIntentError(
                f"intent_code for {family.value} must start with {prefix}"
            )
    return code


@dataclass(frozen=True, slots=True)
class GhostWalkAcceptedIntentRevision:
    target_inference_receipt_sha256: str
    source_operator_note_revision_sha256: str
    revision: int
    intent_family: GhostWalkIntentFamily
    intent_code: str
    status: GhostWalkAcceptedIntentStatus
    accepted_by: str
    accepted_at: str
    supersedes_revision_sha256: str | None
    human_intent_confirmed: bool = True
    causation_proven: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_ACCEPTED_INTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_ACCEPTED_INTENT_SCHEMA_VERSION:
            raise GhostWalkAcceptedIntentError(
                "unsupported accepted-intent schema"
            )
        _require_sha256(
            self.target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        _require_sha256(
            self.source_operator_note_revision_sha256,
            "source_operator_note_revision_sha256",
        )
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise GhostWalkAcceptedIntentError(
                "revision must be a positive integer"
            )
        _require_intent_code(self.intent_family, self.intent_code)
        _require_text(self.accepted_by, "accepted_by", maximum=512)
        _require_timestamp(self.accepted_at, "accepted_at")
        if self.revision == 1:
            if self.supersedes_revision_sha256 is not None:
                raise GhostWalkAcceptedIntentError(
                    "first accepted-intent revision cannot supersede history"
                )
        else:
            _require_sha256(
                self.supersedes_revision_sha256,
                "supersedes_revision_sha256",
            )
        if not self.human_intent_confirmed:
            raise GhostWalkAcceptedIntentError(
                "accepted intent must confirm human intent"
            )
        if self.causation_proven:
            raise GhostWalkAcceptedIntentError(
                "accepted intent cannot claim causation"
            )
        if (
            self.policy_authority
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkAcceptedIntentError(
                "accepted intent cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "source_operator_note_revision_sha256": (
                self.source_operator_note_revision_sha256
            ),
            "revision": self.revision,
            "intent_family": self.intent_family.value,
            "intent_code": self.intent_code,
            "status": self.status.value,
            "accepted_by": self.accepted_by,
            "accepted_at": self.accepted_at,
            "supersedes_revision_sha256": (
                self.supersedes_revision_sha256
            ),
            "human_intent_confirmed": self.human_intent_confirmed,
            "causation_proven": self.causation_proven,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def revision_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["revision_sha256"] = self.revision_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkAcceptedIntentRevision":
        claimed = _require_sha256(
            payload.get("revision_sha256"),
            "revision_sha256",
        )
        try:
            family = GhostWalkIntentFamily(
                _require_text(
                    payload.get("intent_family"),
                    "intent_family",
                    maximum=64,
                )
            )
            status = GhostWalkAcceptedIntentStatus(
                _require_text(
                    payload.get("status"),
                    "status",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise GhostWalkAcceptedIntentError(
                "accepted-intent enum value is unsupported"
            ) from exc
        revision_raw = payload.get("revision")
        if (
            isinstance(revision_raw, bool)
            or not isinstance(revision_raw, int)
        ):
            raise GhostWalkAcceptedIntentError(
                "revision must be an integer"
            )
        item = cls(
            target_inference_receipt_sha256=_require_sha256(
                payload.get("target_inference_receipt_sha256"),
                "target_inference_receipt_sha256",
            ),
            source_operator_note_revision_sha256=_require_sha256(
                payload.get("source_operator_note_revision_sha256"),
                "source_operator_note_revision_sha256",
            ),
            revision=revision_raw,
            intent_family=family,
            intent_code=_require_text(
                payload.get("intent_code"),
                "intent_code",
                maximum=128,
            ),
            status=status,
            accepted_by=_require_text(
                payload.get("accepted_by"),
                "accepted_by",
                maximum=512,
            ),
            accepted_at=_require_timestamp(
                payload.get("accepted_at"),
                "accepted_at",
            ),
            supersedes_revision_sha256=_optional_sha256(
                payload.get("supersedes_revision_sha256"),
                "supersedes_revision_sha256",
            ),
            human_intent_confirmed=_require_bool(
                payload.get("human_intent_confirmed"),
                "human_intent_confirmed",
            ),
            causation_proven=_require_bool(
                payload.get("causation_proven"),
                "causation_proven",
            ),
            policy_authority=_require_bool(
                payload.get("policy_authority"),
                "policy_authority",
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
        if item.revision_sha256 != claimed:
            raise GhostWalkAcceptedIntentError(
                "accepted-intent revision hash mismatch"
            )
        return item


class GhostWalkAcceptedIntentRegistry:
    """Append-only typed human intent acceptance, separate from policy."""

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        accepted_by: str,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkAcceptedIntentError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self.accepted_by = _require_text(
            accepted_by,
            "accepted_by",
            maximum=512,
        )
        self._lock = threading.RLock()
        self._operator_editor = GhostWalkOperatorEditor(
            ledger=ledger,
            author_id=accepted_by,
        )

    def current(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAcceptedIntentRevision | None:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        with self._lock:
            chain = self._load_chain(target)
            return chain[-1] if chain else None

    def accept(
        self,
        *,
        target_inference_receipt_sha256: str,
        source_operator_note_revision_sha256: str,
        intent_family: GhostWalkIntentFamily,
        intent_code: str,
        expected_current_revision_sha256: str | None,
        accepted_at: str | None = None,
    ) -> GhostWalkAcceptedIntentRevision:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        source_note = _require_sha256(
            source_operator_note_revision_sha256,
            "source_operator_note_revision_sha256",
        )
        code = _require_intent_code(intent_family, intent_code)
        timestamp = _require_timestamp(
            _utc_now() if accepted_at is None else accepted_at,
            "accepted_at",
        )

        with self._lock:
            note = self._operator_editor.view(
                target_inference_receipt_sha256=target
            )
            if note.status is not OperatorNoteStatus.ACTIVE:
                raise GhostWalkAcceptedIntentError(
                    "accepted intent requires an ACTIVE operator note"
                )
            if note.revision_sha256 != source_note:
                raise GhostWalkAcceptedIntentError(
                    "operator note revision changed before intent acceptance"
                )

            chain = self._load_chain(target)
            current = chain[-1] if chain else None
            if current is None:
                if expected_current_revision_sha256 is not None:
                    raise GhostWalkAcceptedIntentError(
                        "first accepted intent cannot expect prior history"
                    )
                revision = 1
                previous = None
            else:
                expected = _require_sha256(
                    expected_current_revision_sha256,
                    "expected_current_revision_sha256",
                )
                if current.revision_sha256 != expected:
                    raise GhostWalkAcceptedIntentError(
                        "accepted-intent revision changed before update"
                    )
                revision = current.revision + 1
                previous = current.revision_sha256

            item = GhostWalkAcceptedIntentRevision(
                target_inference_receipt_sha256=target,
                source_operator_note_revision_sha256=source_note,
                revision=revision,
                intent_family=intent_family,
                intent_code=code,
                status=GhostWalkAcceptedIntentStatus.ACTIVE,
                accepted_by=self.accepted_by,
                accepted_at=timestamp,
                supersedes_revision_sha256=previous,
            )
            self._ledger.append_ghostwalk_accepted_intent_revision(item)
            return item

    def revoke(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_current_revision_sha256: str,
        accepted_at: str | None = None,
    ) -> GhostWalkAcceptedIntentRevision:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        expected = _require_sha256(
            expected_current_revision_sha256,
            "expected_current_revision_sha256",
        )
        timestamp = _require_timestamp(
            _utc_now() if accepted_at is None else accepted_at,
            "accepted_at",
        )

        with self._lock:
            chain = self._load_chain(target)
            if not chain:
                raise GhostWalkAcceptedIntentError(
                    "accepted intent does not exist"
                )
            current = chain[-1]
            if current.revision_sha256 != expected:
                raise GhostWalkAcceptedIntentError(
                    "accepted-intent revision changed before revoke"
                )
            if current.status is GhostWalkAcceptedIntentStatus.REVOKED:
                raise GhostWalkAcceptedIntentError(
                    "accepted intent is already revoked"
                )
            item = GhostWalkAcceptedIntentRevision(
                target_inference_receipt_sha256=target,
                source_operator_note_revision_sha256=(
                    current.source_operator_note_revision_sha256
                ),
                revision=current.revision + 1,
                intent_family=current.intent_family,
                intent_code=current.intent_code,
                status=GhostWalkAcceptedIntentStatus.REVOKED,
                accepted_by=self.accepted_by,
                accepted_at=timestamp,
                supersedes_revision_sha256=current.revision_sha256,
            )
            self._ledger.append_ghostwalk_accepted_intent_revision(item)
            return item

    def _load_chain(
        self,
        target_sha256: str,
    ) -> list[GhostWalkAcceptedIntentRevision]:
        rows = self._ledger.ghostwalk_accepted_intent_revisions(
            target_inference_receipt_sha256=target_sha256
        )
        revisions = [
            GhostWalkAcceptedIntentRevision.from_dict(row)
            for row in rows
        ]
        previous: GhostWalkAcceptedIntentRevision | None = None
        for expected_revision, item in enumerate(revisions, start=1):
            if item.target_inference_receipt_sha256 != target_sha256:
                raise GhostWalkAcceptedIntentError(
                    "accepted-intent target changed across revisions"
                )
            if item.revision != expected_revision:
                raise GhostWalkAcceptedIntentError(
                    "accepted-intent revisions are not contiguous"
                )
            self._validate_source_operator_note(item)
            if previous is not None:
                if (
                    item.supersedes_revision_sha256
                    != previous.revision_sha256
                ):
                    raise GhostWalkAcceptedIntentError(
                        "accepted-intent revision chain mismatch"
                    )
            previous = item
        return revisions

    def _validate_source_operator_note(
        self,
        intent: GhostWalkAcceptedIntentRevision,
    ) -> None:
        matches = [
            row
            for row in self._ledger.operator_log_revisions()
            if row.get("revision_sha256")
            == intent.source_operator_note_revision_sha256
        ]
        if len(matches) != 1:
            raise GhostWalkAcceptedIntentError(
                "accepted intent source OperatorLog revision is missing or ambiguous"
            )
        try:
            revision = OperatorLogRevision.from_dict(matches[0])
        except OperatorLogContractError as exc:
            raise GhostWalkAcceptedIntentError(
                "accepted intent source OperatorLog revision is invalid"
            ) from exc
        if (
            revision.target_sha256
            != intent.target_inference_receipt_sha256
        ):
            raise GhostWalkAcceptedIntentError(
                "accepted intent source OperatorLog target mismatch"
            )
