from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, cast

from .build_plan import BuildPlan
from .intake import GitHubRepositoryRef
from .release_advancement import ReleaseCandidateAdvancementRecord

RELEASE_BUILD_REVIEW_SCHEMA_VERSION = "phios.release_build_review.v0.1"

_ADVANCEMENT_NOTE_PREFIX = "release_candidate_advancement_sha256="
_ADVANCEMENT_NOTE_RE = re.compile(
    r"(?:^|;\s*)release_candidate_advancement_sha256=([0-9a-f]{64})$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _string(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
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


def release_advancement_sha256_from_plan(plan: BuildPlan) -> str | None:
    matches: list[str] = []
    for note in plan.notes:
        if note.startswith(_ADVANCEMENT_NOTE_PREFIX):
            matches.append(note[len(_ADVANCEMENT_NOTE_PREFIX) :])
            continue
        legacy_match = _ADVANCEMENT_NOTE_RE.search(note)
        if legacy_match is not None:
            matches.append(legacy_match.group(1))
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("build plan contains multiple release advancement bindings")
    return _sha256(matches[0], "build plan release advancement sha256")


@dataclass(frozen=True)
class ReleaseBuildReviewRecord:
    release_candidate_advancement_sha256: str
    build_plan_sha256: str
    app_id: str
    repository_url: str
    commit_sha: str
    manifest_sha256: str
    source_snapshot_sha256: str
    plan_status: str
    strategy: str
    requested_build_permissions: tuple[str, ...]
    review_state: str = "reviewed_for_build_execution_consideration"
    review_scope: str = "exact_release_build_plan"
    compatibility_verdict: str = "not_assessed"
    permission_grant_authority: bool = False
    build_execution_authority: bool = False
    install_authority: bool = False
    update_authority: bool = False
    schema_version: str = RELEASE_BUILD_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_BUILD_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported release build review schema")
        _sha256(
            self.release_candidate_advancement_sha256,
            "release_candidate_advancement_sha256",
        )
        _sha256(self.build_plan_sha256, "build_plan_sha256")
        _string(self.app_id, "app_id", maximum=64)
        GitHubRepositoryRef.parse(self.repository_url)
        _string(self.commit_sha, "commit_sha", maximum=64)
        _sha256(self.manifest_sha256, "manifest_sha256")
        _sha256(self.source_snapshot_sha256, "source_snapshot_sha256")
        _string(self.plan_status, "plan_status", maximum=32)
        _string(self.strategy, "strategy", maximum=64)
        if len(set(self.requested_build_permissions)) != len(
            self.requested_build_permissions
        ):
            raise ValueError("requested_build_permissions must not contain duplicates")
        if tuple(sorted(self.requested_build_permissions)) != self.requested_build_permissions:
            raise ValueError("requested_build_permissions must be canonically sorted")
        for permission in self.requested_build_permissions:
            _string(permission, "requested build permission", maximum=128)

        if self.review_state != "reviewed_for_build_execution_consideration":
            raise ValueError("unsupported release build review state")
        if self.review_scope != "exact_release_build_plan":
            raise ValueError("unsupported release build review scope")
        if self.compatibility_verdict != "not_assessed":
            raise ValueError("v0.48 does not issue a compatibility verdict")
        if any(
            not isinstance(value, bool)
            for value in (
                self.permission_grant_authority,
                self.build_execution_authority,
                self.install_authority,
                self.update_authority,
            )
        ):
            raise ValueError("v0.48 authority fields must be boolean")
        if (
            self.permission_grant_authority
            or self.build_execution_authority
            or self.install_authority
            or self.update_authority
        ):
            raise ValueError("v0.48 review grants no mutation authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "release_candidate_advancement_sha256": (
                self.release_candidate_advancement_sha256
            ),
            "build_plan_sha256": self.build_plan_sha256,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "manifest_sha256": self.manifest_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "plan_status": self.plan_status,
            "strategy": self.strategy,
            "requested_build_permissions": list(self.requested_build_permissions),
            "review_state": self.review_state,
            "review_scope": self.review_scope,
            "compatibility_verdict": self.compatibility_verdict,
            "permission_grant_authority": self.permission_grant_authority,
            "build_execution_authority": self.build_execution_authority,
            "install_authority": self.install_authority,
            "update_authority": self.update_authority,
        }

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_build_review_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseBuildReviewRecord:
        data = _mapping(value, "release build review")
        expected = {
            "schema_version",
            "release_candidate_advancement_sha256",
            "build_plan_sha256",
            "app_id",
            "repository_url",
            "commit_sha",
            "manifest_sha256",
            "source_snapshot_sha256",
            "plan_status",
            "strategy",
            "requested_build_permissions",
            "review_state",
            "review_scope",
            "compatibility_verdict",
            "permission_grant_authority",
            "build_execution_authority",
            "install_authority",
            "update_authority",
            "release_build_review_sha256",
        }
        if set(data) != expected:
            raise ValueError("release build review contains missing or unknown fields")
        permissions = data["requested_build_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("requested_build_permissions must be an array")
        for field in (
            "permission_grant_authority",
            "build_execution_authority",
            "install_authority",
            "update_authority",
        ):
            if not isinstance(data[field], bool):
                raise ValueError(f"{field} must be boolean")

        record = cls(
            schema_version=_string(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            release_candidate_advancement_sha256=_sha256(
                data["release_candidate_advancement_sha256"],
                "release_candidate_advancement_sha256",
            ),
            build_plan_sha256=_sha256(
                data["build_plan_sha256"],
                "build_plan_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            manifest_sha256=_sha256(
                data["manifest_sha256"],
                "manifest_sha256",
            ),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "source_snapshot_sha256",
            ),
            plan_status=_string(
                data["plan_status"],
                "plan_status",
                maximum=32,
            ),
            strategy=_string(data["strategy"], "strategy", maximum=64),
            requested_build_permissions=tuple(
                _string(item, "requested build permission", maximum=128)
                for item in permissions
            ),
            review_state=_string(
                data["review_state"],
                "review_state",
                maximum=64,
            ),
            review_scope=_string(
                data["review_scope"],
                "review_scope",
                maximum=64,
            ),
            compatibility_verdict=_string(
                data["compatibility_verdict"],
                "compatibility_verdict",
                maximum=32,
            ),
            permission_grant_authority=data["permission_grant_authority"],
            build_execution_authority=data["build_execution_authority"],
            install_authority=data["install_authority"],
            update_authority=data["update_authority"],
        )
        if data["release_build_review_sha256"] != record.sha256():
            raise ValueError(
                "release build review digest does not match canonical record"
            )
        return record


def review_release_build_plan(
    plan_value: Any,
    advancement_value: Any,
    *,
    approved_release_candidate_advancement_sha256: str,
) -> ReleaseBuildReviewRecord:
    plan = BuildPlan.from_dict(plan_value)
    advancement = ReleaseCandidateAdvancementRecord.from_dict(advancement_value)
    approved = _sha256(
        approved_release_candidate_advancement_sha256,
        "approved_release_candidate_advancement_sha256",
    )
    if approved != advancement.sha256():
        raise ValueError(
            "approved release candidate advancement digest does not match advancement"
        )

    bound_advancement = release_advancement_sha256_from_plan(plan)
    if bound_advancement is None:
        raise ValueError("build plan does not contain release advancement lineage")
    if bound_advancement != advancement.sha256():
        raise ValueError("build plan release advancement binding does not match advancement")

    if plan.app_id != advancement.app_id:
        raise ValueError("build plan app_id does not match release advancement")
    if (
        GitHubRepositoryRef.parse(plan.repository_url).repository_url.lower()
        != GitHubRepositoryRef.parse(advancement.repository_url).repository_url.lower()
    ):
        raise ValueError("build plan repository does not match release advancement")
    if plan.commit_sha != advancement.candidate_commit_sha:
        raise ValueError("build plan commit does not match release advancement")
    if plan.manifest_sha256 != advancement.candidate_manifest_sha256:
        raise ValueError("build plan manifest digest does not match release advancement")

    return ReleaseBuildReviewRecord(
        release_candidate_advancement_sha256=advancement.sha256(),
        build_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        repository_url=GitHubRepositoryRef.parse(plan.repository_url).repository_url,
        commit_sha=plan.commit_sha,
        manifest_sha256=plan.manifest_sha256,
        source_snapshot_sha256=plan.source_snapshot_sha256,
        plan_status=plan.status,
        strategy=plan.strategy,
        requested_build_permissions=tuple(sorted(plan.requested_build_permissions)),
    )


def validate_release_build_review(
    plan: BuildPlan,
    review_value: Any,
    *,
    approved_release_build_review_sha256: str,
) -> ReleaseBuildReviewRecord:
    review = ReleaseBuildReviewRecord.from_dict(review_value)
    approved = _sha256(
        approved_release_build_review_sha256,
        "approved_release_build_review_sha256",
    )
    if approved != review.sha256():
        raise ValueError(
            "approved release build review digest does not match review"
        )

    bound_advancement = release_advancement_sha256_from_plan(plan)
    if bound_advancement is None:
        raise ValueError("build plan does not contain release advancement lineage")
    if review.release_candidate_advancement_sha256 != bound_advancement:
        raise ValueError("release build review advancement does not match build plan")
    if review.build_plan_sha256 != plan.sha256():
        raise ValueError("release build review does not bind canonical build plan")
    if review.app_id != plan.app_id:
        raise ValueError("release build review app_id does not match build plan")
    if (
        GitHubRepositoryRef.parse(review.repository_url).repository_url.lower()
        != GitHubRepositoryRef.parse(plan.repository_url).repository_url.lower()
    ):
        raise ValueError("release build review repository does not match build plan")
    if review.commit_sha != plan.commit_sha:
        raise ValueError("release build review commit does not match build plan")
    if review.manifest_sha256 != plan.manifest_sha256:
        raise ValueError("release build review manifest digest does not match build plan")
    if review.source_snapshot_sha256 != plan.source_snapshot_sha256:
        raise ValueError("release build review source snapshot does not match build plan")
    if review.plan_status != plan.status:
        raise ValueError("release build review status does not match build plan")
    if review.strategy != plan.strategy:
        raise ValueError("release build review strategy does not match build plan")
    if review.requested_build_permissions != tuple(
        sorted(plan.requested_build_permissions)
    ):
        raise ValueError("release build review permissions do not match build plan")
    return review
