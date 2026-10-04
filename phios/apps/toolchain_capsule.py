from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from .build_plan import BuildPlan

TOOLCHAIN_REQUIREMENT_SCHEMA_VERSION = "phios.toolchain_requirement.v0.1"
TOOLCHAIN_CAPSULE_SCHEMA_VERSION = "phios.toolchain_capsule.v0.1"
TOOLCHAIN_BINDING_SCHEMA_VERSION = "phios.toolchain_binding.v0.1"

ToolchainFamily = Literal["node_npm", "python_pep517", "rust_cargo", "go_module"]
ToolchainRequirementStatus = Literal[
    "capsule_required",
    "no_capsule_required",
    "unsupported_toolchain",
]
ToolchainPlatform = Literal["linux_x86_64"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CAPSULE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_TOOL_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,63}$")

_FAMILY_TOOLS: dict[ToolchainFamily, frozenset[str]] = {
    "node_npm": frozenset({"node", "npm"}),
    "python_pep517": frozenset({"python", "python-build"}),
    "rust_cargo": frozenset({"cargo", "rustc"}),
    "go_module": frozenset({"go"}),
}


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _string(value: Any, label: str, *, maximum: int = 1024) -> str:
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


def _family(value: Any, label: str = "family") -> ToolchainFamily:
    if value not in _FAMILY_TOOLS:
        raise ValueError(f"Unsupported {label}: {value}")
    return cast(ToolchainFamily, value)


@dataclass(frozen=True)
class ToolchainTool:
    name: str
    version: str

    def __post_init__(self) -> None:
        if not _TOOL_RE.fullmatch(self.name):
            raise ValueError(f"Invalid tool name: {self.name}")
        _string(self.version, "tool version", maximum=96)

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainTool:
        data = _mapping(value, "toolchain tool")
        if set(data) != {"name", "version"}:
            raise ValueError("toolchain tool contains missing or unknown fields")
        return cls(
            name=_string(data["name"], "tool name", maximum=64),
            version=_string(data["version"], "tool version", maximum=96),
        )


