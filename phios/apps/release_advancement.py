from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, cast

from .intake import GitHubRepositoryRef
from .manifest import AppManifest
from .release_compatibility import ReleaseChangeEvidence
from .release_discovery import unwrap_release_candidate_intake
from .release_review import ReleaseChangeAcceptanceRecord

RELEASE_CANDIDATE_ADVANCEMENT_SCHEMA_VERSION = "phios.release_candidate_advancement.v0.1"

_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
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


def _sha(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64).lower()
    if not _SHA_RE.fullmatch(text):
        raise ValueError(f"{label} must be a 40-64 character hexadecimal commit")
    return text


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


@dataclass(frozen=True)
class CandidateChain:
    candidate_intake_sha256: str
    app_id: str
    repository_url: str
    active_version: str
    candidate_version: str
    active_commit_sha: str
    candidate_commit_sha: str
    candidate_manifest_sha256: str


def _candidate_chain(candidate_intake_value: Any) -> CandidateChain:
    payload = _mapping(candidate_intake_value, "release candidate intake")
    intake = unwrap_release_candidate_intake(payload)
    digest = _sha256(
        payload.get("release_candidate_intake_sha256"),
        "release_candidate_intake_sha256",
    )
    selection = _mapping(payload.get("selection"), "release candidate selection")
    manifest_value = intake.get("manifest_candidate")
    if manifest_value is None:
        raise ValueError("release candidate intake has no manifest candidate")
    manifest = AppManifest.from_dict(manifest_value)

    app_id = _string(selection.get("app_id"), "candidate app_id", maximum=64)
    repository_url = GitHubRepositoryRef.parse(
        _string(
            selection.get("repository_url"),
            "candidate repository_url",
            maximum=512,
        )
    ).repository_url
    active_version = _string(
        selection.get("installed_version"),
        "candidate installed_version",
        maximum=128,
    )
    candidate_commit = _sha(
        selection.get("commit_sha"),
        "candidate commit_sha",
    )

    evidence = _mapping(intake.get("evidence"), "candidate intake evidence")
    if _sha(evidence.get("head_sha"), "candidate intake head_sha") != candidate_commit:
        raise ValueError("candidate intake head SHA does not match selected commit")
    if manifest.app_id != app_id:
        raise ValueError("candidate manifest app_id does not match selection")
    if (
        GitHubRepositoryRef.parse(manifest.source.repository_url)
        .repository_url.lower()
        != repository_url.lower()
    ):
        raise ValueError("candidate manifest repository does not match selection")

    return CandidateChain(
        candidate_intake_sha256=digest,
        app_id=app_id,
        repository_url=repository_url,
        active_version=active_version,
        candidate_version=manifest.version,
        active_commit_sha="",
        candidate_commit_sha=candidate_commit,
        candidate_manifest_sha256=manifest.sha256(),
    )


