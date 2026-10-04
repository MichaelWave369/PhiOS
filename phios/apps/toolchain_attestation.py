from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, cast

from .build_plan import BuildPlan, BuildStep
from .sandbox import BuildSandboxPolicy
from .toolchain_acquisition import CapsuleAcquisitionReceipt
from .toolchain_capsule import (
    ToolchainCapsule,
    bind_toolchain_capsule,
    derive_toolchain_requirement,
)

TOOLCHAIN_ATTESTATION_SCHEMA_VERSION = "phios.toolchain_attestation.v0.1"
TOOLCHAIN_SANDBOX_PLAN_SCHEMA_VERSION = "phios.toolchain_sandbox_plan.v0.1"

ToolchainAttestationStatus = Literal["attested_for_review"]
ToolchainSandboxPlanStatus = Literal[
    "ready_for_runtime_adapter_review",
    "dependency_staging_required",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOOL_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,63}$")

_EXPECTED_PROBES: dict[str, tuple[str, ...]] = {
    "node": ("node", "--version"),
    "npm": ("npm", "--version"),
    "python": ("python", "--version"),
    "python-build": ("python", "-m", "build", "--version"),
    "cargo": ("cargo", "--version"),
    "rustc": ("rustc", "--version"),
    "go": ("go", "version"),
}


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


def _false(value: Any, label: str) -> bool:
    if value is not False:
        raise ValueError(f"{label} must remain false")
    return False


def _safe_capsule_locator(value: Any, label: str) -> str:
    text = _string(value, label, maximum=256)
    if text.startswith("python-module:"):
        module = text.removeprefix("python-module:")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", module):
            raise ValueError(f"{label} contains an invalid Python module locator")
        return text

    if not text.startswith("/") or "\\" in text:
        raise ValueError(f"{label} must be an absolute POSIX path or python-module locator")
    path = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise ValueError(f"{label} contains unsafe path segments")
    return text


