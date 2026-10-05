from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .runtime_backend_selection import (
    RuntimeBackendQualification,
    RuntimeBackendSelectionReceipt,
    qualify_runtime_backend,
)
from .toolchain_runtime import (
    OciRuntimeBuildRunner,
    ToolchainRuntimeExecutionResult,
    ToolchainRuntimeRequest,
    ToolchainRuntimeService,
)

SELECTED_TOOLCHAIN_RUNTIME_REQUEST_SCHEMA_VERSION = (
    "phios.selected_toolchain_runtime_request.v0.1"
)
RUNTIME_SELECTION_EXECUTION_RECEIPT_SCHEMA_VERSION = (
    "phios.runtime_selection_execution_receipt.v0.1"
)

RuntimeSelectionExecutionStatus = Literal["executed_selected_backend"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ADAPTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")


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


@dataclass(frozen=True)
class SelectedToolchainRuntimeRequest:
    runtime_request: ToolchainRuntimeRequest
    qualification: RuntimeBackendQualification
    selection: RuntimeBackendSelectionReceipt
    approved_selection_receipt_sha256: str
    schema_version: str = SELECTED_TOOLCHAIN_RUNTIME_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SELECTED_TOOLCHAIN_RUNTIME_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported selected runtime request schema: {self.schema_version}"
            )
        if self.selection.status != "selected_for_request":
            raise ValueError("v0.57 requires a selected_for_request backend receipt")
        if self.selection.operator_confirmed is not True:
            raise ValueError("v0.57 requires explicit operator-confirmed selection")
        if self.approved_selection_receipt_sha256 != self.selection.sha256():
            raise ValueError(
                "approved selection receipt SHA-256 does not match the canonical receipt"
            )
        if self.selection.qualification_sha256 != self.qualification.sha256():
            raise ValueError(
                "backend selection does not bind the supplied qualification"
            )
        if self.selection.sandbox_plan_sha256 != self.runtime_request.sandbox_plan.sha256():
            raise ValueError("backend selection does not match runtime sandbox plan")
        if self.selection.capsule_sha256 != self.runtime_request.capsule.sha256():
            raise ValueError("backend selection does not match runtime capsule")
        if self.selection.attestation_sha256 != self.runtime_request.attestation.sha256():
            raise ValueError("backend selection does not match runtime attestation")
        if (
            self.selection.selected_adapter_id
            != self.qualification.runtime_identity.adapter_id
        ):
            raise ValueError("selected adapter does not match backend qualification")
        if (
            self.selection.runtime_identity_sha256
            != self.qualification.runtime_identity.sha256()
        ):
            raise ValueError("selection runtime identity does not match qualification")
        if self.selection.controls_sha256 != self.qualification.controls.sha256():
            raise ValueError("selection runtime controls do not match qualification")


