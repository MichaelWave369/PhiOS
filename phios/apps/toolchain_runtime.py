from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from .build_execution import (
    BuildExecutionReceipt,
    BuildExecutionRequest,
    BuildExecutionService,
    BuildProcessRunner,
    ProcessResult,
    ToolIdentity,
)
from .build_plan import AcquisitionBinding, BuildPlan, BuildStep
from .toolchain_acquisition import CapsuleAcquisitionReceipt
from .toolchain_attestation import (
    ToolProbeObservation,
    ToolchainAttestation,
    ToolchainSandboxPlan,
    attest_toolchain,
    plan_toolchain_sandbox,
)
from .toolchain_capsule import ToolchainCapsule

OCI_RUNTIME_ADAPTER_IDENTITY_SCHEMA_VERSION = "phios.oci_runtime_adapter_identity.v0.1"
OCI_RUNTIME_CONTROL_EVIDENCE_SCHEMA_VERSION = "phios.oci_runtime_control_evidence.v0.1"
TOOLCHAIN_RUNTIME_REQUEST_SCHEMA_VERSION = "phios.toolchain_runtime_request.v0.1"
TOOLCHAIN_RUNTIME_RECEIPT_SCHEMA_VERSION = "phios.toolchain_runtime_receipt.v0.1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")


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


def _true(value: Any, label: str) -> bool:
    if value is not True:
        raise ValueError(f"{label} must remain true")
    return True


