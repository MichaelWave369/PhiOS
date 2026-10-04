from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from phios.apps.toolchain_acquisition import (
    CapsuleAcquisitionReceipt,
    CapsuleAcquisitionRequest,
    CapsuleAcquisitionService,
    LocalCapsuleArtifactProvider,
    ProvidedCapsuleArtifact,
)
from phios.apps.toolchain_capsule import (
    ToolchainCapsule,
    ToolchainRequirement,
    ToolchainTool,
    bind_toolchain_capsule,
)


def _requirement() -> ToolchainRequirement:
    return ToolchainRequirement(
        app_id="phi.example",
        commit_sha="a" * 40,
        plan_sha256="b" * 64,
        strategy="node_package_manager",
        family="node_npm",
        required_tools=("node", "npm"),
        status="capsule_required",
    )


def _capsule(payload: bytes) -> ToolchainCapsule:
    digest = hashlib.sha256(payload).hexdigest()
    return ToolchainCapsule(
        capsule_id="phios.node-npm.test",
        family="node_npm",
        platform="linux_x86_64",
        artifact_kind="oci_image",
        artifact_ref=f"registry.example/phios/node-npm@sha256:{digest}",
        artifact_sha256=digest,
        tools=(
            ToolchainTool("node", "22.0.0"),
            ToolchainTool("npm", "10.0.0"),
        ),
    )


def _request(payload: bytes) -> CapsuleAcquisitionRequest:
    requirement = _requirement()
    capsule = _capsule(payload)
    binding = bind_toolchain_capsule(requirement, capsule)
    return CapsuleAcquisitionRequest(
        requirement=requirement,
        capsule=capsule,
        binding=binding,
        approved_binding_sha256=binding.sha256(),
    )


def test_request_requires_exact_binding_approval() -> None:
    request = _request(b"capsule")

    with pytest.raises(ValueError, match="approved binding"):
        CapsuleAcquisitionRequest(
            requirement=request.requirement,
            capsule=request.capsule,
            binding=request.binding,
            approved_binding_sha256="0" * 64,
        )


def test_request_rejects_binding_from_another_capsule() -> None:
    requirement = _requirement()
    first = _capsule(b"first")
    second = _capsule(b"second")
    second_binding = bind_toolchain_capsule(requirement, second)

    with pytest.raises(ValueError, match="does not match"):
        CapsuleAcquisitionRequest(
            requirement=requirement,
            capsule=first,
            binding=second_binding,
            approved_binding_sha256=second_binding.sha256(),
        )


def test_local_provider_creates_verified_digest_store_and_receipt(tmp_path: Path) -> None:
    payload = b"opaque-oci-capsule-bytes"
    request = _request(payload)
    source = tmp_path / "candidate.oci"
    source.write_bytes(payload)
    store = tmp_path / "store"
    receipts = tmp_path / "receipts"
    provider = LocalCapsuleArtifactProvider({request.capsule.artifact_ref: source})

    receipt = CapsuleAcquisitionService(provider=provider).acquire(
        request,
        store_root=store,
        receipt_root=receipts,
    )

    expected = (
        store.resolve()
        / "sha256"
        / request.capsule.artifact_sha256[:2]
        / f"{request.capsule.artifact_sha256}.oci"
    )
    assert Path(receipt.storage_path) == expected
    assert expected.read_bytes() == payload
    assert receipt.storage_state == "created"
    assert receipt.status == "verified_available"
    assert receipt.artifact_sha256 == request.capsule.artifact_sha256
    assert receipt.artifact_bytes == len(payload)
    assert receipt.requirement_sha256 == request.requirement.sha256()
    assert receipt.capsule_sha256 == request.capsule.sha256()
    assert receipt.binding_sha256 == request.binding.sha256()
    assert receipt.execution_authority is False
    assert receipt.network_authority is False
    assert receipt.install_authority is False
    assert receipt.host_write_authority is False
    assert list(receipts.glob("*.json"))


class _RefMismatchProvider:
    def __init__(self, path: Path) -> None:
        self.path = path

    def provide(self, capsule: ToolchainCapsule) -> ProvidedCapsuleArtifact:
        return ProvidedCapsuleArtifact(
            path=self.path,
            source_ref="registry.example/wrong",
        )