@dataclass(frozen=True)
class ReleaseCandidateAdvancementRecord:
    release_candidate_intake_sha256: str
    release_change_evidence_sha256: str
    release_change_acceptance_sha256: str
    app_id: str
    repository_url: str
    active_version: str
    candidate_version: str
    active_commit_sha: str
    candidate_commit_sha: str
    candidate_manifest_sha256: str
    advancement_state: str = "human_review_prerequisite_satisfied"
    advancement_scope: str = "build_planning_only"
    compatibility_verdict: str = "not_assessed"
    acquisition_authority: bool = False
    build_execution_authority: bool = False
    install_authority: bool = False
    update_authority: bool = False
    schema_version: str = RELEASE_CANDIDATE_ADVANCEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_CANDIDATE_ADVANCEMENT_SCHEMA_VERSION:
            raise ValueError("unsupported release candidate advancement schema")
        _sha256(
            self.release_candidate_intake_sha256,
            "release_candidate_intake_sha256",
        )
        _sha256(
            self.release_change_evidence_sha256,
            "release_change_evidence_sha256",
        )
        _sha256(
            self.release_change_acceptance_sha256,
            "release_change_acceptance_sha256",
        )
        _string(self.app_id, "app_id", maximum=64)
        GitHubRepositoryRef.parse(self.repository_url)
        _string(self.active_version, "active_version", maximum=128)
        _string(self.candidate_version, "candidate_version", maximum=128)
        _sha(self.active_commit_sha, "active_commit_sha")
        _sha(self.candidate_commit_sha, "candidate_commit_sha")
        _sha256(self.candidate_manifest_sha256, "candidate_manifest_sha256")
        if self.advancement_state != "human_review_prerequisite_satisfied":
            raise ValueError("unsupported advancement_state")
        if self.advancement_scope != "build_planning_only":
            raise ValueError("unsupported advancement_scope")
        if self.compatibility_verdict != "not_assessed":
            raise ValueError("v0.47 does not issue a compatibility verdict")
        if any(
            not isinstance(value, bool)
            for value in (
                self.acquisition_authority,
                self.build_execution_authority,
                self.install_authority,
                self.update_authority,
            )
        ):
            raise ValueError("v0.47 authority fields must be boolean")
        if (
            self.acquisition_authority
            or self.build_execution_authority
            or self.install_authority
            or self.update_authority
        ):
            raise ValueError("v0.47 advancement grants no mutation authority")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_candidate_advancement_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseCandidateAdvancementRecord:
        data = _mapping(value, "release candidate advancement")
        expected = {
            "schema_version",
            "release_candidate_intake_sha256",
            "release_change_evidence_sha256",
            "release_change_acceptance_sha256",
            "app_id",
            "repository_url",
            "active_version",
            "candidate_version",
            "active_commit_sha",
            "candidate_commit_sha",
            "candidate_manifest_sha256",
            "advancement_state",
            "advancement_scope",
            "compatibility_verdict",
            "acquisition_authority",
            "build_execution_authority",
            "install_authority",
            "update_authority",
            "release_candidate_advancement_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "release candidate advancement contains missing or unknown fields"
            )
        for field in (
            "acquisition_authority",
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
            release_candidate_intake_sha256=_sha256(
                data["release_candidate_intake_sha256"],
                "release_candidate_intake_sha256",
            ),
            release_change_evidence_sha256=_sha256(
                data["release_change_evidence_sha256"],
                "release_change_evidence_sha256",
            ),
            release_change_acceptance_sha256=_sha256(
                data["release_change_acceptance_sha256"],
                "release_change_acceptance_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "repository_url",
                maximum=512,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            candidate_version=_string(
                data["candidate_version"],
                "candidate_version",
                maximum=128,
            ),
            active_commit_sha=_sha(
                data["active_commit_sha"],
                "active_commit_sha",
            ),
            candidate_commit_sha=_sha(
                data["candidate_commit_sha"],
                "candidate_commit_sha",
            ),
            candidate_manifest_sha256=_sha256(
                data["candidate_manifest_sha256"],
                "candidate_manifest_sha256",
            ),
            advancement_state=_string(
                data["advancement_state"],
                "advancement_state",
                maximum=64,
            ),
            advancement_scope=_string(
                data["advancement_scope"],
                "advancement_scope",
                maximum=64,
            ),
            compatibility_verdict=_string(
                data["compatibility_verdict"],
                "compatibility_verdict",
                maximum=32,
            ),
            acquisition_authority=data["acquisition_authority"],
            build_execution_authority=data["build_execution_authority"],
            install_authority=data["install_authority"],
            update_authority=data["update_authority"],
        )
        if data["release_candidate_advancement_sha256"] != record.sha256():
            raise ValueError(
                "release candidate advancement digest does not match canonical record"
            )
        return record


def _verify_chain(
    candidate_intake_value: Any,
    change_evidence_value: Any,
    acceptance_value: Any,
) -> tuple[CandidateChain, ReleaseChangeEvidence, ReleaseChangeAcceptanceRecord]:
    candidate = _candidate_chain(candidate_intake_value)
    evidence = ReleaseChangeEvidence.from_dict(change_evidence_value)
    acceptance = ReleaseChangeAcceptanceRecord.from_dict(acceptance_value)

    if evidence.release_candidate_intake_sha256 != candidate.candidate_intake_sha256:
        raise ValueError("v0.45 evidence does not bind the supplied v0.44 candidate intake")
    if acceptance.release_change_evidence_sha256 != evidence.sha256():
        raise ValueError("v0.46 acceptance does not bind the supplied v0.45 evidence")

    if evidence.app_id != candidate.app_id or acceptance.app_id != candidate.app_id:
        raise ValueError("release advancement app_id chain mismatch")
    if (
        GitHubRepositoryRef.parse(evidence.repository_url).repository_url.lower()
        != candidate.repository_url.lower()
        or GitHubRepositoryRef.parse(acceptance.repository_url).repository_url.lower()
        != candidate.repository_url.lower()
    ):
        raise ValueError("release advancement repository chain mismatch")

    if evidence.active_version != candidate.active_version:
        raise ValueError("v0.45 active version does not match v0.44 installed version")
    if acceptance.active_version != evidence.active_version:
        raise ValueError("v0.46 active version does not match v0.45 evidence")
    if evidence.candidate_version != candidate.candidate_version:
        raise ValueError("v0.45 candidate version does not match v0.44 candidate manifest")
    if acceptance.candidate_version != evidence.candidate_version:
        raise ValueError("v0.46 candidate version does not match v0.45 evidence")

    if evidence.candidate_commit_sha != candidate.candidate_commit_sha:
        raise ValueError("v0.45 candidate commit does not match v0.44 selection")
    if acceptance.candidate_commit_sha != evidence.candidate_commit_sha:
        raise ValueError("v0.46 candidate commit does not match v0.45 evidence")
    if acceptance.active_commit_sha != evidence.active_commit_sha:
        raise ValueError("v0.46 active commit does not match v0.45 evidence")
    if evidence.candidate_manifest_sha256 != candidate.candidate_manifest_sha256:
        raise ValueError("v0.45 candidate manifest digest does not match v0.44 candidate")

    candidate = CandidateChain(
        candidate_intake_sha256=candidate.candidate_intake_sha256,
        app_id=candidate.app_id,
        repository_url=candidate.repository_url,
        active_version=candidate.active_version,
        candidate_version=candidate.candidate_version,
        active_commit_sha=evidence.active_commit_sha,
        candidate_commit_sha=candidate.candidate_commit_sha,
        candidate_manifest_sha256=candidate.candidate_manifest_sha256,
    )
    return candidate, evidence, acceptance


def advance_release_candidate(
    candidate_intake_value: Any,
    change_evidence_value: Any,
    acceptance_value: Any,
    *,
    approved_release_change_acceptance_sha256: str,
) -> ReleaseCandidateAdvancementRecord:
    candidate, evidence, acceptance = _verify_chain(
        candidate_intake_value,
        change_evidence_value,
        acceptance_value,
    )
    approved = _sha256(
        approved_release_change_acceptance_sha256,
        "approved_release_change_acceptance_sha256",
    )
    if approved != acceptance.sha256():
        raise ValueError(
            "approved release change acceptance digest does not match acceptance"
        )
    return ReleaseCandidateAdvancementRecord(
        release_candidate_intake_sha256=candidate.candidate_intake_sha256,
        release_change_evidence_sha256=evidence.sha256(),
        release_change_acceptance_sha256=acceptance.sha256(),
        app_id=candidate.app_id,
        repository_url=candidate.repository_url,
        active_version=candidate.active_version,
        candidate_version=candidate.candidate_version,
        active_commit_sha=candidate.active_commit_sha,
        candidate_commit_sha=candidate.candidate_commit_sha,
        candidate_manifest_sha256=candidate.candidate_manifest_sha256,
    )


def validate_release_candidate_advancement(
    candidate_intake_value: Any,
    change_evidence_value: Any,
    acceptance_value: Any,
    advancement_value: Any,
    *,
    approved_release_candidate_advancement_sha256: str,
) -> ReleaseCandidateAdvancementRecord:
    advancement = ReleaseCandidateAdvancementRecord.from_dict(advancement_value)
    approved = _sha256(
        approved_release_candidate_advancement_sha256,
        "approved_release_candidate_advancement_sha256",
    )
    if approved != advancement.sha256():
        raise ValueError(
            "approved release candidate advancement digest does not match advancement"
        )

    candidate, evidence, acceptance = _verify_chain(
        candidate_intake_value,
        change_evidence_value,
        acceptance_value,
    )
    expected = ReleaseCandidateAdvancementRecord(
        release_candidate_intake_sha256=candidate.candidate_intake_sha256,
        release_change_evidence_sha256=evidence.sha256(),
        release_change_acceptance_sha256=acceptance.sha256(),
        app_id=candidate.app_id,
        repository_url=candidate.repository_url,
        active_version=candidate.active_version,
        candidate_version=candidate.candidate_version,
        active_commit_sha=candidate.active_commit_sha,
        candidate_commit_sha=candidate.candidate_commit_sha,
        candidate_manifest_sha256=candidate.candidate_manifest_sha256,
    )
    if advancement != expected:
        raise ValueError(
            "release candidate advancement does not match the supplied review chain"
        )
    return advancement