@dataclass(frozen=True)
class RuntimeSelectionExecutionReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    commit_sha: str
    execution_approval_id: str
    selection_receipt_sha256: str
    qualification_sha256: str
    sandbox_plan_sha256: str
    capsule_sha256: str
    attestation_sha256: str
    selected_adapter_id: str
    runtime_identity_sha256: str
    controls_sha256: str
    toolchain_runtime_receipt_sha256: str
    status: RuntimeSelectionExecutionStatus = "executed_selected_backend"
    operator_selection_verified: bool = True
    reusable_execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = RUNTIME_SELECTION_EXECUTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SELECTION_EXECUTION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported runtime selection receipt schema: {self.schema_version}"
            )
        try:
            parsed_receipt = uuid.UUID(self.receipt_id)
            parsed_approval = uuid.UUID(self.execution_approval_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("receipt and execution approval IDs must be UUIDs") from exc
        if str(parsed_receipt) != self.receipt_id:
            raise ValueError("receipt_id must use canonical lowercase UUID syntax")
        if str(parsed_approval) != self.execution_approval_id:
            raise ValueError(
                "execution_approval_id must use canonical lowercase UUID syntax"
            )
        _string(self.timestamp_utc, "timestamp_utc", maximum=64)
        _string(self.app_id, "app_id", maximum=64)
        if not re.fullmatch(r"^[0-9a-f]{40,64}$", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase hexadecimal identifier")
        for value, label in (
            (self.selection_receipt_sha256, "selection_receipt_sha256"),
            (self.qualification_sha256, "qualification_sha256"),
            (self.sandbox_plan_sha256, "sandbox_plan_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.attestation_sha256, "attestation_sha256"),
            (self.runtime_identity_sha256, "runtime_identity_sha256"),
            (self.controls_sha256, "controls_sha256"),
            (
                self.toolchain_runtime_receipt_sha256,
                "toolchain_runtime_receipt_sha256",
            ),
        ):
            _sha256(value, label)
        if not _ADAPTER_ID_RE.fullmatch(self.selected_adapter_id):
            raise ValueError("selected_adapter_id has invalid syntax")
        if self.status != "executed_selected_backend":
            raise ValueError("v0.57 receipt status must be executed_selected_backend")
        _true(self.operator_selection_verified, "operator_selection_verified")
        if any(
            value is not False
            for value in (
                self.reusable_execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("v0.57 execution receipts never grant downstream authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "execution_approval_id": self.execution_approval_id,
            "selection_receipt_sha256": self.selection_receipt_sha256,
            "qualification_sha256": self.qualification_sha256,
            "sandbox_plan_sha256": self.sandbox_plan_sha256,
            "capsule_sha256": self.capsule_sha256,
            "attestation_sha256": self.attestation_sha256,
            "selected_adapter_id": self.selected_adapter_id,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "controls_sha256": self.controls_sha256,
            "toolchain_runtime_receipt_sha256": (
                self.toolchain_runtime_receipt_sha256
            ),
            "status": self.status,
            "operator_selection_verified": True,
            "reusable_execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeSelectionExecutionReceipt:
        data = _mapping(value, "runtime selection execution receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "commit_sha",
            "execution_approval_id",
            "selection_receipt_sha256",
            "qualification_sha256",
            "sandbox_plan_sha256",
            "capsule_sha256",
            "attestation_sha256",
            "selected_adapter_id",
            "runtime_identity_sha256",
            "controls_sha256",
            "toolchain_runtime_receipt_sha256",
            "status",
            "operator_selection_verified",
            "reusable_execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "runtime selection execution receipt contains missing or unknown fields"
            )
        receipt = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=36),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=64),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            execution_approval_id=_string(
                data["execution_approval_id"], "execution_approval_id", maximum=36
            ),
            selection_receipt_sha256=_sha256(
                data["selection_receipt_sha256"], "selection_receipt_sha256"
            ),
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
            toolchain_runtime_receipt_sha256=_sha256(
                data["toolchain_runtime_receipt_sha256"],
                "toolchain_runtime_receipt_sha256",
            ),
            status=cast(RuntimeSelectionExecutionStatus, data["status"]),
            operator_selection_verified=_true(
                data["operator_selection_verified"],
                "operator_selection_verified",
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
        if data["receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "runtime selection execution receipt digest does not match content"
            )
        return receipt


@dataclass(frozen=True)
class SelectedToolchainRuntimeExecutionResult:
    runtime_result: ToolchainRuntimeExecutionResult
    selection_receipt: RuntimeSelectionExecutionReceipt
    selection_receipt_path: str | None
    selection_receipt_persisted: bool


def _write_receipt(path: Path, receipt: RuntimeSelectionExecutionReceipt) -> None:
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


class SelectedToolchainRuntimeService:
    """Execute v0.54 only after an exact v0.56 operator backend selection."""

    def __init__(self, *, runner: OciRuntimeBuildRunner) -> None:
        self.runner = runner

    def execute(
        self,
        request: SelectedToolchainRuntimeRequest,
        *,
        execution_root: Path,
        receipt_root: Path | None = None,
    ) -> SelectedToolchainRuntimeExecutionResult:
        request = SelectedToolchainRuntimeRequest(
            runtime_request=request.runtime_request,
            qualification=request.qualification,
            selection=request.selection,
            approved_selection_receipt_sha256=(
                request.approved_selection_receipt_sha256
            ),
        )

        runtime_request = request.runtime_request
        live_qualification = qualify_runtime_backend(
            runtime_request.sandbox_plan,
            runtime_request.capsule,
            runtime_request.attestation,
            self.runner,
        )
        if live_qualification.sha256() != request.qualification.sha256():
            raise ValueError(
                "live runtime backend qualification differs from operator-selected qualification"
            )
        if (
            live_qualification.runtime_identity.sha256()
            != request.selection.runtime_identity_sha256
        ):
            raise ValueError("live runtime identity differs from operator selection")
        if live_qualification.controls.sha256() != request.selection.controls_sha256:
            raise ValueError("live runtime controls differ from operator selection")

        result = ToolchainRuntimeService(runner=self.runner).execute(
            runtime_request,
            execution_root=execution_root,
            receipt_root=receipt_root,
        )

        if (
            result.runtime.runtime_identity.sha256()
            != request.selection.runtime_identity_sha256
        ):
            raise ValueError(
                "executed runtime identity differs from operator-selected backend"
            )
        if result.runtime.controls.sha256() != request.selection.controls_sha256:
            raise ValueError(
                "executed runtime controls differ from operator-selected backend"
            )

        receipt = RuntimeSelectionExecutionReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=runtime_request.build_plan.app_id,
            commit_sha=runtime_request.build_plan.commit_sha,
            execution_approval_id=runtime_request.execution_approval_id,
            selection_receipt_sha256=request.selection.sha256(),
            qualification_sha256=request.qualification.sha256(),
            sandbox_plan_sha256=runtime_request.sandbox_plan.sha256(),
            capsule_sha256=runtime_request.capsule.sha256(),
            attestation_sha256=runtime_request.attestation.sha256(),
            selected_adapter_id=request.selection.selected_adapter_id,
            runtime_identity_sha256=result.runtime.runtime_identity.sha256(),
            controls_sha256=result.runtime.controls.sha256(),
            toolchain_runtime_receipt_sha256=result.runtime.sha256(),
        )

        root = execution_root.expanduser().resolve()
        receipts = (receipt_root or (root / ".phios-receipts")).expanduser().resolve()
        path = receipts / f"runtime-selection-{receipt.receipt_id}.json"
        persisted = True
        path_text: str | None = str(path)
        try:
            _write_receipt(path, receipt)
        except OSError:
            persisted = False
            path_text = None

        return SelectedToolchainRuntimeExecutionResult(
            runtime_result=result,
            selection_receipt=receipt,
            selection_receipt_path=path_text,
            selection_receipt_persisted=persisted,
        )