@dataclass(frozen=True)
class ToolchainRequirement:
    app_id: str
    commit_sha: str
    plan_sha256: str
    strategy: str
    family: ToolchainFamily | None
    required_tools: tuple[str, ...]
    status: ToolchainRequirementStatus
    execution_authority: bool = False
    schema_version: str = TOOLCHAIN_REQUIREMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_REQUIREMENT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported toolchain requirement schema: {self.schema_version}")
        _string(self.app_id, "app_id", maximum=64)
        if not re.fullmatch(r"^[0-9a-f]{40,64}$", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase hexadecimal commit identifier")
        _sha256(self.plan_sha256, "plan_sha256")
        _string(self.strategy, "strategy", maximum=64)
        if self.status not in {
            "capsule_required",
            "no_capsule_required",
            "unsupported_toolchain",
        }:
            raise ValueError(f"Unsupported toolchain requirement status: {self.status}")
        if self.execution_authority is not False:
            raise ValueError("toolchain requirements never grant execution authority")
        if len(self.required_tools) > 16 or len(set(self.required_tools)) != len(self.required_tools):
            raise ValueError("required_tools must contain at most 16 unique tools")
        for tool in self.required_tools:
            if not _TOOL_RE.fullmatch(tool):
                raise ValueError(f"Invalid required tool: {tool}")
        if self.family is not None and self.family not in _FAMILY_TOOLS:
            raise ValueError(f"Unsupported toolchain family: {self.family}")
        if self.status == "capsule_required" and self.family is None:
            raise ValueError("capsule_required requirements must name a family")
        if self.status != "capsule_required" and self.family is not None:
            raise ValueError("only capsule_required requirements may name a family")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "strategy": self.strategy,
            "family": self.family,
            "required_tools": list(self.required_tools),
            "status": self.status,
            "execution_authority": False,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.body_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["requirement_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainRequirement:
        data = _mapping(value, "toolchain requirement")
        expected = {
            "schema_version",
            "app_id",
            "commit_sha",
            "plan_sha256",
            "strategy",
            "family",
            "required_tools",
            "status",
            "execution_authority",
            "requirement_sha256",
        }
        if set(data) != expected:
            raise ValueError("toolchain requirement contains missing or unknown fields")
        if data["schema_version"] != TOOLCHAIN_REQUIREMENT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported toolchain requirement schema: {data['schema_version']}")
        raw_tools = data["required_tools"]
        if not isinstance(raw_tools, list) or not all(isinstance(item, str) for item in raw_tools):
            raise ValueError("required_tools must be an array of strings")
        raw_family = data["family"]
        family = None if raw_family is None else _family(raw_family)
        requirement = cls(
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            plan_sha256=_sha256(data["plan_sha256"], "plan_sha256"),
            strategy=_string(data["strategy"], "strategy", maximum=64),
            family=family,
            required_tools=tuple(raw_tools),
            status=cast(ToolchainRequirementStatus, data["status"]),
            execution_authority=_false(data["execution_authority"], "execution_authority"),
        )
        if data["requirement_sha256"] != requirement.sha256():
            raise ValueError("toolchain requirement digest does not match canonical content")
        return requirement


@dataclass(frozen=True)
class ToolchainCapsule:
    capsule_id: str
    family: ToolchainFamily
    platform: ToolchainPlatform
    artifact_kind: Literal["oci_image"]
    artifact_ref: str
    artifact_sha256: str
    tools: tuple[ToolchainTool, ...]
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = TOOLCHAIN_CAPSULE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_CAPSULE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported toolchain capsule schema: {self.schema_version}")
        if not _CAPSULE_ID_RE.fullmatch(self.capsule_id):
            raise ValueError("capsule_id must use bounded lowercase identifier syntax")
        if self.family not in _FAMILY_TOOLS:
            raise ValueError(f"Unsupported toolchain family: {self.family}")
        if self.platform != "linux_x86_64":
            raise ValueError("v0.51 supports only linux_x86_64 capsules")
        if self.artifact_kind != "oci_image":
            raise ValueError("v0.51 supports only oci_image capsule artifacts")
        _string(self.artifact_ref, "artifact_ref", maximum=512)
        _sha256(self.artifact_sha256, "artifact_sha256")
        if any(
            value is not False
            for value in (
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("toolchain capsule authority fields must remain false")
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("toolchain capsule tools must not contain duplicates")
        expected = _FAMILY_TOOLS[self.family]
        if set(names) != expected:
            raise ValueError(
                f"{self.family} capsule must declare exactly: {', '.join(sorted(expected))}"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capsule_id": self.capsule_id,
            "family": self.family,
            "platform": self.platform,
            "artifact_kind": self.artifact_kind,
            "artifact_ref": self.artifact_ref,
            "artifact_sha256": self.artifact_sha256,
            "tools": [tool.to_dict() for tool in sorted(self.tools, key=lambda item: item.name)],
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
        result["capsule_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainCapsule:
        data = _mapping(value, "toolchain capsule")
        expected = {
            "schema_version",
            "capsule_id",
            "family",
            "platform",
            "artifact_kind",
            "artifact_ref",
            "artifact_sha256",
            "tools",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "capsule_sha256",
        }
        if set(data) != expected:
            raise ValueError("toolchain capsule contains missing or unknown fields")
        raw_tools = data["tools"]
        if not isinstance(raw_tools, list):
            raise ValueError("tools must be an array")
        capsule = cls(
            capsule_id=_string(data["capsule_id"], "capsule_id", maximum=96),
            family=_family(data["family"]),
            platform=cast(ToolchainPlatform, data["platform"]),
            artifact_kind=cast(Literal["oci_image"], data["artifact_kind"]),
            artifact_ref=_string(data["artifact_ref"], "artifact_ref", maximum=512),
            artifact_sha256=_sha256(data["artifact_sha256"], "artifact_sha256"),
            tools=tuple(ToolchainTool.from_dict(item) for item in raw_tools),
            execution_authority=_false(data["execution_authority"], "execution_authority"),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(data["host_write_authority"], "host_write_authority"),
        )
        if data["capsule_sha256"] != capsule.sha256():
            raise ValueError("toolchain capsule digest does not match canonical content")
        return capsule


@dataclass(frozen=True)
class ToolchainBinding:
    app_id: str
    commit_sha: str
    plan_sha256: str
    requirement_sha256: str
    capsule_sha256: str
    family: ToolchainFamily
    status: Literal["compatible_for_review"] = "compatible_for_review"
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = TOOLCHAIN_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOLCHAIN_BINDING_SCHEMA_VERSION:
            raise ValueError(f"Unsupported toolchain binding schema: {self.schema_version}")
        _string(self.app_id, "app_id", maximum=64)
        if not re.fullmatch(r"^[0-9a-f]{40,64}$", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase hexadecimal commit identifier")
        for value, label in (
            (self.plan_sha256, "plan_sha256"),
            (self.requirement_sha256, "requirement_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
        ):
            _sha256(value, label)
        if self.family not in _FAMILY_TOOLS:
            raise ValueError(f"Unsupported toolchain family: {self.family}")
        if self.status != "compatible_for_review":
            raise ValueError("v0.51 binding status must be compatible_for_review")
        if any(
            value is not False
            for value in (
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("toolchain bindings never grant authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "requirement_sha256": self.requirement_sha256,
            "capsule_sha256": self.capsule_sha256,
            "family": self.family,
            "status": self.status,
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
        result["binding_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainBinding:
        data = _mapping(value, "toolchain binding")
        expected = {
            "schema_version",
            "app_id",
            "commit_sha",
            "plan_sha256",
            "requirement_sha256",
            "capsule_sha256",
            "family",
            "status",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "binding_sha256",
        }
        if set(data) != expected:
            raise ValueError("toolchain binding contains missing or unknown fields")
        binding = cls(
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            plan_sha256=_sha256(data["plan_sha256"], "plan_sha256"),
            requirement_sha256=_sha256(data["requirement_sha256"], "requirement_sha256"),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            family=_family(data["family"]),
            status=cast(Literal["compatible_for_review"], data["status"]),
            execution_authority=_false(data["execution_authority"], "execution_authority"),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(data["host_write_authority"], "host_write_authority"),
        )
        if data["binding_sha256"] != binding.sha256():
            raise ValueError("toolchain binding digest does not match canonical content")
        return binding


def derive_toolchain_requirement(plan: BuildPlan) -> ToolchainRequirement:
    required_tools = tuple(sorted(plan.required_tools))

    if plan.status == "no_build_required" or not required_tools:
        return ToolchainRequirement(
            app_id=plan.app_id,
            commit_sha=plan.commit_sha,
            plan_sha256=plan.sha256(),
            strategy=plan.strategy,
            family=None,
            required_tools=required_tools,
            status="no_capsule_required",
        )

    family: ToolchainFamily | None = None
    if (
        plan.strategy == "node_package_manager"
        and plan.package_manager == "npm"
        and set(required_tools) == _FAMILY_TOOLS["node_npm"]
    ):
        family = "node_npm"
    elif (
        plan.strategy == "python_pep517_wheel"
        and set(required_tools) == _FAMILY_TOOLS["python_pep517"]
    ):
        family = "python_pep517"
    elif (
        plan.strategy == "rust_cargo_release"
        and set(required_tools) == _FAMILY_TOOLS["rust_cargo"]
    ):
        family = "rust_cargo"
    elif (
        plan.strategy == "go_module_build"
        and set(required_tools) == _FAMILY_TOOLS["go_module"]
    ):
        family = "go_module"

    return ToolchainRequirement(
        app_id=plan.app_id,
        commit_sha=plan.commit_sha,
        plan_sha256=plan.sha256(),
        strategy=plan.strategy,
        family=family,
        required_tools=required_tools,
        status="capsule_required" if family is not None else "unsupported_toolchain",
    )


def bind_toolchain_capsule(
    requirement: ToolchainRequirement,
    capsule: ToolchainCapsule,
) -> ToolchainBinding:
    if requirement.status != "capsule_required" or requirement.family is None:
        raise ValueError("only capsule_required requirements can be bound")
    if requirement.family != capsule.family:
        raise ValueError("toolchain capsule family does not match requirement")
    capsule_tools = {tool.name for tool in capsule.tools}
    if set(requirement.required_tools) != capsule_tools:
        raise ValueError("toolchain capsule tools do not exactly match requirement")

    return ToolchainBinding(
        app_id=requirement.app_id,
        commit_sha=requirement.commit_sha,
        plan_sha256=requirement.plan_sha256,
        requirement_sha256=requirement.sha256(),
        capsule_sha256=capsule.sha256(),
        family=capsule.family,
    )
