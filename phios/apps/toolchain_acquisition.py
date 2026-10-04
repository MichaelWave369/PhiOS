from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from .toolchain_capsule import (
    ToolchainBinding,
    ToolchainCapsule,
    ToolchainRequirement,
    bind_toolchain_capsule,
)

CAPSULE_ACQUISITION_REQUEST_SCHEMA_VERSION = "phios.capsule_acquisition_request.v0.1"
CAPSULE_ACQUISITION_RECEIPT_SCHEMA_VERSION = "phios.capsule_acquisition_receipt.v0.1"

_DEFAULT_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024
_COPY_CHUNK_BYTES = 1024 * 1024


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
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _non_negative_integer(value: Any, label: str, *, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    if value > maximum:
        raise ValueError(f"{label} exceeds the bounded maximum")
    return value


def _false(value: Any, label: str) -> bool:
    if value is not False:
        raise ValueError(f"{label} must remain false")
    return False


@dataclass(frozen=True)
class CapsuleAcquisitionRequest:
    requirement: ToolchainRequirement
    capsule: ToolchainCapsule
    binding: ToolchainBinding
    approved_binding_sha256: str
    schema_version: str = CAPSULE_ACQUISITION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAPSULE_ACQUISITION_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported capsule acquisition request schema: {self.schema_version}"
            )

        reconstructed = bind_toolchain_capsule(self.requirement, self.capsule)
        if reconstructed.sha256() != self.binding.sha256():
            raise ValueError(
                "toolchain binding does not match the exact requirement and capsule"
            )
        if self.approved_binding_sha256 != self.binding.sha256():
            raise ValueError(
                "approved binding SHA-256 does not match the canonical toolchain binding"
            )


@dataclass(frozen=True)
class ProvidedCapsuleArtifact:
    path: Path
    source_ref: str


class CapsuleArtifactProvider(Protocol):
    def provide(self, capsule: ToolchainCapsule) -> ProvidedCapsuleArtifact: ...


class LocalCapsuleArtifactProvider:
    """Resolve an already-obtained capsule artifact from an explicit ref-to-file map."""

    def __init__(self, artifacts: Mapping[str, Path]) -> None:
        self._artifacts = {key: Path(value) for key, value in artifacts.items()}

    def provide(self, capsule: ToolchainCapsule) -> ProvidedCapsuleArtifact:
        try:
            path = self._artifacts[capsule.artifact_ref]
        except KeyError as exc:
            raise ValueError("no local capsule artifact is mapped for the reviewed artifact ref") from exc
        return ProvidedCapsuleArtifact(path=path, source_ref=capsule.artifact_ref)