def test_provider_source_ref_must_match_reviewed_capsule(tmp_path: Path) -> None:
    payload = b"capsule"
    source = tmp_path / "candidate.oci"
    source.write_bytes(payload)

    with pytest.raises(ValueError, match="source ref"):
        CapsuleAcquisitionService(provider=_RefMismatchProvider(source)).acquire(
            _request(payload),
            store_root=tmp_path / "store",
        )


def test_digest_mismatch_leaves_no_verified_artifact(tmp_path: Path) -> None:
    reviewed = b"reviewed"
    request = _request(reviewed)
    source = tmp_path / "candidate.oci"
    source.write_bytes(b"different")
    store = tmp_path / "store"
    provider = LocalCapsuleArtifactProvider({request.capsule.artifact_ref: source})

    with pytest.raises(ValueError, match="SHA-256"):
        CapsuleAcquisitionService(provider=provider).acquire(
            request,
            store_root=store,
        )

    assert not list(store.glob("sha256/**/*.oci"))


def test_symlink_source_is_rejected(tmp_path: Path) -> None:
    payload = b"capsule"
    request = _request(payload)
    real = tmp_path / "real.oci"
    real.write_bytes(payload)
    link = tmp_path / "link.oci"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    provider = LocalCapsuleArtifactProvider({request.capsule.artifact_ref: link})

    with pytest.raises(ValueError, match="symlink"):
        CapsuleAcquisitionService(provider=provider).acquire(
            request,
            store_root=tmp_path / "store",
        )


class _NeverProvider:
    def provide(self, capsule: ToolchainCapsule) -> ProvidedCapsuleArtifact:
        raise AssertionError("provider must not be called for a verified existing CAS entry")


def test_existing_valid_store_entry_is_reverified_without_provider(tmp_path: Path) -> None:
    payload = b"capsule"
    request = _request(payload)
    digest = request.capsule.artifact_sha256
    destination = tmp_path / "store" / "sha256" / digest[:2] / f"{digest}.oci"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)

    receipt = CapsuleAcquisitionService(provider=_NeverProvider()).acquire(
        request,
        store_root=tmp_path / "store",
    )

    assert receipt.storage_state == "reused_verified"
    assert receipt.artifact_sha256 == digest


def test_corrupt_existing_store_entry_fails_closed(tmp_path: Path) -> None:
    payload = b"capsule"
    request = _request(payload)
    digest = request.capsule.artifact_sha256
    destination = tmp_path / "store" / "sha256" / digest[:2] / f"{digest}.oci"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="does not match"):
        CapsuleAcquisitionService().acquire(
            request,
            store_root=tmp_path / "store",
        )


def test_receipt_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    payload = b"capsule"
    request = _request(payload)
    source = tmp_path / "candidate.oci"
    source.write_bytes(payload)
    provider = LocalCapsuleArtifactProvider({request.capsule.artifact_ref: source})
    receipt = CapsuleAcquisitionService(provider=provider).acquire(
        request,
        store_root=tmp_path / "store",
    )

    data = receipt.to_dict()
    assert CapsuleAcquisitionReceipt.from_dict(data) == receipt

    data["storage_state"] = "reused_verified"
    with pytest.raises(ValueError, match="digest"):
        CapsuleAcquisitionReceipt.from_dict(data)


def test_receipt_rejects_authority_smuggling(tmp_path: Path) -> None:
    payload = b"capsule"
    request = _request(payload)
    source = tmp_path / "candidate.oci"
    source.write_bytes(payload)
    provider = LocalCapsuleArtifactProvider({request.capsule.artifact_ref: source})
    receipt = CapsuleAcquisitionService(provider=provider).acquire(
        request,
        store_root=tmp_path / "store",
    )

    data = receipt.to_dict()
    data["execution_authority"] = True
    with pytest.raises(ValueError, match="must remain false"):
        CapsuleAcquisitionReceipt.from_dict(data)


def test_missing_provider_is_rejected_when_store_has_no_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no provider"):
        CapsuleAcquisitionService().acquire(
            _request(b"capsule"),
            store_root=tmp_path / "store",
        )
