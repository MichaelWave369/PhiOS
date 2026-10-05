from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, cast

from .podman_runtime import (
    PODMAN_ROOTLESS_ADAPTER_ID,
    PODMAN_ROOTLESS_ADAPTER_VERSION,
)
from .toolchain_attestation import ToolchainAttestation, ToolchainSandboxPlan
from .toolchain_capsule import ToolchainCapsule
from .toolchain_runtime import (
    OciRuntimeAdapterIdentity,
    OciRuntimeBuildRunner,
    OciRuntimeControlEvidence,
)

RUNTIME_BACKEND_QUALIFICATION_SCHEMA_VERSION = (
    "phios.runtime_backend_qualification.v0.1"
)
RUNTIME_BACKEND_SELECTION_PROPOSAL_SCHEMA_VERSION = (
    "phios.runtime_backend_selection_proposal.v0.1"
)
RUNTIME_BACKEND_SELECTION_RECEIPT_SCHEMA_VERSION = (
    "phios.runtime_backend_selection_receipt.v0.1"
)

RuntimeBackendQualificationStatus = Literal["qualified_for_selection"]
RuntimeBackendSelectionProposalStatus = Literal[
    "no_qualified_backend",
    "candidate_available",
    "operator_choice_required",
]
RuntimeBackendSelectionStatus = Literal["selected_for_request"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ADAPTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")

_RECOGNIZED_ADAPTERS: dict[str, tuple[str, str]] = {
    PODMAN_ROOTLESS_ADAPTER_ID: (PODMAN_ROOTLESS_ADAPTER_VERSION, "podman"),
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


def _true(value: Any, label: str) -> bool:
    if value is not True:
        raise ValueError(f"{label} must remain true")
    return True


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _platform_matches_capsule(
    identity: OciRuntimeAdapterIdentity,
    capsule: ToolchainCapsule,
) -> bool:
    if capsule.platform != "linux_x86_64":
        return False
    system = identity.platform_system.strip().lower()
    machine = identity.platform_machine.strip().lower()
    return system == "linux" and machine in {"x86_64", "amd64"}


@dataclass(frozen=True)
class RuntimeBackendQualification:
    sandbox_plan_sha256: str
    capsule_sha256: str
    attestation_sha256: str
    capsule_family: str
    runtime_identity: OciRuntimeAdapterIdentity
    controls: OciRuntimeControlEvidence
    status: RuntimeBackendQualificationStatus = "qualified_for_selection"
    selection_authority: bool = False
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = RUNTIME_BACKEND_QUALIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_BACKEND_QUALIFICATION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported backend qualification schema: {self.schema_version}"
            )
        for value, label in (
            (self.sandbox_plan_sha256, "sandbox_plan_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.attestation_sha256, "attestation_sha256"),
        ):
            _sha256(value, label)
        _string(self.capsule_family, "capsule_family", maximum=64)
        recognized = _RECOGNIZED_ADAPTERS.get(self.runtime_identity.adapter_id)
        if recognized is None:
            raise ValueError(
                f"unrecognized runtime backend adapter: {self.runtime_identity.adapter_id}"
            )
        expected_version, expected_backend = recognized
        if self.runtime_identity.adapter_version != expected_version:
            raise ValueError("runtime backend adapter version is not recognized")
        if self.runtime_identity.backend != expected_backend:
            raise ValueError(
                "runtime backend implementation does not match adapter contract"
            )
        if self.status != "qualified_for_selection":
            raise ValueError("v0.56 qualification status must be qualified_for_selection")
        if any(
            value is not False
            for value in (
                self.selection_authority,
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("backend qualification never grants authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sandbox_plan_sha256": self.sandbox_plan_sha256,
            "capsule_sha256": self.capsule_sha256,
            "attestation_sha256": self.attestation_sha256,
            "capsule_family": self.capsule_family,
            "runtime_identity": self.runtime_identity.to_dict(),
            "controls": self.controls.to_dict(),
            "status": self.status,
            "selection_authority": False,
            "execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["qualification_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeBackendQualification:
        data = _mapping(value, "runtime backend qualification")
        expected = {
            "schema_version",
            "sandbox_plan_sha256",
            "capsule_sha256",
            "attestation_sha256",
            "capsule_family",
            "runtime_identity",
            "controls",
            "status",
            "selection_authority",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "qualification_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "runtime backend qualification contains missing or unknown fields"
            )
        qualification = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            sandbox_plan_sha256=_sha256(
                data["sandbox_plan_sha256"], "sandbox_plan_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            attestation_sha256=_sha256(
                data["attestation_sha256"], "attestation_sha256"
            ),
            capsule_family=_string(
                data["capsule_family"], "capsule_family", maximum=64
            ),
            runtime_identity=OciRuntimeAdapterIdentity.from_dict(
                data["runtime_identity"]
            ),
            controls=OciRuntimeControlEvidence.from_dict(data["controls"]),
            status=cast(RuntimeBackendQualificationStatus, data["status"]),
            selection_authority=_false(
                data["selection_authority"], "selection_authority"
            ),
            execution_authority=_false(
                data["execution_authority"], "execution_authority"
            ),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(
                data["host_write_authority"], "host_write_authority"
            ),
        )
        if data["qualification_sha256"] != qualification.sha256():
            raise ValueError(
                "runtime backend qualification digest does not match canonical content"
            )
        return qualification


@dataclass(frozen=True)
class RuntimeBackendSelectionProposal:
    sandbox_plan_sha256: str
    capsule_sha256: str
    attestation_sha256: str
    candidate_qualification_sha256s: tuple[str, ...]
    candidate_adapter_ids: tuple[str, ...]
    status: RuntimeBackendSelectionProposalStatus
    advisory_only: bool = True
    selection_authority: bool = False
    execution_authority: bool = False
    schema_version: str = RUNTIME_BACKEND_SELECTION_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_BACKEND_SELECTION_PROPOSAL_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported backend selection proposal schema: {self.schema_version}"
            )
        for value, label in (
            (self.sandbox_plan_sha256, "sandbox_plan_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.attestation_sha256, "attestation_sha256"),
        ):
            _sha256(value, label)
        if self.status not in {
            "no_qualified_backend",
            "candidate_available",
            "operator_choice_required",
        }:
            raise ValueError(f"Unsupported backend selection proposal status: {self.status}")
        if self.advisory_only is not True:
            raise ValueError("v0.56 backend proposals must remain advisory_only")
        _false(self.selection_authority, "selection_authority")
        _false(self.execution_authority, "execution_authority")
        if len(self.candidate_qualification_sha256s) != len(
            self.candidate_adapter_ids
        ):
            raise ValueError("backend proposal candidate arrays must remain aligned")
        if len(set(self.candidate_qualification_sha256s)) != len(
            self.candidate_qualification_sha256s
        ):
            raise ValueError("backend proposal candidates must be unique")
        for digest in self.candidate_qualification_sha256s:
            _sha256(digest, "candidate qualification SHA-256")
        for adapter_id in self.candidate_adapter_ids:
            if not _ADAPTER_ID_RE.fullmatch(adapter_id):
                raise ValueError(f"Invalid backend adapter ID: {adapter_id}")

        count = len(self.candidate_qualification_sha256s)
        if self.status == "no_qualified_backend" and count != 0:
            raise ValueError("no_qualified_backend proposals must have zero candidates")
        if self.status == "candidate_available" and count != 1:
            raise ValueError("candidate_available proposals must have one candidate")
        if self.status == "operator_choice_required" and count < 2:
            raise ValueError(
                "operator_choice_required proposals must have multiple candidates"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sandbox_plan_sha256": self.sandbox_plan_sha256,
            "capsule_sha256": self.capsule_sha256,
            "attestation_sha256": self.attestation_sha256,
            "candidate_qualification_sha256s": list(
                self.candidate_qualification_sha256s
            ),
            "candidate_adapter_ids": list(self.candidate_adapter_ids),
            "status": self.status,
            "advisory_only": True,
            "selection_authority": False,
            "execution_authority": False,
        }

    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["proposal_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeBackendSelectionProposal:
        data = _mapping(value, "runtime backend selection proposal")
        expected = {
            "schema_version",
            "sandbox_plan_sha256",
            "capsule_sha256",
            "attestation_sha256",
            "candidate_qualification_sha256s",
            "candidate_adapter_ids",
            "status",
            "advisory_only",
            "selection_authority",
            "execution_authority",
            "proposal_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "runtime backend selection proposal contains missing or unknown fields"
            )
        raw_digests = data["candidate_qualification_sha256s"]
        raw_ids = data["candidate_adapter_ids"]
        if not isinstance(raw_digests, list) or not all(
            isinstance(item, str) for item in raw_digests
        ):
            raise ValueError("candidate_qualification_sha256s must be an array of strings")
        if not isinstance(raw_ids, list) or not all(
            isinstance(item, str) for item in raw_ids
        ):
            raise ValueError("candidate_adapter_ids must be an array of strings")

        proposal = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            sandbox_plan_sha256=_sha256(
                data["sandbox_plan_sha256"], "sandbox_plan_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            attestation_sha256=_sha256(
                data["attestation_sha256"], "attestation_sha256"
            ),
            candidate_qualification_sha256s=tuple(raw_digests),
            candidate_adapter_ids=tuple(raw_ids),
            status=cast(RuntimeBackendSelectionProposalStatus, data["status"]),
            advisory_only=_true(data["advisory_only"], "advisory_only"),
            selection_authority=_false(
                data["selection_authority"], "selection_authority"
            ),
            execution_authority=_false(
                data["execution_authority"], "execution_authority"
            ),
        )
        if data["proposal_sha256"] != proposal.sha256():
            raise ValueError(
                "runtime backend selection proposal digest does not match content"
            )
        return proposal


@dataclass(frozen=True)
class RuntimeBackendSelectionReceipt:
    selection_id: str
    proposal_sha256: str
    qualification_sha256: str
    sandbox_plan_sha256: str
    capsule_sha256: str
    attestation_sha256: str
    selected_adapter_id: str
    runtime_identity_sha256: str
    controls_sha256: str
    status: RuntimeBackendSelectionStatus = "selected_for_request"
    operator_confirmed: bool = True
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = RUNTIME_BACKEND_SELECTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_BACKEND_SELECTION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported backend selection receipt schema: {self.schema_version}"
            )
        try:
            parsed = uuid.UUID(self.selection_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("selection_id must be a UUID") from exc
        if str(parsed) != self.selection_id:
            raise ValueError("selection_id must use canonical lowercase UUID syntax")
        for value, label in (
            (self.proposal_sha256, "proposal_sha256"),
            (self.qualification_sha256, "qualification_sha256"),
            (self.sandbox_plan_sha256, "sandbox_plan_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.attestation_sha256, "attestation_sha256"),
            (self.runtime_identity_sha256, "runtime_identity_sha256"),
            (self.controls_sha256, "controls_sha256"),
        ):
            _sha256(value, label)
        if not _ADAPTER_ID_RE.fullmatch(self.selected_adapter_id):
            raise ValueError("selected_adapter_id has invalid syntax")
        if self.status != "selected_for_request":
            raise ValueError("v0.56 selection status must be selected_for_request")
        _true(self.operator_confirmed, "operator_confirmed")
        if any(
            value is not False
            for value in (
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("backend selection never grants runtime authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "selection_id": self.selection_id,
            "proposal_sha256": self.proposal_sha256,
            "qualification_sha256": self.qualification_sha256,
            "sandbox_plan_sha256": self.sandbox_plan_sha256,
            "capsule_sha256": self.capsule_sha256,
            "attestation_sha256": self.attestation_sha256,
            "selected_adapter_id": self.selected_adapter_id,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "controls_sha256": self.controls_sha256,
            "status": self.status,
            "operator_confirmed": True,
            "execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["selection_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeBackendSelectionReceipt:
        data = _mapping(value, "runtime backend selection receipt")
        expected = {
            "schema_version",
            "selection_id",
            "proposal_sha256",
            "qualification_sha256",
            "sandbox_plan_sha256",
            "capsule_sha256",
            "attestation_sha256",
            "selected_adapter_id",
            "runtime_identity_sha256",
            "controls_sha256",
            "status",
            "operator_confirmed",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "selection_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "runtime backend selection receipt contains missing or unknown fields"
            )
        receipt = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            selection_id=_string(data["selection_id"], "selection_id", maximum=36),
            proposal_sha256=_sha256(data["proposal_sha256"], "proposal_sha256"),
            qualification_sha256=_sha256(
                data["qualification_sha256"], "qualification_sha256"
            ),
            sandbox_plan_sha256=_sha256(
                data["sandbox_plan_sha256"], "sandbox_plan_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            attestation_sha256=_sha256(
                data["attestation_sha256"], "attestation_sha256"
            ),
            selected_adapter_id=_string(
                data["selected_adapter_id"], "selected_adapter_id", maximum=96
            ),
            runtime_identity_sha256=_sha256(
                data["runtime_identity_sha256"], "runtime_identity_sha256"
            ),
            controls_sha256=_sha256(data["controls_sha256"], "controls_sha256"),
            status=cast(RuntimeBackendSelectionStatus, data["status"]),
            operator_confirmed=_true(
                data["operator_confirmed"], "operator_confirmed"
            ),
            execution_authority=_false(
                data["execution_authority"], "execution_authority"
            ),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(
                data["host_write_authority"], "host_write_authority"
            ),
        )
        if data["selection_receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "runtime backend selection receipt digest does not match content"
            )
        return receipt


def qualify_runtime_backend(
    sandbox_plan: ToolchainSandboxPlan,
    capsule: ToolchainCapsule,
    attestation: ToolchainAttestation,
    runner: OciRuntimeBuildRunner,
) -> RuntimeBackendQualification:
    if sandbox_plan.status != "ready_for_runtime_adapter_review":
        raise ValueError(
            "backend qualification requires ready_for_runtime_adapter_review status"
        )
    if sandbox_plan.sandbox_policy.network_mode != "deny":
        raise ValueError("backend qualification requires network-denied sandbox policy")
    if sandbox_plan.capsule_sha256 != capsule.sha256():
        raise ValueError("sandbox plan does not match reviewed capsule")
    if sandbox_plan.attestation_sha256 != attestation.sha256():
        raise ValueError("sandbox plan does not match reviewed attestation")
    if sandbox_plan.capsule_artifact_sha256 != capsule.artifact_sha256:
        raise ValueError("sandbox plan artifact digest does not match reviewed capsule")

    if runner.capsule_artifact_sha256 != capsule.artifact_sha256:
        raise ValueError("runtime backend capsule digest does not match reviewed capsule")
    if runner.capsule_storage_path != sandbox_plan.capsule_storage_path:
        raise ValueError("runtime backend storage path does not match sandbox plan")
    if runner.sandbox_plan_sha256 != sandbox_plan.sha256():
        raise ValueError("runtime backend sandbox plan does not match reviewed plan")
    if runner.policy_sha256 != sandbox_plan.sandbox_policy.sha256():
        raise ValueError("runtime backend sandbox policy does not match reviewed policy")
    if runner.network_sandbox_enforced is not True:
        raise ValueError("runtime backend must advertise enforced network denial")

    identity = runner.preflight()
    controls = runner.control_evidence()

    recognized = _RECOGNIZED_ADAPTERS.get(identity.adapter_id)
    if recognized is None:
        raise ValueError(f"unrecognized runtime backend adapter: {identity.adapter_id}")
    expected_version, expected_backend = recognized
    if identity.adapter_version != expected_version:
        raise ValueError("runtime backend adapter version is not recognized")
    if identity.backend != expected_backend:
        raise ValueError("runtime backend implementation does not match adapter contract")
    if not _platform_matches_capsule(identity, capsule):
        raise ValueError("runtime backend platform does not match capsule platform")

    return RuntimeBackendQualification(
        sandbox_plan_sha256=sandbox_plan.sha256(),
        capsule_sha256=capsule.sha256(),
        attestation_sha256=attestation.sha256(),
        capsule_family=capsule.family,
        runtime_identity=identity,
        controls=controls,
    )


def propose_runtime_backend_selection(
    sandbox_plan: ToolchainSandboxPlan,
    capsule: ToolchainCapsule,
    attestation: ToolchainAttestation,
    qualifications: tuple[RuntimeBackendQualification, ...],
) -> RuntimeBackendSelectionProposal:
    candidates: list[RuntimeBackendQualification] = []
    seen: set[str] = set()

    for qualification in qualifications:
        if qualification.sandbox_plan_sha256 != sandbox_plan.sha256():
            raise ValueError("backend qualification does not match sandbox plan")
        if qualification.capsule_sha256 != capsule.sha256():
            raise ValueError("backend qualification does not match capsule")
        if qualification.attestation_sha256 != attestation.sha256():
            raise ValueError("backend qualification does not match attestation")
        if qualification.capsule_family != capsule.family:
            raise ValueError("backend qualification does not match capsule family")

        digest = qualification.sha256()
        if digest in seen:
            continue
        seen.add(digest)
        candidates.append(qualification)

    candidates.sort(
        key=lambda item: (
            item.runtime_identity.adapter_id,
            item.runtime_identity.backend_version,
            item.sha256(),
        )
    )

    count = len(candidates)
    if count == 0:
        status: RuntimeBackendSelectionProposalStatus = "no_qualified_backend"
    elif count == 1:
        status = "candidate_available"
    else:
        status = "operator_choice_required"

    return RuntimeBackendSelectionProposal(
        sandbox_plan_sha256=sandbox_plan.sha256(),
        capsule_sha256=capsule.sha256(),
        attestation_sha256=attestation.sha256(),
        candidate_qualification_sha256s=tuple(item.sha256() for item in candidates),
        candidate_adapter_ids=tuple(
            item.runtime_identity.adapter_id for item in candidates
        ),
        status=status,
    )


def select_runtime_backend(
    proposal: RuntimeBackendSelectionProposal,
    qualification: RuntimeBackendQualification,
    *,
    selection_id: str,
    approved_qualification_sha256: str,
) -> RuntimeBackendSelectionReceipt:
    if proposal.status == "no_qualified_backend":
        raise ValueError("cannot select a backend from a no_qualified_backend proposal")
    if qualification.sha256() not in proposal.candidate_qualification_sha256s:
        raise ValueError("selected qualification is not a candidate in this proposal")
    if approved_qualification_sha256 != qualification.sha256():
        raise ValueError(
            "approved qualification SHA-256 does not match selected qualification"
        )
    if qualification.sandbox_plan_sha256 != proposal.sandbox_plan_sha256:
        raise ValueError("selected qualification does not match proposal sandbox plan")
    if qualification.capsule_sha256 != proposal.capsule_sha256:
        raise ValueError("selected qualification does not match proposal capsule")
    if qualification.attestation_sha256 != proposal.attestation_sha256:
        raise ValueError("selected qualification does not match proposal attestation")

    return RuntimeBackendSelectionReceipt(
        selection_id=selection_id,
        proposal_sha256=proposal.sha256(),
        qualification_sha256=qualification.sha256(),
        sandbox_plan_sha256=proposal.sandbox_plan_sha256,
        capsule_sha256=proposal.capsule_sha256,
        attestation_sha256=proposal.attestation_sha256,
        selected_adapter_id=qualification.runtime_identity.adapter_id,
        runtime_identity_sha256=qualification.runtime_identity.sha256(),
        controls_sha256=qualification.controls.sha256(),
    )
