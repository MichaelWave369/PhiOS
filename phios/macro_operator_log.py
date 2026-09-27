"""Versioned editable operator annotations for Macro Runtime v0.12.

Operator notes are editable by appending revisions. They never rewrite Reality
Ledger execution evidence and never carry execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from phios.spine.ledger import RealityLedger

OPERATOR_LOG_SCHEMA_VERSION = "phios.operator_log_revision.v0.12"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class OperatorLogContractError(ValueError):
    """Raised when an operator-log revision chain cannot be trusted."""


class OperatorNoteStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETRACTED = "RETRACTED"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 16384,
) -> str:
    if not isinstance(value, str) or not value:
        raise OperatorLogContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise OperatorLogContractError(
            f"{field} exceeds {maximum} characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise OperatorLogContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperatorLogContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise OperatorLogContractError(
            f"{field} must include a timezone"
        )
    return text


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise OperatorLogContractError(
            f"{field} must be Boolean"
        )
    return value


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
        raise OperatorLogContractError(
            "operator log payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OperatorLogRevision:
    note_id: str
    revision: int
    target_sha256: str
    author_id: str
    body: str
    tags: tuple[str, ...]
    status: OperatorNoteStatus
    created_at: str
    supersedes_revision_sha256: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = OPERATOR_LOG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OPERATOR_LOG_SCHEMA_VERSION:
            raise OperatorLogContractError(
                "unsupported operator log schema"
            )
        _require_text(self.note_id, "note_id", maximum=512)
        if isinstance(self.revision, bool) or not isinstance(
            self.revision,
            int,
        ):
            raise OperatorLogContractError("revision must be an integer")
        if self.revision < 1:
            raise OperatorLogContractError("revision must be positive")
        _require_sha256(self.target_sha256, "target_sha256")
        _require_text(self.author_id, "author_id", maximum=512)
        _require_text(self.body, "body")
        normalized_tags = tuple(
            _require_text(tag, "tag", maximum=128)
            for tag in self.tags
        )
        if tuple(sorted(set(normalized_tags))) != normalized_tags:
            raise OperatorLogContractError(
                "tags must be sorted and unique"
            )
        _require_timestamp(self.created_at, "created_at")
        if self.revision == 1:
            if self.supersedes_revision_sha256 is not None:
                raise OperatorLogContractError(
                    "first revision cannot supersede prior history"
                )
        else:
            if self.supersedes_revision_sha256 is None:
                raise OperatorLogContractError(
                    "edited revision must supersede prior revision"
                )
            _require_sha256(
                self.supersedes_revision_sha256,
                "supersedes_revision_sha256",
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise OperatorLogContractError(
                "OperatorLogRevision cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "note_id": self.note_id,
            "revision": self.revision,
            "target_sha256": self.target_sha256,
            "author_id": self.author_id,
            "body": self.body,
            "tags": list(self.tags),
            "status": self.status.value,
            "created_at": self.created_at,
            "supersedes_revision_sha256": (
                self.supersedes_revision_sha256
            ),
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
    ) -> "OperatorLogRevision":
        claimed = _require_sha256(
            payload.get("revision_sha256"),
            "revision_sha256",
        )
        tags_raw = payload.get("tags")
        if not isinstance(tags_raw, list) or not all(
            isinstance(item, str) for item in tags_raw
        ):
            raise OperatorLogContractError("tags must be a string list")
        try:
            status = OperatorNoteStatus(
                _require_text(payload.get("status"), "status", maximum=64)
            )
        except ValueError as exc:
            raise OperatorLogContractError(
                "operator note status is unsupported"
            ) from exc
        revision_raw = payload.get("revision")
        if isinstance(revision_raw, bool) or not isinstance(
            revision_raw,
            int,
        ):
            raise OperatorLogContractError("revision must be an integer")
        previous_raw = payload.get("supersedes_revision_sha256")
        revision = cls(
            note_id=_require_text(
                payload.get("note_id"),
                "note_id",
                maximum=512,
            ),
            revision=revision_raw,
            target_sha256=_require_sha256(
                payload.get("target_sha256"),
                "target_sha256",
            ),
            author_id=_require_text(
                payload.get("author_id"),
                "author_id",
                maximum=512,
            ),
            body=_require_text(payload.get("body"), "body"),
            tags=tuple(tags_raw),
            status=status,
            created_at=_require_timestamp(
                payload.get("created_at"),
                "created_at",
            ),
            supersedes_revision_sha256=(
                None
                if previous_raw is None
                else _require_sha256(
                    previous_raw,
                    "supersedes_revision_sha256",
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
            ),
        )
        if revision.revision_sha256 != claimed:
            raise OperatorLogContractError(
                "operator log revision hash mismatch"
            )
        return revision


class OperatorLog:
    """Append-only revision manager for editable human context."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise OperatorLogContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger

    def create(
        self,
        *,
        note_id: str,
        target_sha256: str,
        author_id: str,
        body: str,
        created_at: str,
        tags: tuple[str, ...] = (),
    ) -> OperatorLogRevision:
        if self._ledger.operator_log_revisions(note_id=note_id):
            raise OperatorLogContractError("note_id already exists")
        revision = OperatorLogRevision(
            note_id=note_id,
            revision=1,
            target_sha256=target_sha256,
            author_id=author_id,
            body=body,
            tags=tuple(sorted(set(tags))),
            status=OperatorNoteStatus.ACTIVE,
            created_at=created_at,
            supersedes_revision_sha256=None,
        )
        self._ledger.append_operator_log_revision(revision)
        return revision

    def current(self, *, note_id: str) -> OperatorLogRevision:
        revisions = self._load_chain(note_id)
        if not revisions:
            raise OperatorLogContractError("operator note does not exist")
        return revisions[-1]

    def edit(
        self,
        *,
        note_id: str,
        expected_current_revision_sha256: str,
        author_id: str,
        body: str,
        created_at: str,
        tags: tuple[str, ...] = (),
        status: OperatorNoteStatus = OperatorNoteStatus.ACTIVE,
    ) -> OperatorLogRevision:
        current = self.current(note_id=note_id)
        _require_sha256(
            expected_current_revision_sha256,
            "expected_current_revision_sha256",
        )
        if (
            current.revision_sha256
            != expected_current_revision_sha256
        ):
            raise OperatorLogContractError(
                "operator note revision changed before edit"
            )
        revision = OperatorLogRevision(
            note_id=current.note_id,
            revision=current.revision + 1,
            target_sha256=current.target_sha256,
            author_id=author_id,
            body=body,
            tags=tuple(sorted(set(tags))),
            status=status,
            created_at=created_at,
            supersedes_revision_sha256=current.revision_sha256,
        )
        self._ledger.append_operator_log_revision(revision)
        return revision

    def _load_chain(
        self,
        note_id: str,
    ) -> list[OperatorLogRevision]:
        rows = self._ledger.operator_log_revisions(note_id=note_id)
        revisions = [
            OperatorLogRevision.from_dict(row)
            for row in rows
        ]
        previous: OperatorLogRevision | None = None
        for expected_revision, item in enumerate(revisions, start=1):
            if item.note_id != note_id:
                raise OperatorLogContractError(
                    "operator note identity changed in revision chain"
                )
            if item.revision != expected_revision:
                raise OperatorLogContractError(
                    "operator note revisions are not contiguous"
                )
            if previous is not None:
                if item.target_sha256 != previous.target_sha256:
                    raise OperatorLogContractError(
                        "operator note target changed across revisions"
                    )
                if (
                    item.supersedes_revision_sha256
                    != previous.revision_sha256
                ):
                    raise OperatorLogContractError(
                        "operator note revision chain mismatch"
                    )
            previous = item
        return revisions