@dataclass(frozen=True)
class CapsuleAcquisitionReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    commit_sha: str
    plan_sha256: str
    requirement_sha256: str
    capsule_sha256: str
    binding_sha256: str
    capsule_id: str
    family: str
    artifact_kind: str
    artifact_ref: str
    artifact_sha256: str
    artifact_bytes: int
    storage_path: str
    storage_state: str
    status: str = "verified_available"
    execution_authority: bool = False
    network_authority: bool = False
    install_authority: bool = False
    host_write_authority: bool = False
    schema_version: str = CAPSULE_ACQUISITION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAPSULE_ACQUISITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported capsule acquisition receipt schema: {self.schema_version}"
            )
        _string(self.receipt_id, "receipt_id", maximum=64)
        _string(self.timestamp_utc, "timestamp_utc", maximum=64)
        _string(self.app_id, "app_id", maximum=64)
        _string(self.commit_sha, "commit_sha", maximum=64)
        for value, label in (
            (self.plan_sha256, "plan_sha256"),
            (self.requirement_sha256, "requirement_sha256"),
            (self.capsule_sha256, "capsule_sha256"),
            (self.binding_sha256, "binding_sha256"),
            (self.artifact_sha256, "artifact_sha256"),
        ):
            _sha256(value, label)
        _string(self.capsule_id, "capsule_id", maximum=96)
        _string(self.family, "family", maximum=64)
        if self.artifact_kind != "oci_image":
            raise ValueError("v0.52 receipts support only oci_image artifacts")
        _string(self.artifact_ref, "artifact_ref", maximum=512)
        _non_negative_integer(
            self.artifact_bytes,
            "artifact_bytes",
            maximum=_DEFAULT_MAX_ARTIFACT_BYTES,
        )
        if self.artifact_bytes == 0:
            raise ValueError("verified capsule artifacts must not be empty")
        storage = Path(_string(self.storage_path, "storage_path", maximum=4096)).expanduser()
        if not storage.is_absolute():
            raise ValueError("storage_path must be absolute")
        if self.storage_state not in {"created", "reused_verified"}:
            raise ValueError("unsupported capsule storage_state")
        if self.status != "verified_available":
            raise ValueError("v0.52 receipt status must be verified_available")
        if any(
            value is not False
            for value in (
                self.execution_authority,
                self.network_authority,
                self.install_authority,
                self.host_write_authority,
            )
        ):
            raise ValueError("capsule acquisition receipts never confer downstream authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "requirement_sha256": self.requirement_sha256,
            "capsule_sha256": self.capsule_sha256,
            "binding_sha256": self.binding_sha256,
            "capsule_id": self.capsule_id,
            "family": self.family,
            "artifact_kind": self.artifact_kind,
            "artifact_ref": self.artifact_ref,
            "artifact_sha256": self.artifact_sha256,
            "artifact_bytes": self.artifact_bytes,
            "storage_path": self.storage_path,
            "storage_state": self.storage_state,
            "status": self.status,
            "execution_authority": False,
            "network_authority": False,
            "install_authority": False,
            "host_write_authority": False,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> CapsuleAcquisitionReceipt:
        data = _mapping(value, "capsule acquisition receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "commit_sha",
            "plan_sha256",
            "requirement_sha256",
            "capsule_sha256",
            "binding_sha256",
            "capsule_id",
            "family",
            "artifact_kind",
            "artifact_ref",
            "artifact_sha256",
            "artifact_bytes",
            "storage_path",
            "storage_state",
            "status",
            "execution_authority",
            "network_authority",
            "install_authority",
            "host_write_authority",
            "receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("capsule acquisition receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=64),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "commit_sha", maximum=64),
            plan_sha256=_sha256(data["plan_sha256"], "plan_sha256"),
            requirement_sha256=_sha256(
                data["requirement_sha256"], "requirement_sha256"
            ),
            capsule_sha256=_sha256(data["capsule_sha256"], "capsule_sha256"),
            binding_sha256=_sha256(data["binding_sha256"], "binding_sha256"),
            capsule_id=_string(data["capsule_id"], "capsule_id", maximum=96),
            family=_string(data["family"], "family", maximum=64),
            artifact_kind=_string(data["artifact_kind"], "artifact_kind", maximum=32),
            artifact_ref=_string(data["artifact_ref"], "artifact_ref", maximum=512),
            artifact_sha256=_sha256(data["artifact_sha256"], "artifact_sha256"),
            artifact_bytes=_non_negative_integer(
                data["artifact_bytes"],
                "artifact_bytes",
                maximum=_DEFAULT_MAX_ARTIFACT_BYTES,
            ),
            storage_path=_string(data["storage_path"], "storage_path", maximum=4096),
            storage_state=_string(data["storage_state"], "storage_state", maximum=32),
            status=_string(data["status"], "status", maximum=32),
            execution_authority=_false(
                data["execution_authority"], "execution_authority"
            ),
            network_authority=_false(data["network_authority"], "network_authority"),
            install_authority=_false(data["install_authority"], "install_authority"),
            host_write_authority=_false(
                data["host_write_authority"], "host_write_authority"
            ),
        )
        if data["receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "capsule acquisition receipt digest does not match canonical content"
            )
        return receipt


def _regular_file_size(path: Path, *, maximum: int) -> int:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError("capsule artifact does not exist") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("capsule artifact symlinks are not allowed")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("capsule artifact must be a regular file")
    if info.st_size <= 0:
        raise ValueError("capsule artifact must not be empty")
    if info.st_size > maximum:
        raise ValueError(f"capsule artifact exceeds {maximum} bytes")
    return info.st_size