def _observation_set_sha256(observations: tuple[ToolProbeObservation, ...]) -> str:
    payload = [
        item.to_dict()
        for item in sorted(observations, key=lambda observation: observation.name)
    ]
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _verify_capsule_file(path: Path, *, expected_sha256: str, expected_bytes: int) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError("verified capsule artifact is no longer available") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("verified capsule artifact must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("verified capsule artifact must remain a regular file")
    if info.st_size != expected_bytes:
        raise ValueError("verified capsule artifact byte count changed before execution")

    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    if total != expected_bytes or digest.hexdigest() != expected_sha256:
        raise ValueError("verified capsule artifact digest changed before execution")


@dataclass(frozen=True)
class OciRuntimeAdapterIdentity:
    adapter_id: str
    adapter_version: str
    backend: str
    backend_version: str
    backend_binary_sha256: str
    platform_system: str
    platform_machine: str
    schema_version: str = OCI_RUNTIME_ADAPTER_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OCI_RUNTIME_ADAPTER_IDENTITY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported OCI runtime adapter identity schema: {self.schema_version}"
            )
        if not _ID_RE.fullmatch(self.adapter_id):
            raise ValueError("adapter_id must use bounded lowercase identifier syntax")
        if not _ID_RE.fullmatch(self.backend):
            raise ValueError("backend must use bounded lowercase identifier syntax")
        _string(self.adapter_version, "adapter_version", maximum=96)
        _string(self.backend_version, "backend_version", maximum=192)
        _sha256(self.backend_binary_sha256, "backend_binary_sha256")
        _string(self.platform_system, "platform_system", maximum=64)
        _string(self.platform_machine, "platform_machine", maximum=64)

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "backend_binary_sha256": self.backend_binary_sha256,
            "platform_system": self.platform_system,
            "platform_machine": self.platform_machine,
        }

    def sha256(self) -> str:
        payload = json.dumps(
            self.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["identity_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> OciRuntimeAdapterIdentity:
        data = _mapping(value, "OCI runtime adapter identity")
        expected = {
            "schema_version",
            "adapter_id",
            "adapter_version",
            "backend",
            "backend_version",
            "backend_binary_sha256",
            "platform_system",
            "platform_machine",
            "identity_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "OCI runtime adapter identity contains missing or unknown fields"
            )
        identity = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            adapter_id=_string(data["adapter_id"], "adapter_id", maximum=96),
            adapter_version=_string(
                data["adapter_version"], "adapter_version", maximum=96
            ),
            backend=_string(data["backend"], "backend", maximum=96),
            backend_version=_string(
                data["backend_version"], "backend_version", maximum=192
            ),
            backend_binary_sha256=_sha256(
                data["backend_binary_sha256"], "backend_binary_sha256"
            ),
            platform_system=_string(
                data["platform_system"], "platform_system", maximum=64
            ),
            platform_machine=_string(
                data["platform_machine"], "platform_machine", maximum=64
            ),
        )
        if data["identity_sha256"] != identity.sha256():
            raise ValueError("OCI runtime adapter identity digest does not match content")
        return identity


@dataclass(frozen=True)
class OciRuntimeControlEvidence:
    rootfs_read_only: bool
    workspace_bind_read_write: bool
    network_namespace_enforced: bool
    host_network_inherited: bool
    host_control_plane_mounted: bool
    privileged_mode: bool
    capabilities_dropped: bool
    no_new_privileges: bool
    shell_invocation: bool
    schema_version: str = OCI_RUNTIME_CONTROL_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OCI_RUNTIME_CONTROL_EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported OCI runtime control evidence schema: {self.schema_version}"
            )
        _true(self.rootfs_read_only, "rootfs_read_only")
        _true(self.workspace_bind_read_write, "workspace_bind_read_write")
        _true(self.network_namespace_enforced, "network_namespace_enforced")
        _false(self.host_network_inherited, "host_network_inherited")
        _false(self.host_control_plane_mounted, "host_control_plane_mounted")
        _false(self.privileged_mode, "privileged_mode")
        _true(self.capabilities_dropped, "capabilities_dropped")
        _true(self.no_new_privileges, "no_new_privileges")
        _false(self.shell_invocation, "shell_invocation")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rootfs_read_only": True,
            "workspace_bind_read_write": True,
            "network_namespace_enforced": True,
            "host_network_inherited": False,
            "host_control_plane_mounted": False,
            "privileged_mode": False,
            "capabilities_dropped": True,
            "no_new_privileges": True,
            "shell_invocation": False,
        }

    def sha256(self) -> str:
        payload = json.dumps(
            self.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["controls_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> OciRuntimeControlEvidence:
        data = _mapping(value, "OCI runtime control evidence")
        expected = {
            "schema_version",
            "rootfs_read_only",
            "workspace_bind_read_write",
            "network_namespace_enforced",
            "host_network_inherited",
            "host_control_plane_mounted",
            "privileged_mode",
            "capabilities_dropped",
            "no_new_privileges",
            "shell_invocation",
            "controls_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "OCI runtime control evidence contains missing or unknown fields"
            )
        controls = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            rootfs_read_only=data["rootfs_read_only"],
            workspace_bind_read_write=data["workspace_bind_read_write"],
            network_namespace_enforced=data["network_namespace_enforced"],
            host_network_inherited=data["host_network_inherited"],
            host_control_plane_mounted=data["host_control_plane_mounted"],
            privileged_mode=data["privileged_mode"],
            capabilities_dropped=data["capabilities_dropped"],
            no_new_privileges=data["no_new_privileges"],
            shell_invocation=data["shell_invocation"],
        )
        if data["controls_sha256"] != controls.sha256():
            raise ValueError("OCI runtime control evidence digest does not match content")
        return controls


@dataclass(frozen=True)
class ToolchainRuntimeRequest:
    build_plan: BuildPlan
    source_acquisition: AcquisitionBinding
    capsule: ToolchainCapsule
    capsule_acquisition: CapsuleAcquisitionReceipt
    attestation: ToolchainAttestation
    sandbox_plan: ToolchainSandboxPlan
    approved_sandbox_plan_sha256: str
    approved_attestation_sha256: str
    approved_source_snapshot_sha256: str
    approved_build_permissions: tuple[str, ...]
    execution_approval_id: str
    execution_scope: str = "single_toolchain_build"
    schema_version: str = TOOLCHAIN_RUNTIME_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_RUNTIME_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported toolchain runtime request schema: {self.schema_version}"
            )
        if self.execution_scope != "single_toolchain_build":
            raise ValueError("v0.54 supports only single_toolchain_build execution scope")
        try:
            parsed_approval_id = uuid.UUID(self.execution_approval_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("execution_approval_id must be a UUID") from exc
        if str(parsed_approval_id) != self.execution_approval_id:
            raise ValueError("execution_approval_id must use canonical lowercase UUID syntax")
        if self.sandbox_plan.status != "ready_for_runtime_adapter_review":
            raise ValueError(
                "toolchain runtime execution requires ready_for_runtime_adapter_review"
            )
        if any(step.requires_network for step in self.build_plan.steps):
            raise ValueError("v0.54 refuses build steps that still require network access")
        if self.sandbox_plan.sandbox_policy.network_mode != "deny":
            raise ValueError("v0.54 requires a network-denied sandbox plan")

        reconstructed_attestation = attest_toolchain(
            self.build_plan,
            self.capsule,
            self.capsule_acquisition,
            self.attestation.observations,
            inspector_id=self.attestation.inspector_id,
            inspector_version=self.attestation.inspector_version,
        )
        if reconstructed_attestation.sha256() != self.attestation.sha256():
            raise ValueError(
                "toolchain attestation does not reconstruct from the exact runtime inputs"
            )

        reconstructed_sandbox = plan_toolchain_sandbox(
            self.build_plan,
            self.capsule,
            self.capsule_acquisition,
            self.attestation,
            sandbox_policy=self.sandbox_plan.sandbox_policy,
        )
        if reconstructed_sandbox.sha256() != self.sandbox_plan.sha256():
            raise ValueError(
                "toolchain sandbox plan does not reconstruct from the exact runtime inputs"
            )

        if self.approved_sandbox_plan_sha256 != self.sandbox_plan.sha256():
            raise ValueError(
                "approved sandbox plan SHA-256 does not match the canonical plan"
            )
        if self.approved_attestation_sha256 != self.attestation.sha256():
            raise ValueError(
                "approved attestation SHA-256 does not match the canonical attestation"
            )
        if self.approved_source_snapshot_sha256 != self.build_plan.source_snapshot_sha256:
            raise ValueError(
                "approved source snapshot SHA-256 does not match the build plan"
            )
        if tuple(sorted(self.approved_build_permissions)) != tuple(
            sorted(self.build_plan.requested_build_permissions)
        ):
            raise ValueError(
                "approved build permissions must exactly match the reviewed build plan"
            )

        from .release_build_review import release_advancement_sha256_from_plan

        if release_advancement_sha256_from_plan(self.build_plan) is not None:
            raise ValueError(
                "v0.54 toolchain runtime does not execute release-lineage build plans"
            )

        BuildExecutionRequest(
            plan=self.build_plan,
            acquisition=self.source_acquisition,
            approved_plan_sha256=self.build_plan.sha256(),
            approved_source_snapshot_sha256=self.approved_source_snapshot_sha256,
            approved_permissions=tuple(sorted(self.approved_build_permissions)),
        )


class OciRuntimeBuildRunner(BuildProcessRunner, Protocol):
    isolation_mode: str
    network_sandbox_enforced: bool
    capsule_artifact_sha256: str
    capsule_storage_path: str
    sandbox_plan_sha256: str
    policy_sha256: str

    def preflight(self) -> OciRuntimeAdapterIdentity: ...

    def control_evidence(self) -> OciRuntimeControlEvidence: ...

    def runtime_observations(self) -> tuple[ToolProbeObservation, ...]: ...


@dataclass(frozen=True)
class ToolchainRuntimeReceipt:
    runtime_receipt_id: str
    timestamp_utc: str
    app_id: str
    commit_sha: str
    build_plan_sha256: str
    source_snapshot_sha256: str
    capsule_sha256: str
    capsule_acquisition_receipt_sha256: str
    attestation_sha256: str
    sandbox_plan_sha256: str
    capsule_artifact_sha256: str
    runtime_observation_set_sha256: str
    runtime_recheck_attestation_sha256: str
    runtime_identity: OciRuntimeAdapterIdentity
    controls: OciRuntimeControlEvidence
    build_execution_receipt_sha256: str
    build_status: str
    execution_approval_id: str
    execution_approval_claim_sha256: str
    execution_scope: str = "single_toolchain_build"
    execution_approval_consumed: bool = True
    reusable_execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = TOOLCHAIN_RUNTIME_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_RUNTIME_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported toolchain runtime receipt schema: {self.schema_version}"
            )
        _string(self.runtime_receipt_id, "runtime_receipt_id", maximum=64)
        _string(self.timestamp_utc, "timestamp_utc", maximum=64)
        _string(self.app_id, "app_id", maximum=64)
        if not re.fullmatch(r"^[0-9a-f]{40,64}$", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase hexadecimal identifier")
        for value, label in (
            (self.build_plan_sha256, "build_plan_sha256"),
            (self.source_snapshot_sha256, "source_snapshot_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (
                self.capsule_acquisition_receipt_sha256,
                "capsule_acquisition_receipt_sha256",
            ),
            (self.attestation_sha256, "attestation_sha256"),
            (self.sandbox_plan_sha256, "sandbox_plan_sha256"),
            (self.capsule_artifact_sha256, "capsule_artifact_sha256"),
            (self.runtime_observation_set_sha256, "runtime_observation_set_sha256"),
            (
                self.runtime_recheck_attestation_sha256,
                "runtime_recheck_attestation_sha256",
            ),
            (
                self.build_execution_receipt_sha256,
                "build_execution_receipt_sha256",
            ),
            (
                self.execution_approval_claim_sha256,
                "execution_approval_claim_sha256",
            ),
        ):
            _sha256(value, label)
        try:
            parsed_approval_id = uuid.UUID(self.execution_approval_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("execution_approval_id must be a UUID") from exc
        if str(parsed_approval_id) != self.execution_approval_id:
            raise ValueError("execution_approval_id must use canonical lowercase UUID syntax")
        if self.execution_scope != "single_toolchain_build":
            raise ValueError("unsupported runtime receipt execution_scope")
        _true(self.execution_approval_consumed, "execution_approval_consumed")
        _false(self.reusable_execution_authority, "reusable_execution_authority")
        _false(self.network_authority, "network_authority")
        _false(self.install_authority, "install_authority")
        _false(self.host_write_authority, "host_write_authority")
        if self.build_status not in {"success", "no_build_required", "failed"}:
            raise ValueError("unsupported build_status in runtime receipt")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime_receipt_id": self.runtime_receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "build_plan_sha256": self.build_plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "capsule_sha256": self.capsule_sha256,
            "capsule_acquisition_receipt_sha256": (
                self.capsule_acquisition_receipt_sha256
            ),
            "attestation_sha256": self.attestation_sha256,
            "sandbox_plan_sha256": self.sandbox_plan_sha256,
            "capsule_artifact_sha256": self.capsule_artifact_sha256,
            "runtime_observation_set_sha256": self.runtime_observation_set_sha256,
            "runtime_recheck_attestation_sha256": (
                self.runtime_recheck_attestation_sha256
            ),
            "runtime_identity": self.runtime_identity.to_dict(),
            "controls": self.controls.to_dict(),
            "build_execution_receipt_sha256": self.build_execution_receipt_sha256,
            "build_status": self.build_status,
            "execution_approval_id": self.execution_approval_id,
            "execution_approval_claim_sha256": self.execution_approval_claim_sha256,
            "execution_scope": self.execution_scope,
            "execution_approval_consumed": True,
            "reusable_execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def sha256(self) -> str:
        payload = json.dumps(
            self.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["runtime_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainRuntimeReceipt:
        data = _mapping(value, "toolchain runtime receipt")
        expected = {
            "schema_version",
            "runtime_receipt_id",
            "timestamp_utc",
            "app_id",
            "commit_sha",
            "build_plan_sha256",
            "source_snapshot_sha256",
            "capsule_sha256",
            "capsule_acquisition_receipt_sha256",
            "attestation_sha256",
            "sandbox_plan_sha256",
            "capsule_artifact_sha256",
            "runtime_observation_set_sha256",
            "runtime_recheck_attestation_sha256",
            "runtime_identity",
            "controls",
            "build_execution_receipt_sha256",
            "build_status",
            "execution_approval_id",
            "execution_approval_claim_sha256",
            "execution_scope",
            "execution_approval_consumed",
            "reusable_execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "runtime_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("toolchain runtime receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            runtime_receipt_id=_string(
                data["runtime_receipt_id"], "runtime_receipt_id", maximum=64
            ),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=64),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            build_plan_sha256=_sha256(
                data["build_plan_sha256"], "build_plan_sha256"
            ),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"], "source_snapshot_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            capsule_acquisition_receipt_sha256=_sha256(
                data["capsule_acquisition_receipt_sha256"],
                "capsule_acquisition_receipt_sha256",
            ),
            attestation_sha256=_sha256(
                data["attestation_sha256"], "attestation_sha256"
            ),
            sandbox_plan_sha256=_sha256(
                data["sandbox_plan_sha256"], "sandbox_plan_sha256"
            ),
            capsule_artifact_sha256=_sha256(
                data["capsule_artifact_sha256"], "capsule_artifact_sha256"
            ),
            runtime_observation_set_sha256=_sha256(
                data["runtime_observation_set_sha256"],
                "runtime_observation_set_sha256",
            ),
            runtime_recheck_attestation_sha256=_sha256(
                data["runtime_recheck_attestation_sha256"],
                "runtime_recheck_attestation_sha256",
            ),
            runtime_identity=OciRuntimeAdapterIdentity.from_dict(
                data["runtime_identity"]
            ),
            controls=OciRuntimeControlEvidence.from_dict(data["controls"]),
            build_execution_receipt_sha256=_sha256(
                data["build_execution_receipt_sha256"],
                "build_execution_receipt_sha256",
            ),
            build_status=_string(data["build_status"], "build_status", maximum=32),
            execution_approval_id=_string(
                data["execution_approval_id"], "execution_approval_id", maximum=36
            ),
            execution_approval_claim_sha256=_sha256(
                data["execution_approval_claim_sha256"],
                "execution_approval_claim_sha256",
            ),
            execution_scope=_string(
                data["execution_scope"], "execution_scope", maximum=64
            ),
            execution_approval_consumed=_true(
                data["execution_approval_consumed"],
                "execution_approval_consumed",
            ),
            reusable_execution_authority=_false(
                data["reusable_execution_authority"],
                "reusable_execution_authority",
            ),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(
                data["host_write_authority"], "host_write_authority"
            ),
        )
        if data["runtime_receipt_sha256"] != receipt.sha256():
            raise ValueError("toolchain runtime receipt digest does not match content")
        return receipt


@dataclass(frozen=True)
class ToolchainRuntimeExecutionResult:
    execution: BuildExecutionReceipt
    runtime: ToolchainRuntimeReceipt
    runtime_receipt_path: str | None
    runtime_receipt_persisted: bool


def _consume_execution_approval(
    authority_root: Path,
    request: ToolchainRuntimeRequest,
) -> str:
    root = authority_root.expanduser().resolve()
    claim_root = (root / "toolchain-runtime").resolve()
    if root not in claim_root.parents:
        raise ValueError("execution approval claim root escaped authority root")
    claim_root.mkdir(parents=True, exist_ok=True)

    claim_path = (claim_root / f"{request.execution_approval_id}.json").resolve()
    if claim_root not in claim_path.parents:
        raise ValueError("execution approval claim path escaped authority root")

    body = {
        "schema_version": "phios.toolchain_execution_claim.v0.1",
        "execution_approval_id": request.execution_approval_id,
        "execution_scope": request.execution_scope,
        "sandbox_plan_sha256": request.sandbox_plan.sha256(),
        "attestation_sha256": request.attestation.sha256(),
        "capsule_sha256": request.capsule.sha256(),
        "source_snapshot_sha256": request.build_plan.source_snapshot_sha256,
    }
    canonical = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    claim_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload = json.dumps(
        {**body, "claim_sha256": claim_sha256},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    try:
        with claim_path.open("x", encoding="utf-8") as stream:
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ValueError("execution approval has already been consumed") from exc
    return claim_sha256


def _write_receipt(path: Path, receipt: ToolchainRuntimeReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(
        receipt.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    try:
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class ToolchainRuntimeService:
    """Execute one exactly approved v0.53 plan through an injected OCI adapter."""

    def __init__(self, *, runner: OciRuntimeBuildRunner) -> None:
        self.runner = runner

    def execute(
        self,
        request: ToolchainRuntimeRequest,
        *,
        execution_root: Path,
        receipt_root: Path | None = None,
    ) -> ToolchainRuntimeExecutionResult:
        request = ToolchainRuntimeRequest(
            build_plan=request.build_plan,
            source_acquisition=request.source_acquisition,
            capsule=request.capsule,
            capsule_acquisition=request.capsule_acquisition,
            attestation=request.attestation,
            sandbox_plan=request.sandbox_plan,
            approved_sandbox_plan_sha256=request.approved_sandbox_plan_sha256,
            approved_attestation_sha256=request.approved_attestation_sha256,
            approved_source_snapshot_sha256=request.approved_source_snapshot_sha256,
            approved_build_permissions=request.approved_build_permissions,
            execution_approval_id=request.execution_approval_id,
            execution_scope=request.execution_scope,
        )

        if self.runner.capsule_artifact_sha256 != request.capsule.artifact_sha256:
            raise ValueError("OCI runner capsule digest does not match reviewed capsule")
        if Path(self.runner.capsule_storage_path) != Path(
            request.capsule_acquisition.storage_path
        ):
            raise ValueError("OCI runner capsule path does not match acquisition receipt")
        if self.runner.sandbox_plan_sha256 != request.sandbox_plan.sha256():
            raise ValueError("OCI runner sandbox plan does not match approved plan")
        if self.runner.policy_sha256 != request.sandbox_plan.sandbox_policy.sha256():
            raise ValueError("OCI runner sandbox policy does not match approved policy")
        if self.runner.network_sandbox_enforced is not True:
            raise ValueError("OCI runner must enforce network denial")

        artifact_path = Path(request.capsule_acquisition.storage_path)
        _verify_capsule_file(
            artifact_path,
            expected_sha256=request.capsule.artifact_sha256,
            expected_bytes=request.capsule_acquisition.artifact_bytes,
        )

        authority_root = execution_root.expanduser().resolve() / ".phios-authority"
        approval_claim_sha256 = _consume_execution_approval(authority_root, request)

        runtime_identity = self.runner.preflight()
        controls = self.runner.control_evidence()

        runtime_observations = self.runner.runtime_observations()
        reviewed_observation_sha256 = _observation_set_sha256(
            request.attestation.observations
        )
        runtime_observation_sha256 = _observation_set_sha256(runtime_observations)
        if runtime_observation_sha256 != reviewed_observation_sha256:
            raise ValueError(
                "runtime tool observations do not match the reviewed v0.53 attestation"
            )

        runtime_recheck = attest_toolchain(
            request.build_plan,
            request.capsule,
            request.capsule_acquisition,
            runtime_observations,
            inspector_id=runtime_identity.adapter_id,
            inspector_version=runtime_identity.adapter_version,
        )

        build_request = BuildExecutionRequest(
            plan=request.build_plan,
            acquisition=request.source_acquisition,
            approved_plan_sha256=request.build_plan.sha256(),
            approved_source_snapshot_sha256=request.approved_source_snapshot_sha256,
            approved_permissions=tuple(sorted(request.approved_build_permissions)),
        )
        execution = BuildExecutionService(
            runner=self.runner,
            step_timeout_seconds=request.sandbox_plan.sandbox_policy.wall_clock_seconds,
        ).execute(
            build_request,
            execution_root=execution_root,
            receipt_root=receipt_root,
        )

        if execution.network_sandbox_enforced is not True:
            raise ValueError("OCI build execution did not retain network denial")

        runtime_by_name = {item.name: item for item in runtime_observations}
        execution_by_name = {
            item.logical_tool: item for item in execution.tool_identities
        }
        if set(runtime_by_name) != set(execution_by_name):
            raise ValueError(
                "executed tool identity set does not match runtime recheck observations"
            )
        for name, observation in runtime_by_name.items():
            identity = execution_by_name[name]
            if identity.version != observation.observed_version:
                raise ValueError(
                    f"executed tool version for {name} differs from runtime recheck"
                )
            if identity.version_output_sha256 != observation.probe_output_sha256:
                raise ValueError(
                    f"executed tool probe digest for {name} differs from runtime recheck"
                )

        receipt = ToolchainRuntimeReceipt(
            runtime_receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=request.build_plan.app_id,
            commit_sha=request.build_plan.commit_sha,
            build_plan_sha256=request.build_plan.sha256(),
            source_snapshot_sha256=request.build_plan.source_snapshot_sha256,
            capsule_sha256=request.capsule.sha256(),
            capsule_acquisition_receipt_sha256=request.capsule_acquisition.sha256(),
            attestation_sha256=request.attestation.sha256(),
            sandbox_plan_sha256=request.sandbox_plan.sha256(),
            capsule_artifact_sha256=request.capsule.artifact_sha256,
            runtime_observation_set_sha256=runtime_observation_sha256,
            runtime_recheck_attestation_sha256=runtime_recheck.sha256(),
            runtime_identity=runtime_identity,
            controls=controls,
            build_execution_receipt_sha256=execution.sha256(),
            build_status=execution.status,
            execution_approval_id=request.execution_approval_id,
            execution_approval_claim_sha256=approval_claim_sha256,
        )

        root = execution_root.expanduser().resolve()
        receipts = (receipt_root or (root / ".phios-receipts")).expanduser().resolve()
        receipt_path = receipts / f"toolchain-runtime-{execution.execution_id}.json"
        persisted = True
        path_text: str | None = str(receipt_path)
        try:
            _write_receipt(receipt_path, receipt)
        except OSError:
            persisted = False
            path_text = None

        return ToolchainRuntimeExecutionResult(
            execution=execution,
            runtime=receipt,
            runtime_receipt_path=path_text,
            runtime_receipt_persisted=persisted,
        )