@dataclass(frozen=True)
class ToolProbeObservation:
    name: str
    probe_argv: tuple[str, ...]
    observed_version: str
    subject_locator: str
    subject_sha256: str
    probe_output_sha256: str

    def __post_init__(self) -> None:
        if not _TOOL_RE.fullmatch(self.name):
            raise ValueError(f"Invalid tool name: {self.name}")
        expected_probe = _EXPECTED_PROBES.get(self.name)
        if expected_probe is None:
            raise ValueError(f"No v0.53 probe contract exists for tool: {self.name}")
        if self.probe_argv != expected_probe:
            raise ValueError(f"Probe argv for {self.name} does not match the v0.53 contract")
        _string(self.observed_version, "observed_version", maximum=96)
        _safe_capsule_locator(self.subject_locator, "subject_locator")
        _sha256(self.subject_sha256, "subject_sha256")
        _sha256(self.probe_output_sha256, "probe_output_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "probe_argv": list(self.probe_argv),
            "observed_version": self.observed_version,
            "subject_locator": self.subject_locator,
            "subject_sha256": self.subject_sha256,
            "probe_output_sha256": self.probe_output_sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ToolProbeObservation:
        data = _mapping(value, "tool probe observation")
        expected = {
            "name",
            "probe_argv",
            "observed_version",
            "subject_locator",
            "subject_sha256",
            "probe_output_sha256",
        }
        if set(data) != expected:
            raise ValueError("tool probe observation contains missing or unknown fields")
        argv = data["probe_argv"]
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            raise ValueError("probe_argv must be an array of strings")
        return cls(
            name=_string(data["name"], "tool name", maximum=64),
            probe_argv=tuple(argv),
            observed_version=_string(data["observed_version"], "observed_version", maximum=96),
            subject_locator=_safe_capsule_locator(data["subject_locator"], "subject_locator"),
            subject_sha256=_sha256(data["subject_sha256"], "subject_sha256"),
            probe_output_sha256=_sha256(
                data["probe_output_sha256"], "probe_output_sha256"
            ),
        )


@dataclass(frozen=True)
class ToolchainAttestation:
    app_id: str
    commit_sha: str
    plan_sha256: str
    requirement_sha256: str
    capsule_sha256: str
    binding_sha256: str
    acquisition_receipt_sha256: str
    artifact_sha256: str
    inspector_id: str
    inspector_version: str
    observations: tuple[ToolProbeObservation, ...]
    status: ToolchainAttestationStatus = "attested_for_review"
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = TOOLCHAIN_ATTESTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_ATTESTATION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported toolchain attestation schema: {self.schema_version}"
            )
        _string(self.app_id, "app_id", maximum=64)
        if not re.fullmatch(r"^[0-9a-f]{40,64}$", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase hexadecimal commit identifier")
        for value, label in (
            (self.plan_sha256, "plan_sha256"),
            (self.requirement_sha256, "requirement_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.binding_sha256, "binding_sha256"),
            (self.acquisition_receipt_sha256, "acquisition_receipt_sha256"),
            (self.artifact_sha256, "artifact_sha256"),
        ):
            _sha256(value, label)
        _string(self.inspector_id, "inspector_id", maximum=96)
        _string(self.inspector_version, "inspector_version", maximum=96)
        if self.status != "attested_for_review":
            raise ValueError("v0.53 attestation status must be attested_for_review")
        names = [item.name for item in self.observations]
        if not names or len(names) != len(set(names)):
            raise ValueError("attestation observations must contain unique tools")
        if any(
            value is not False
            for value in (
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("toolchain attestations never grant authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "requirement_sha256": self.requirement_sha256,
            "capsule_sha256": self.capsule_sha256,
            "binding_sha256": self.binding_sha256,
            "acquisition_receipt_sha256": self.acquisition_receipt_sha256,
            "artifact_sha256": self.artifact_sha256,
            "inspector_id": self.inspector_id,
            "inspector_version": self.inspector_version,
            "observations": [
                item.to_dict() for item in sorted(self.observations, key=lambda item: item.name)
            ],
            "status": self.status,
            "execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def canonical_json(self) -> str:
        return json.dumps(\n            self.body_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False\n        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["attestation_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainAttestation:
        data = _mapping(value, "toolchain attestation")
        expected = {
            "schema_version",
            "app_id",
            "commit_sha",
            "plan_sha256",
            "requirement_sha256",
            "capsule_sha256",
            "binding_sha256",
            "acquisition_receipt_sha256",
            "artifact_sha256",
            "inspector_id",
            "inspector_version",
            "observations",
            "status",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "attestation_sha256",
        }
        if set(data) != expected:
            raise ValueError("toolchain attestation contains missing or unknown fields")
        raw_observations = data["observations"]
        if not isinstance(raw_observations, list):
            raise ValueError("observations must be an array")
        attestation = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            plan_sha256=_sha256(data["plan_sha256"], "plan_sha256"),
            requirement_sha256=_sha256(
                data["requirement_sha256"], "requirement_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            binding_sha256=_sha256(data["binding_sha256"], "binding_sha256"),
            acquisition_receipt_sha256=_sha256(
                data["acquisition_receipt_sha256"], "acquisition_receipt_sha256"
            ),
            artifact_sha256=_sha256(data["artifact_sha256"], "artifact_sha256"),
            inspector_id=_string(data["inspector_id"], "inspector_id", maximum=96),
            inspector_version=_string(
                data["inspector_version"], "inspector_version", maximum=96
            ),
            observations=tuple(
                ToolProbeObservation.from_dict(item) for item in raw_observations
            ),
            status=cast(ToolchainAttestationStatus, data["status"]),
            execution_authority=_false(
                data["execution_authority"], "execution_authority"
            ),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(
                data["host_write_authority"], "host_write_authority"
            ),
        )
        if data["attestation_sha256"] != attestation.sha256():
            raise ValueError("toolchain attestation digest does not match canonical content")
        return attestation


@dataclass(frozen=True)
class ToolchainSandboxPlan:
    app_id: str
    commit_sha: str
    build_plan_sha256: str
    acquisition_receipt_sha256: str
    capsule_sha256: str
    attestation_sha256: str
    capsule_artifact_sha256: str
    capsule_storage_path: str
    sandbox_policy: BuildSandboxPolicy
    steps: tuple[BuildStep, ...]
    status: ToolchainSandboxPlanStatus
    runtime_adapter_required: bool = True
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = TOOLCHAIN_SANDBOX_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_SANDBOX_PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported toolchain sandbox plan schema: {self.schema_version}"
            )
        _string(self.app_id, "app_id", maximum=64)
        if not re.fullmatch(r"^[0-9a-f]{40,64}$", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase hexadecimal commit identifier")
        for value, label in (
            (self.build_plan_sha256, "build_plan_sha256"),
            (self.acquisition_receipt_sha256, "acquisition_receipt_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.attestation_sha256, "attestation_sha256"),
            (self.capsule_artifact_sha256, "capsule_artifact_sha256"),
        ):
            _sha256(value, label)
        storage = _string(self.capsule_storage_path, "capsule_storage_path", maximum=4096)
        if not storage.startswith("/"):
            raise ValueError("capsule_storage_path must be absolute")
        if self.sandbox_policy.network_mode != "deny":
            raise ValueError("v0.53 sandbox plans must deny network access")
        if self.status not in {
            "ready_for_runtime_adapter_review",
            "dependency_staging_required",
        }:
            raise ValueError(f"Unsupported toolchain sandbox plan status: {self.status}")
        if self.runtime_adapter_required is not True:
            raise ValueError("v0.53 plans require a future runtime adapter")
        if any(
            value is not False
            for value in (
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("toolchain sandbox plans never grant authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "build_plan_sha256": self.build_plan_sha256,
            "acquisition_receipt_sha256": self.acquisition_receipt_sha256,
            "capsule_sha256": self.capsule_sha256,
            "attestation_sha256": self.attestation_sha256,
            "capsule_artifact_sha256": self.capsule_artifact_sha256,
            "capsule_storage_path": self.capsule_storage_path,
            "sandbox_policy": self.sandbox_policy.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "status": self.status,
            "runtime_adapter_required": True,
            "execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.body_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["sandbox_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainSandboxPlan:
        data = _mapping(value, "toolchain sandbox plan")
        expected = {
            "schema_version",
            "app_id",
            "commit_sha",
            "build_plan_sha256",
            "acquisition_receipt_sha256",
            "capsule_sha256",
            "attestation_sha256",
            "capsule_artifact_sha256",
            "capsule_storage_path",
            "sandbox_policy",
            "steps",
            "status",
            "runtime_adapter_required",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "sandbox_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("toolchain sandbox plan contains missing or unknown fields")
        raw_steps = data["steps"]
        if not isinstance(raw_steps, list):
            raise ValueError("steps must be an array")
        plan = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            build_plan_sha256=_sha256(
                data["build_plan_sha256"], "build_plan_sha256"
            ),
            acquisition_receipt_sha256=_sha256(
                data["acquisition_receipt_sha256"], "acquisition_receipt_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            attestation_sha256=_sha256(
                data["attestation_sha256"], "attestation_sha256"
            ),
            capsule_artifact_sha256=_sha256(
                data["capsule_artifact_sha256"], "capsule_artifact_sha256"
            ),
            capsule_storage_path=_string(
                data["capsule_storage_path"], "capsule_storage_path", maximum=4096
            ),
            sandbox_policy=BuildSandboxPolicy.from_dict(data["sandbox_policy"]),
            steps=tuple(BuildStep.from_dict(item) for item in raw_steps),
            status=cast(ToolchainSandboxPlanStatus, data["status"]),
            runtime_adapter_required=data["runtime_adapter_required"],
            execution_authority=_false(
                data["execution_authority"], "execution_authority"
            ),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(
                data["host_write_authority"], "host_write_authority"
            ),
        )
        if data["sandbox_plan_sha256"] != plan.sha256():
            raise ValueError("toolchain sandbox plan digest does not match canonical content")
        return plan


def attest_toolchain(
    plan: BuildPlan,
    capsule: ToolchainCapsule,
    acquisition: CapsuleAcquisitionReceipt,
    observations: tuple[ToolProbeObservation, ...],
    *,
    inspector_id: str,
    inspector_version: str,
) -> ToolchainAttestation:
    requirement = derive_toolchain_requirement(plan)
    if requirement.status != "capsule_required":
        raise ValueError("toolchain attestation requires a capsule-backed build plan")
    binding = bind_toolchain_capsule(requirement, capsule)

    if acquisition.app_id != plan.app_id or acquisition.commit_sha != plan.commit_sha:
        raise ValueError("capsule acquisition identity does not match build plan")
    if acquisition.plan_sha256 != plan.sha256():
        raise ValueError("capsule acquisition plan digest does not match build plan")
    if acquisition.requirement_sha256 != requirement.sha256():
        raise ValueError("capsule acquisition requirement does not match build plan")
    if acquisition.capsule_sha256 != capsule.sha256():
        raise ValueError("capsule acquisition does not match reviewed capsule")
    if acquisition.binding_sha256 != binding.sha256():
        raise ValueError("capsule acquisition binding does not match reviewed capsule")
    if acquisition.artifact_sha256 != capsule.artifact_sha256:
        raise ValueError("capsule acquisition artifact digest does not match reviewed capsule")
    if acquisition.status != "verified_available":
        raise ValueError("toolchain attestation requires verified capsule availability")

    observed = {item.name: item for item in observations}
    declared = {item.name: item.version for item in capsule.tools}
    if set(observed) != set(declared):
        raise ValueError("observed tool set does not exactly match reviewed capsule")

    for name, version in declared.items():
        if observed[name].observed_version != version:
            raise ValueError(f"observed version for {name} does not match reviewed capsule")

    return ToolchainAttestation(
        app_id=plan.app_id,
        commit_sha=plan.commit_sha,
        plan_sha256=plan.sha256(),
        requirement_sha256=requirement.sha256(),
        capsule_sha256=capsule.sha256(),
        binding_sha256=binding.sha256(),
        acquisition_receipt_sha256=acquisition.sha256(),
        artifact_sha256=acquisition.artifact_sha256,
        inspector_id=inspector_id,
        inspector_version=inspector_version,
        observations=observations,
    )


def plan_toolchain_sandbox(
    plan: BuildPlan,
    capsule: ToolchainCapsule,
    acquisition: CapsuleAcquisitionReceipt,
    attestation: ToolchainAttestation,
    *,
    sandbox_policy: BuildSandboxPolicy | None = None,
) -> ToolchainSandboxPlan:
    policy = sandbox_policy or BuildSandboxPolicy(network_mode="deny")
    if policy.network_mode != "deny":
        raise ValueError("v0.53 toolchain sandbox planning requires network denial")

    reconstructed = attest_toolchain(
        plan,
        capsule,
        acquisition,
        attestation.observations,
        inspector_id=attestation.inspector_id,
        inspector_version=attestation.inspector_version,
    )
    if reconstructed.sha256() != attestation.sha256():
        raise ValueError(
            "toolchain attestation does not reconstruct from the exact plan, capsule "
            "and acquisition"
        )

    status: ToolchainSandboxPlanStatus = (
        "dependency_staging_required"
        if any(step.requires_network for step in plan.steps)
        else "ready_for_runtime_adapter_review"
    )

    return ToolchainSandboxPlan(
        app_id=plan.app_id,
        commit_sha=plan.commit_sha,
        build_plan_sha256=plan.sha256(),
        acquisition_receipt_sha256=acquisition.sha256(),
        capsule_sha256=capsule.sha256(),
        attestation_sha256=attestation.sha256(),
        capsule_artifact_sha256=capsule.artifact_sha256,
        capsule_storage_path=acquisition.storage_path,
        sandbox_policy=policy,
        steps=plan.steps,
        status=status,
    )
