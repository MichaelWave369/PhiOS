from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, cast

from .package_install import BuildPackagePlan

RELEASE_INSTALL_PROPOSAL_SCHEMA_VERSION = "phios.release_install_proposal.v0.1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_PROPOSAL_STATE = "proposed_for_side_by_side_install_review"
_PROPOSAL_SCOPE = "release_candidate_install_only"


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


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ReleaseInstallProposalRecord:
    package_plan_sha256: str
    release_build_review_sha256: str
    app_id: str
    app_version: str
    repository_url: str
    commit_sha: str
    manifest_sha256: str
    registry_snapshot_sha256: str
    execution_receipt_sha256: str
    offline_build_receipt_sha256: str
    artifact_set_sha256: str
    install_relative_path: str
    proposal_state: str = _PROPOSAL_STATE
    proposal_scope: str = _PROPOSAL_SCOPE
    compatibility_verdict: str = "not_assessed"
    install_authority: bool = False
    launch_authority: bool = False
    update_authority: bool = False
    rollback_authority: bool = False
    schema_version: str = RELEASE_INSTALL_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_INSTALL_PROPOSAL_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported release install proposal schema: {self.schema_version}"
            )
        for value, label in (
            (self.package_plan_sha256, "package_plan_sha256"),
            (self.release_build_review_sha256, "release_build_review_sha256"),
            (self.manifest_sha256, "manifest_sha256"),
            (self.registry_snapshot_sha256, "registry_snapshot_sha256"),
            (self.execution_receipt_sha256, "execution_receipt_sha256"),
            (self.offline_build_receipt_sha256, "offline_build_receipt_sha256"),
            (self.artifact_set_sha256, "artifact_set_sha256"),
        ):
            _sha256(value, label)
        _string(self.app_id, "app_id", maximum=64)
        _string(self.app_version, "app_version", maximum=128)
        _string(self.repository_url, "repository_url", maximum=512)
        if not _COMMIT_RE.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be lowercase hexadecimal")
        _string(self.install_relative_path, "install_relative_path", maximum=1024)
        if self.proposal_state != _PROPOSAL_STATE:
            raise ValueError("unsupported release install proposal state")
        if self.proposal_scope != _PROPOSAL_SCOPE:
            raise ValueError("unsupported release install proposal scope")
        if self.compatibility_verdict != "not_assessed":
            raise ValueError("release install proposal does not assess compatibility")
        if any(
            (
                self.install_authority,
                self.launch_authority,
                self.update_authority,
                self.rollback_authority,
            )
        ):
            raise ValueError("release install proposal grants no mutation authority")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.body_dict()).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_install_proposal_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseInstallProposalRecord:
        data = _mapping(value, "release install proposal")
        expected = {
            "schema_version",
            "package_plan_sha256",
            "release_build_review_sha256",
            "app_id",
            "app_version",
            "repository_url",
            "commit_sha",
            "manifest_sha256",
            "registry_snapshot_sha256",
            "execution_receipt_sha256",
            "offline_build_receipt_sha256",
            "artifact_set_sha256",
            "install_relative_path",
            "proposal_state",
            "proposal_scope",
            "compatibility_verdict",
            "install_authority",
            "launch_authority",
            "update_authority",
            "rollback_authority",
            "release_install_proposal_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "release install proposal contains missing or unknown fields"
            )
        record = cls(
            schema_version=data["schema_version"],
            package_plan_sha256=_sha256(
                data["package_plan_sha256"],
                "package_plan_sha256",
            ),
            release_build_review_sha256=_sha256(
                data["release_build_review_sha256"],
                "release_build_review_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            app_version=_string(data["app_version"], "app_version", maximum=128),
            repository_url=_string(
                data["repository_url"],
                "repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            manifest_sha256=_sha256(data["manifest_sha256"], "manifest_sha256"),
            registry_snapshot_sha256=_sha256(
                data["registry_snapshot_sha256"],
                "registry_snapshot_sha256",
            ),
            execution_receipt_sha256=_sha256(
                data["execution_receipt_sha256"],
                "execution_receipt_sha256",
            ),
            offline_build_receipt_sha256=_sha256(
                data["offline_build_receipt_sha256"],
                "offline_build_receipt_sha256",
            ),
            artifact_set_sha256=_sha256(
                data["artifact_set_sha256"],
                "artifact_set_sha256",
            ),
            install_relative_path=_string(
                data["install_relative_path"],
                "install_relative_path",
                maximum=1024,
            ),
            proposal_state=_string(
                data["proposal_state"],
                "proposal_state",
                maximum=64,
            ),
            proposal_scope=_string(
                data["proposal_scope"],
                "proposal_scope",
                maximum=64,
            ),
            compatibility_verdict=_string(
                data["compatibility_verdict"],
                "compatibility_verdict",
                maximum=32,
            ),
            install_authority=data["install_authority"],
            launch_authority=data["launch_authority"],
            update_authority=data["update_authority"],
            rollback_authority=data["rollback_authority"],
        )
        if data["release_install_proposal_sha256"] != record.sha256():
            raise ValueError(
                "release install proposal digest does not match canonical record"
            )
        return record


def propose_release_install(
    package_plan_value: Any,
    *,
    approved_package_plan_sha256: str,
) -> ReleaseInstallProposalRecord:
    plan = BuildPackagePlan.from_dict(package_plan_value)
    approved = _sha256(
        approved_package_plan_sha256,
        "approved_package_plan_sha256",
    )
    if approved != plan.sha256():
        raise ValueError(
            "approved package-plan digest does not match canonical package plan"
        )
    if plan.release_build_review_sha256 is None:
        raise ValueError(
            "release install proposal requires a v0.49 release-lineage package plan"
        )

    return ReleaseInstallProposalRecord(
        package_plan_sha256=plan.sha256(),
        release_build_review_sha256=plan.release_build_review_sha256,
        app_id=plan.app_id,
        app_version=plan.app_version,
        repository_url=plan.repository_url,
        commit_sha=plan.commit_sha,
        manifest_sha256=plan.manifest_sha256,
        registry_snapshot_sha256=plan.registry_snapshot_sha256,
        execution_receipt_sha256=plan.execution_receipt_sha256,
        offline_build_receipt_sha256=plan.offline_build_receipt_sha256,
        artifact_set_sha256=plan.artifact_set_sha256,
        install_relative_path=plan.install_relative_path,
    )


def validate_release_install_proposal(
    plan: BuildPackagePlan,
    proposal_value: Any,
    *,
    approved_release_install_proposal_sha256: str,
) -> ReleaseInstallProposalRecord:
    proposal = ReleaseInstallProposalRecord.from_dict(proposal_value)
    approved = _sha256(
        approved_release_install_proposal_sha256,
        "approved_release_install_proposal_sha256",
    )
    if approved != proposal.sha256():
        raise ValueError(
            "approved release install proposal digest does not match proposal"
        )
    if plan.release_build_review_sha256 is None:
        raise ValueError("package plan does not contain release lineage")

    expected = (
        ("package_plan_sha256", proposal.package_plan_sha256, plan.sha256()),
        (
            "release_build_review_sha256",
            proposal.release_build_review_sha256,
            plan.release_build_review_sha256,
        ),
        ("app_id", proposal.app_id, plan.app_id),
        ("app_version", proposal.app_version, plan.app_version),
        ("repository_url", proposal.repository_url.lower(), plan.repository_url.lower()),
        ("commit_sha", proposal.commit_sha, plan.commit_sha),
        ("manifest_sha256", proposal.manifest_sha256, plan.manifest_sha256),
        (
            "registry_snapshot_sha256",
            proposal.registry_snapshot_sha256,
            plan.registry_snapshot_sha256,
        ),
        (
            "execution_receipt_sha256",
            proposal.execution_receipt_sha256,
            plan.execution_receipt_sha256,
        ),
        (
            "offline_build_receipt_sha256",
            proposal.offline_build_receipt_sha256,
            plan.offline_build_receipt_sha256,
        ),
        ("artifact_set_sha256", proposal.artifact_set_sha256, plan.artifact_set_sha256),
        (
            "install_relative_path",
            proposal.install_relative_path,
            plan.install_relative_path,
        ),
    )
    for label, observed, required in expected:
        if observed != required:
            raise ValueError(
                f"release install proposal {label} does not match package plan"
            )
    return proposal