def _hash_file(path: Path, *, maximum: int) -> tuple[str, int]:
    expected_size = _regular_file_size(path, maximum=maximum)
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(_COPY_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ValueError(f"capsule artifact exceeds {maximum} bytes")
            digest.update(chunk)
    if total != expected_size:
        raise ValueError("capsule artifact changed while it was being verified")
    return digest.hexdigest(), total


def _copy_verified(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    maximum: int,
) -> int:
    expected_size = _regular_file_size(source, maximum=maximum)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    digest = hashlib.sha256()
    total = 0
    try:
        with source.open("rb") as src, temporary.open("xb") as dst:
            while True:
                chunk = src.read(_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise ValueError(f"capsule artifact exceeds {maximum} bytes")
                digest.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        if total != expected_size:
            raise ValueError("capsule artifact changed while it was being acquired")
        if digest.hexdigest() != expected_sha256:
            raise ValueError("capsule artifact SHA-256 does not match the reviewed capsule")
        try:
            os.chmod(temporary, 0o444)
        except OSError:
            pass
        temporary.replace(destination)
        return total
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_receipt(path: Path, receipt: CapsuleAcquisitionReceipt) -> None:
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


class CapsuleAcquisitionService:
    """Acquire and verify reviewed capsule bytes without executing the capsule."""

    def __init__(
        self,
        *,
        provider: CapsuleArtifactProvider | None = None,
        max_artifact_bytes: int = _DEFAULT_MAX_ARTIFACT_BYTES,
    ) -> None:
        if max_artifact_bytes <= 0 or max_artifact_bytes > _DEFAULT_MAX_ARTIFACT_BYTES:
            raise ValueError(
                f"max_artifact_bytes must be between 1 and {_DEFAULT_MAX_ARTIFACT_BYTES}"
            )
        self.provider = provider
        self.max_artifact_bytes = max_artifact_bytes

    def acquire(
        self,
        request: CapsuleAcquisitionRequest,
        *,
        store_root: Path,
        receipt_root: Path | None = None,
    ) -> CapsuleAcquisitionReceipt:
        # Re-run request validation at the service boundary.
        request = CapsuleAcquisitionRequest(
            requirement=request.requirement,
            capsule=request.capsule,
            binding=request.binding,
            approved_binding_sha256=request.approved_binding_sha256,
        )

        root = store_root.expanduser().resolve()
        receipts = (receipt_root or (root / "receipts")).expanduser().resolve()
        digest = request.capsule.artifact_sha256
        destination = (root / "sha256" / digest[:2] / f"{digest}.oci").resolve()
        if root not in destination.parents:
            raise ValueError("capsule storage destination escaped the configured store root")
        if receipts == destination or destination in receipts.parents:
            raise ValueError("receipt root must not be inside an artifact file path")

        storage_state: str
        artifact_bytes: int

        if destination.exists():
            observed_sha256, artifact_bytes = _hash_file(
                destination, maximum=self.max_artifact_bytes
            )
            if observed_sha256 != digest:
                raise ValueError(
                    "existing capsule-store artifact does not match its digest path"
                )
            storage_state = "reused_verified"
        else:
            if self.provider is None:
                raise ValueError(
                    "capsule artifact is not already verified in the store and no provider is configured"
                )
            provided = self.provider.provide(request.capsule)
            if provided.source_ref != request.capsule.artifact_ref:
                raise ValueError(
                    "capsule provider source ref does not match the reviewed artifact ref"
                )
            source = provided.path.expanduser().resolve(strict=False)
            artifact_bytes = _copy_verified(
                source,
                destination,
                expected_sha256=digest,
                maximum=self.max_artifact_bytes,
            )
            storage_state = "created"

        receipt = CapsuleAcquisitionReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=request.requirement.app_id,
            commit_sha=request.requirement.commit_sha,
            plan_sha256=request.requirement.plan_sha256,
            requirement_sha256=request.requirement.sha256(),
            capsule_sha256=request.capsule.sha256(),
            binding_sha256=request.binding.sha256(),
            capsule_id=request.capsule.capsule_id,
            family=request.capsule.family,
            artifact_kind=request.capsule.artifact_kind,
            artifact_ref=request.capsule.artifact_ref,
            artifact_sha256=digest,
            artifact_bytes=artifact_bytes,
            storage_path=str(destination),
            storage_state=storage_state,
        )
        receipt_path = receipts / f"{receipt.receipt_id}.json"
        try:
            _write_receipt(receipt_path, receipt)
        except Exception:
            if storage_state == "created":
                try:
                    destination.unlink()
                except FileNotFoundError:
                    pass
            raise
        return receipt
