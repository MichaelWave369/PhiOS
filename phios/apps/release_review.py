from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .release_compatibility import ReleaseChangeEvidence

RELEASE_CHANGE_ACCEPTANCE_SCHEMA_VERSION = "phios.release_change_acceptance.v0.1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MARKER_CHANGE_TYPES = {"added", "removed", "changed", "type_changed"}


def _string(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _optional_note(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("review note must be string or null")
    if len(value) > 512:
        raise ValueError("review note exceeds 512 characters")
    if any(ord(char) < 32 and char not in {"\n", "\t"} for char in value):
        raise ValueError("review note contains unsupported control characters")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _unique_sorted(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    normalized = tuple(sorted(values))
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} contains duplicate acknowledgements")
    return normalized


@dataclass(frozen=True, order=True)
class MarkerChangeAcknowledgement:
    path: str
    change: str

    def __post_init__(self) -> None:
        _string(self.path, "marker acknowledgement path", maximum=256)
        if self.change not in _ALLOWED_MARKER_CHANGE_TYPES:
            raise ValueError(
                "marker acknowledgement change must be added, removed, changed, or type_changed"
            )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> MarkerChangeAcknowledgement:
        if not isinstance(value, dict):
            raise ValueError("marker acknowledgement must be an object")
        if set(value) != {"path", "change"}:
            raise ValueError(
                "marker acknowledgement contains missing or unknown fields"
            )
        return cls(
            path=_string(
                value["path"],
                "marker acknowledgement path",
                maximum=256,
            ),
            change=_string(
                value["change"],
                "marker acknowledgement change",
                maximum=32,
            ),
        )

    @classmethod
    def from_text(cls, value: str) -> MarkerChangeAcknowledgement:
        text = _string(value, "marker acknowledgement", maximum=320)
        if "=" not in text:
            raise ValueError(
                "marker acknowledgement must use PATH=CHANGE syntax"
            )
        path, change = text.rsplit("=", 1)
        return cls(path=path, change=change)


@dataclass(frozen=True)
class ReleaseChangeAcceptanceRecord:
    release_change_evidence_sha256: str
    app_id: str
    repository_url: str
    active_version: str
    candidate_version: str
    active_commit_sha: str
    candidate_commit_sha: str
    acknowledged_manifest_changes: tuple[str, ...]
    acknowledged_permissions_added: tuple[str, ...]
    acknowledged_permissions_removed: tuple[str, ...]
    acknowledged_source_marker_changes: tuple[MarkerChangeAcknowledgement, ...]
    review_note: str | None = None
    review_scope: str = "observed_changes_only"
    review_state: str = "accepted_for_further_review"
    compatibility_verdict: str = "not_assessed"
    permission_grant_authority: bool = False
    build_authority: bool = False
    install_authority: bool = False
    update_authority: bool = False
    schema_version: str = RELEASE_CHANGE_ACCEPTANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_CHANGE_ACCEPTANCE_SCHEMA_VERSION:
            raise ValueError("unsupported release change acceptance schema")
        _sha256(
            self.release_change_evidence_sha256,
            "release_change_evidence_sha256",
        )
        _string(self.app_id, "app_id", maximum=64)
        _string(self.repository_url, "repository_url", maximum=512)
        _string(self.active_version, "active_version", maximum=128)
        _string(self.candidate_version, "candidate_version", maximum=128)
        _string(self.active_commit_sha, "active_commit_sha", maximum=64)
        _string(self.candidate_commit_sha, "candidate_commit_sha", maximum=64)
        if self.review_scope != "observed_changes_only":
            raise ValueError("v0.46 review scope must be observed_changes_only")
        if self.review_state != "accepted_for_further_review":
            raise ValueError(
                "v0.46 review state must be accepted_for_further_review"
            )
        if self.compatibility_verdict != "not_assessed":
            raise ValueError("v0.46 does not issue a compatibility verdict")
        _optional_note(self.review_note)
        if any(
            not isinstance(value, bool)
            for value in (
                self.permission_grant_authority,
                self.build_authority,
                self.install_authority,
                self.update_authority,
            )
        ):
            raise ValueError("v0.46 authority fields must be boolean")
        if (
            self.permission_grant_authority
            or self.build_authority
            or self.install_authority
            or self.update_authority
        ):
            raise ValueError("v0.46 acceptance grants no mutation authority")
        for values, label in (
            (
                self.acknowledged_manifest_changes,
                "acknowledged_manifest_changes",
            ),
            (
                self.acknowledged_permissions_added,
                "acknowledged_permissions_added",
            ),
            (
                self.acknowledged_permissions_removed,
                "acknowledged_permissions_removed",
            ),
        ):
            if values != _unique_sorted(values, label):
                raise ValueError(f"{label} must be canonically sorted")
        marker_pairs = tuple(
            f"{item.path}={item.change}"
            for item in self.acknowledged_source_marker_changes
        )
        if marker_pairs != _unique_sorted(
            marker_pairs,
            "acknowledged_source_marker_changes",
        ):
            raise ValueError(
                "acknowledged_source_marker_changes must be canonically sorted"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "release_change_evidence_sha256": self.release_change_evidence_sha256,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "active_version": self.active_version,
            "candidate_version": self.candidate_version,
            "active_commit_sha": self.active_commit_sha,
            "candidate_commit_sha": self.candidate_commit_sha,
            "acknowledged_manifest_changes": list(
                self.acknowledged_manifest_changes
            ),
            "acknowledged_permissions_added": list(
                self.acknowledged_permissions_added
            ),
            "acknowledged_permissions_removed": list(
                self.acknowledged_permissions_removed
            ),
            "acknowledged_source_marker_changes": [
                item.to_dict()
                for item in self.acknowledged_source_marker_changes
            ],
            "review_note": self.review_note,
            "review_scope": self.review_scope,
            "review_state": self.review_state,
            "compatibility_verdict": self.compatibility_verdict,
            "permission_grant_authority": self.permission_grant_authority,
            "build_authority": self.build_authority,
            "install_authority": self.install_authority,
            "update_authority": self.update_authority,
        }

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_change_acceptance_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseChangeAcceptanceRecord:
        if not isinstance(value, dict):
            raise ValueError("release change acceptance must be an object")
        expected = {
            "schema_version",
            "release_change_evidence_sha256",
            "app_id",
            "repository_url",
            "active_version",
            "candidate_version",
            "active_commit_sha",
            "candidate_commit_sha",
            "acknowledged_manifest_changes",
            "acknowledged_permissions_added",
            "acknowledged_permissions_removed",
            "acknowledged_source_marker_changes",
            "review_note",
            "review_scope",
            "review_state",
            "compatibility_verdict",
            "permission_grant_authority",
            "build_authority",
            "install_authority",
            "update_authority",
            "release_change_acceptance_sha256",
        }
        if set(value) != expected:
            raise ValueError(
                "release change acceptance contains missing or unknown fields"
            )
        list_fields = (
            "acknowledged_manifest_changes",
            "acknowledged_permissions_added",
            "acknowledged_permissions_removed",
            "acknowledged_source_marker_changes",
        )
        for field in list_fields:
            if not isinstance(value[field], list):
                raise ValueError(f"{field} must be an array")
        for field in (
            "permission_grant_authority",
            "build_authority",
            "install_authority",
            "update_authority",
        ):
            if not isinstance(value[field], bool):
                raise ValueError(f"{field} must be boolean")
        record = cls(
            schema_version=_string(
                value["schema_version"],
                "release change acceptance schema_version",
                maximum=64,
            ),
            release_change_evidence_sha256=_sha256(
                value["release_change_evidence_sha256"],
                "release_change_evidence_sha256",
            ),
            app_id=_string(value["app_id"], "app_id", maximum=64),
            repository_url=_string(
                value["repository_url"],
                "repository_url",
                maximum=512,
            ),
            active_version=_string(
                value["active_version"],
                "active_version",
                maximum=128,
            ),
            candidate_version=_string(
                value["candidate_version"],
                "candidate_version",
                maximum=128,
            ),
            active_commit_sha=_string(
                value["active_commit_sha"],
                "active_commit_sha",
                maximum=64,
            ),
            candidate_commit_sha=_string(
                value["candidate_commit_sha"],
                "candidate_commit_sha",
                maximum=64,
            ),
            acknowledged_manifest_changes=tuple(
                _string(item, "acknowledged manifest change", maximum=64)
                for item in value["acknowledged_manifest_changes"]
            ),
            acknowledged_permissions_added=tuple(
                _string(item, "acknowledged added permission", maximum=128)
                for item in value["acknowledged_permissions_added"]
            ),
            acknowledged_permissions_removed=tuple(
                _string(item, "acknowledged removed permission", maximum=128)
                for item in value["acknowledged_permissions_removed"]
            ),
            acknowledged_source_marker_changes=tuple(
                MarkerChangeAcknowledgement.from_dict(item)
                for item in value["acknowledged_source_marker_changes"]
            ),
            review_note=_optional_note(value["review_note"]),
            review_scope=_string(
                value["review_scope"],
                "review_scope",
                maximum=64,
            ),
            review_state=_string(
                value["review_state"],
                "review_state",
                maximum=64,
            ),
            compatibility_verdict=_string(
                value["compatibility_verdict"],
                "compatibility_verdict",
                maximum=32,
            ),
            permission_grant_authority=value["permission_grant_authority"],
            build_authority=value["build_authority"],
            install_authority=value["install_authority"],
            update_authority=value["update_authority"],
        )
        if value["release_change_acceptance_sha256"] != record.sha256():
            raise ValueError(
                "release change acceptance digest does not match canonical record"
            )
        return record


def accept_release_change_evidence(
    evidence_value: Any,
    *,
    approved_release_change_evidence_sha256: str,
    acknowledged_manifest_changes: tuple[str, ...] = (),
    acknowledged_permissions_added: tuple[str, ...] = (),
    acknowledged_permissions_removed: tuple[str, ...] = (),
    acknowledged_source_marker_changes: tuple[
        MarkerChangeAcknowledgement, ...
    ] = (),
    review_note: str | None = None,
) -> ReleaseChangeAcceptanceRecord:
    evidence = ReleaseChangeEvidence.from_dict(evidence_value)
    approved = _sha256(
        approved_release_change_evidence_sha256,
        "approved_release_change_evidence_sha256",
    )
    if approved != evidence.sha256():
        raise ValueError(
            "approved release change evidence digest does not match evidence"
        )

    expected_manifest = tuple(sorted(evidence.manifest_changes))
    supplied_manifest = _unique_sorted(
        acknowledged_manifest_changes,
        "acknowledged_manifest_changes",
    )
    if supplied_manifest != expected_manifest:
        raise ValueError(
            "manifest change acknowledgements must exactly match observed changes"
        )

    expected_added = tuple(sorted(evidence.permissions_added))
    supplied_added = _unique_sorted(
        acknowledged_permissions_added,
        "acknowledged_permissions_added",
    )
    if supplied_added != expected_added:
        raise ValueError(
            "added-permission acknowledgements must exactly match observed additions"
        )

    expected_removed = tuple(sorted(evidence.permissions_removed))
    supplied_removed = _unique_sorted(
        acknowledged_permissions_removed,
        "acknowledged_permissions_removed",
    )
    if supplied_removed != expected_removed:
        raise ValueError(
            "removed-permission acknowledgements must exactly match observed removals"
        )

    expected_markers = tuple(
        sorted(
            MarkerChangeAcknowledgement(path=item.path, change=item.change)
            for item in evidence.source_marker_changes
            if item.change != "unchanged"
        )
    )
    supplied_markers = tuple(sorted(acknowledged_source_marker_changes))
    supplied_marker_pairs = tuple(
        f"{item.path}={item.change}" for item in supplied_markers
    )
    _unique_sorted(
        supplied_marker_pairs,
        "acknowledged_source_marker_changes",
    )
    if supplied_markers != expected_markers:
        raise ValueError(
            "source-marker acknowledgements must exactly match observed changes"
        )

    return ReleaseChangeAcceptanceRecord(
        release_change_evidence_sha256=evidence.sha256(),
        app_id=evidence.app_id,
        repository_url=evidence.repository_url,
        active_version=evidence.active_version,
        candidate_version=evidence.candidate_version,
        active_commit_sha=evidence.active_commit_sha,
        candidate_commit_sha=evidence.candidate_commit_sha,
        acknowledged_manifest_changes=supplied_manifest,
        acknowledged_permissions_added=supplied_added,
        acknowledged_permissions_removed=supplied_removed,
        acknowledged_source_marker_changes=supplied_markers,
        review_note=_optional_note(review_note),
    )
