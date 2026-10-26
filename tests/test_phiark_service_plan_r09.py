"""PhiARK R0.9 synthetic installed-tree command tests. No launch or network."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from phios.apps.manifest import AppManifest
from phios.apps.package_install import AppInstallReceipt, snapshot_installed_tree
from phios.apps.phiark_service_plan import command_preview, inspect_phiark_service

COMMIT = "d0c01e7200d07ae4c5448375878e5188048a6a40"


def _installed(
    root: Path, *, permissions: tuple[str, ...] = ("runtime.data.persist",),
    source: str = "https://github.com/MichaelWave369/PhiARK",
) -> tuple[dict, Path, Path, Path]:
    manifest = AppManifest.from_dict({
        "schema_version": "phios.app_manifest.v0.1",
        "app_id": "phi.phiark",
        "name": "PhiARK Knowledge Vault",
        "version": "0.5.0",
        "description": "Synthetic runtime test fixture, not real PhiARK source.",
        "source": {
            "repository_url": source,
            "license_expression": "MIT",
            "redistribution": "unknown",
        },
        "entrypoint": {"runtime": "node", "target": "src/server.mjs"},
        "permissions": list(permissions),
    })
    install_root = root / "installed"
    install_path = install_root / "phi.phiark" / "0.5.0" / "digest"
    payload = install_path / "payload"
    (payload / "src").mkdir(parents=True)
    (payload / "src" / "server.mjs").write_text("console.log('synthetic only')\n")
    metadata = install_path / ".phios"
    metadata.mkdir()
    (metadata / "manifest.json").write_text(json.dumps(manifest.to_dict()))
    (metadata / "package-plan.json").write_text('{"fixture":true}')
    payload_sha, count, byte_count = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-10-25T20:00:00+00:00",
        app_id="phi.phiark",
        app_version="0.5.0",
        package_plan_sha256="1" * 64,
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="2" * 64,
        build_plan_sha256="3" * 64,
        execution_receipt_sha256="4" * 64,
        offline_build_receipt_sha256="5" * 64,
        artifact_set_sha256=payload_sha,
        installed_payload_sha256=payload_sha,
        installed_tree_sha256=tree_sha,
        artifact_count=count,
        total_bytes=byte_count,
        install_path=str(install_path.resolve()),
        launch_authority=False,
        status="installed",
    )
    data = root / "private-vault"
    data.mkdir(mode=0o700)
    data.chmod(0o700)
    return receipt.to_dict(), install_root, data, install_path


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-mode contract")
def test_service_plan_rechecks_real_installed_bytes_but_claims_no_launch(tmp_path: Path) -> None:
    receipt, installed, data, install_path = _installed(tmp_path)
    plan = inspect_phiark_service(
        receipt, install_root=installed, data_directory=data, source_commit_candidate=COMMIT,
    )
    status = plan.to_dict()
    assert status["status"] == "HELD_FOR_OPERATOR_REVIEW"
    assert status["source_commit_candidate"] == COMMIT
    assert status["source_commit_attested_to_installed_tree"] is False
    assert status["installed_tree_sha256"] == receipt["installed_tree_sha256"]
    assert status["network_mode"] == "deny"
    assert status["guest_environment"] == {
        "PHIARK_DATA_DIR": "/phios/app-data",
        "PHIARK_SOCKET_PATH": "/phios/app-data/.phiark.sock",
    }
    assert status["service_supervised"] is False
    assert not any(status[key] for key in ("install_authority", "launch_authority", "gateway_authority"))
    assert not (data / ".phiark.sock").exists()
    # Same-size modification changes the installed-tree receipt and must fail closed.
    (install_path / "payload" / "src" / "server.mjs").write_text("console.log('modified fixture')\n")
    with pytest.raises(ValueError, match="installed tree changed"):
        inspect_phiark_service(
            receipt, install_root=installed, data_directory=data, source_commit_candidate=COMMIT,
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-mode contract")
def test_command_preview_denies_network_and_binds_executable_read_only(tmp_path: Path) -> None:
    receipt, installed, data, _ = _installed(tmp_path)
    plan = inspect_phiark_service(
        receipt, install_root=installed, data_directory=data, source_commit_candidate=COMMIT,
    )
    command = command_preview(
        receipt, install_root=installed, data_directory=data, source_commit_candidate=COMMIT,
        reviewed_preview_sha256=plan.to_dict()["preview_sha256"],
        node_binary=Path("/usr/bin/node"),
        bwrap_binary=Path("/usr/bin/bwrap"),
        prlimit_binary=Path("/usr/bin/prlimit"),
    )
    assert command[0] == "/usr/bin/bwrap"
    assert "--unshare-net" in command
    assert "--clearenv" in command
    assert "--die-with-parent" in command
    assert "--ro-bind" in command
    assert command[-3:] == ("--", str(Path("/usr/bin/node").resolve()), "/app/src/server.mjs")
    assert command.count("--bind") == 1
    assert command[command.index("--bind") + 1:command.index("--bind") + 3] == (
        str(data), "/phios/app-data",
    )
    for name, value in {
        "PHIARK_DATA_DIR": "/phios/app-data",
        "PHIARK_SOCKET_PATH": "/phios/app-data/.phiark.sock",
    }.items():
        assert ("--setenv", name, value) in [
            command[i:i + 3] for i in range(len(command) - 2)
        ]
    for prohibited in ("PHIARK_HOST", "PHIARK_PORT", "PHIARK_ALLOW_LAN", "--share-net"):
        assert prohibited not in command
    with pytest.raises(ValueError, match="operator review"):
        command_preview(
            receipt, install_root=installed, data_directory=data, source_commit_candidate=COMMIT,
            reviewed_preview_sha256="0" * 64,
            node_binary=Path("/usr/bin/node"),
            bwrap_binary=Path("/usr/bin/bwrap"),
            prlimit_binary=Path("/usr/bin/prlimit"),
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-mode contract")
def test_service_preview_blocks_broad_network_and_wrong_source(tmp_path: Path) -> None:
    for index, case in enumerate(("network", "source", "unknown")):
        root = tmp_path / str(index)
        root.mkdir()
        if case == "network":
            receipt, installed, data, _ = _installed(
                root, permissions=("runtime.data.persist", "runtime.network.inherit"),
            )
        elif case == "source":
            receipt, installed, data, _ = _installed(
                root, source="https://github.com/attacker/PhiARK",
            )
        else:
            receipt, installed, data, _ = _installed(root, permissions=())
        with pytest.raises(ValueError, match="unsupported runtime or authority"):
            inspect_phiark_service(
                receipt, install_root=installed, data_directory=data, source_commit_candidate=COMMIT,
            )


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-mode contract")
def test_service_preview_blocks_unprivate_or_replaced_data_roots(tmp_path: Path) -> None:
    receipt, installed, data, _ = _installed(tmp_path)
    expected = dict(install_root=installed, source_commit_candidate=COMMIT)
    data.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        inspect_phiark_service(receipt, data_directory=data, **expected)
    data.chmod(0o700)
    alias = tmp_path / "redirected-vault"
    alias.symlink_to(data, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        inspect_phiark_service(receipt, data_directory=alias, **expected)
    (data / ".phiark.sock").write_text("occupied")
    with pytest.raises(ValueError, match="already exists"):
        inspect_phiark_service(receipt, data_directory=data, **expected)
    (data / ".phiark.sock").unlink()
    symlinked_parent = tmp_path / "alias-parent"
    symlinked_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        inspect_phiark_service(receipt, data_directory=symlinked_parent / data.name, **expected)
    with pytest.raises(ValueError, match="40-character SHA"):
        inspect_phiark_service(receipt, data_directory=data, install_root=installed,
                               source_commit_candidate="abc")


@pytest.mark.skipif(os.name != "posix", reason="POSIX local provenance check")
def test_r10_package_lineage_tracks_an_exact_local_commit_claim(tmp_path: Path) -> None:
    from dataclasses import replace
    import hashlib

    from phios.apps.package_install import BuildPackagePlan, PackageArtifact
    from phios.apps.phiark_source_lineage import review_phiark_source_lineage

    receipt_data, root, data, installed_path = _installed(tmp_path)
    receipt = AppInstallReceipt.from_dict(receipt_data)
    content = (installed_path / "payload" / "src" / "server.mjs").read_bytes()
    artifact = PackageArtifact(
        path="src/server.mjs", byte_count=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    artifacts_sha = hashlib.sha256(artifact.canonical_line()).hexdigest()
    plan = BuildPackagePlan(
        app_id="phi.phiark", app_version="0.5.0",
        manifest_sha256=receipt.manifest_sha256,
        registry_snapshot_sha256=receipt.registry_snapshot_sha256,
        repository_url="https://github.com/MichaelWave369/PhiARK",
        commit_sha=COMMIT,
        build_plan_sha256=receipt.build_plan_sha256,
        execution_receipt_sha256=receipt.execution_receipt_sha256,
        offline_build_receipt_sha256=receipt.offline_build_receipt_sha256,
        artifact_set_sha256=artifacts_sha, artifacts=(artifact,),
        install_relative_path="phi.phiark/0.5.0/digest",
    )
    metadata_file = installed_path / ".phios" / "package-plan.json"
    metadata_file.write_text(json.dumps(plan.to_dict()))
    new_tree_sha, _, _ = snapshot_installed_tree(installed_path)
    receipt = replace(
        receipt, package_plan_sha256=plan.sha256(),
        artifact_set_sha256=artifacts_sha,
        installed_tree_sha256=new_tree_sha,
    )
    report = review_phiark_source_lineage(
        receipt.to_dict(), install_root=root, data_directory=data, expected_commit=COMMIT,
    )
    assert report["status"] == "HELD_FOR_SOURCE_ATTESTATION"
    assert report["source_commit_claim"] == COMMIT
    assert report["local_package_lineage_consistent"] is True
    assert report["source_archive_attested"] is False
    assert report["build_source_lineage_independently_verified"] is False
    assert report["launch_authority"] is False
    assert not (data / ".phiark.sock").exists()

    # Metadata can be self-consistent but cannot assert a different approved
    # commit without a mismatch. This is a claim check, not public GitHub proof.
    with pytest.raises(ValueError, match="commit"):
        review_phiark_source_lineage(
            receipt.to_dict(), install_root=root, data_directory=data, expected_commit="f" * 40,
        )

    # Even valid JSON with substituted bytes cannot match an installed receipt.
    metadata_file.write_text(json.dumps({**plan.to_dict(), "commit_sha": "f" * 40}))
    with pytest.raises(ValueError, match="installed tree changed"):
        review_phiark_source_lineage(
            receipt.to_dict(), install_root=root, data_directory=data, expected_commit=COMMIT,
        )
    metadata_file.unlink()
    metadata_file.symlink_to(installed_path / ".phios" / "manifest.json")
    # Snapshot rejects symlinks explicitly before reaching its tree-hash check.
    # Both paths must fail closed; expect the more precise security rejection.
    with pytest.raises(ValueError, match="installed payload contains a symlink"):
        review_phiark_source_lineage(
            receipt.to_dict(), install_root=root, data_directory=data, expected_commit=COMMIT,
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX local provenance check")
def test_r10_missing_package_plan_is_blocked_even_when_app_receipt_claims_installed(tmp_path: Path) -> None:
    from phios.apps.phiark_source_lineage import review_phiark_source_lineage

    receipt, root, data, installed_path = _installed(tmp_path)
    (installed_path / ".phios" / "package-plan.json").unlink()
    with pytest.raises(ValueError, match="installed tree changed"):
        review_phiark_source_lineage(
            receipt, install_root=root, data_directory=data, expected_commit=COMMIT,
        )



def _r11_chain_fixture(tmp_path: Path):
    """Self-consistent synthetic archive/build/install records, never real source."""
    from dataclasses import replace
    import io
    import zipfile

    from phios.apps.build_execution import BuildArtifact, BuildExecutionReceipt
    from phios.apps.npm_offline import NpmOfflineBuildReceipt
    from phios.apps.package_install import BuildPackagePlan, PackageArtifact
    from phios.apps.phiark_archive_chain import verify_archive_bytes

    receipt_data, root, data, install = _installed(tmp_path)
    receipt = AppInstallReceipt.from_dict(receipt_data)
    source = (install / "payload" / "src" / "server.mjs").read_bytes()
    wire = io.BytesIO()
    with zipfile.ZipFile(wire, "w") as zf:
        zf.writestr("PhiARK-" + COMMIT + "/", b"")
        zf.writestr("PhiARK-" + COMMIT + "/src/server.mjs", source)
    archive = wire.getvalue()
    inspection = verify_archive_bytes(archive)
    artifact = BuildArtifact(
        path="src/server.mjs", byte_count=len(source),
        sha256=hashlib.sha256(source).hexdigest(),
    )
    artifact_digest = hashlib.sha256(artifact.canonical_line()).hexdigest()
    acquired_path = tmp_path / "acquired" / COMMIT
    acquired_path.mkdir(parents=True)
    acquisition = {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": str(uuid.uuid4()),
        "timestamp_utc": "2026-10-25T20:00:00+00:00",
        "app_id": "phi.phiark",
        "repository_url": "https://github.com/MichaelWave369/PhiARK",
        "commit_sha": COMMIT,
        "manifest_sha256": receipt.manifest_sha256,
        "archive_sha256": inspection["archive_sha256"],
        "tree_sha256": inspection["acquisition_tree_sha256"],
        "file_count": inspection["file_count"],
        "total_bytes": inspection["total_bytes"],
        "workspace_path": str(acquired_path),
        "status": "acquired",
    }
    execution = BuildExecutionReceipt(
        execution_id=str(uuid.uuid4()),
        timestamp_utc="2026-10-25T20:01:00+00:00",
        app_id="phi.phiark",
        repository_url="https://github.com/MichaelWave369/PhiARK",
        commit_sha=COMMIT,
        plan_sha256=receipt.build_plan_sha256,
        source_snapshot_sha256=inspection["source_snapshot_sha256"],
        acquisition_tree_sha256=inspection["acquisition_tree_sha256"],
        approved_permissions=("build.process.execute", "build.workspace.write"),
        isolation_mode="bubblewrap_linux_namespaces",
        network_sandbox_enforced=True,
        source_workspace_path=str(acquired_path),
        execution_workspace_path=str(tmp_path / "build"),
        tool_identities=(),
        steps=(),
        artifacts=(artifact,),
        artifact_set_sha256=artifact_digest,
        status="success",
        failure_reason=None,
    )
    offline = NpmOfflineBuildReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-10-25T20:02:00+00:00",
        app_id="phi.phiark",
        commit_sha=COMMIT,
        npm_offline_plan_sha256="a" * 64,
        original_build_plan_sha256="b" * 64,
        derived_build_plan_sha256=receipt.build_plan_sha256,
        npm_cache_receipt_sha256="c" * 64,
        cache_tree_sha256="d" * 64,
        cache_mount_target="/phios/npm-cache",
        build_execution_receipt_sha256=execution.sha256(),
        sandbox_receipt_sha256="e" * 64,
        network_mode="deny",
        network_namespace_enforced=True,
        build_status="success",
    )
    package_artifact = PackageArtifact(
        path=artifact.path, byte_count=artifact.byte_count, sha256=artifact.sha256
    )
    package = BuildPackagePlan(
        app_id="phi.phiark", app_version="0.5.0",
        manifest_sha256=receipt.manifest_sha256,
        registry_snapshot_sha256=receipt.registry_snapshot_sha256,
        repository_url="https://github.com/MichaelWave369/PhiARK",
        commit_sha=COMMIT,
        build_plan_sha256=receipt.build_plan_sha256,
        execution_receipt_sha256=execution.sha256(),
        offline_build_receipt_sha256=offline.sha256(),
        artifact_set_sha256=artifact_digest,
        artifacts=(package_artifact,),
        install_relative_path="phi.phiark/0.5.0/digest",
    )
    (install / ".phios" / "package-plan.json").write_text(
        json.dumps(package.to_dict()), encoding="utf-8"
    )
    tree_sha, _, _ = snapshot_installed_tree(install)
    receipt = replace(
        receipt,
        package_plan_sha256=package.sha256(),
        execution_receipt_sha256=execution.sha256(),
        offline_build_receipt_sha256=offline.sha256(),
        artifact_set_sha256=artifact_digest,
        installed_tree_sha256=tree_sha,
    )
    return receipt.to_dict(), acquisition, execution.to_dict(), offline.to_dict(), archive, root, data


@pytest.mark.skipif(os.name != "posix", reason="POSIX local installed-tree proof")
def test_r11_archive_bytes_match_acquisition_build_and_install_receipts(tmp_path: Path) -> None:
    from phios.apps.phiark_archive_chain import review_phiark_archive_chain

    receipt, acquisition, execution, offline, archive, root, data = _r11_chain_fixture(tmp_path)
    report = review_phiark_archive_chain(
        receipt, acquisition, execution, offline, archive,
        install_root=root, data_directory=data, expected_commit=COMMIT,
    )
    assert report["status"] == "ARCHIVE_BYTES_MATCHED_LOCAL_RECEIPTS"
    assert report["source_archive_bytes_matched_local_receipt"] is True
    assert report["acquisition_build_install_crosschecked"] is True
    assert report["source_authenticated_against_github"] is False
    assert report["launch_authority"] is False
    assert not (data / ".phiark.sock").exists()

    with pytest.raises(ValueError, match="acquired ZIP hash"):
        review_phiark_archive_chain(
            receipt, acquisition, execution, offline, archive + b"changed",
            install_root=root, data_directory=data, expected_commit=COMMIT,
        )
    altered = dict(acquisition, commit_sha="f" * 40)
    with pytest.raises(ValueError, match="acquisition identity"):
        review_phiark_archive_chain(
            receipt, altered, execution, offline, archive,
            install_root=root, data_directory=data, expected_commit=COMMIT,
        )
    corrupt = dict(execution, source_snapshot_sha256="0" * 64)
    with pytest.raises(ValueError):
        review_phiark_archive_chain(
            receipt, acquisition, corrupt, offline, archive,
            install_root=root, data_directory=data, expected_commit=COMMIT,
        )


def test_r11_archive_refuses_duplicate_traversal_and_symlink_members() -> None:
    import io
    import stat
    import zipfile

    from phios.apps.phiark_archive_chain import verify_archive_bytes

    def zip_of(*members):
        wire = io.BytesIO()
        with zipfile.ZipFile(wire, "w") as archive:
            for item in members:
                if isinstance(item, tuple):
                    archive.writestr(item[0], item[1])
                else:
                    archive.writestr(item, b"good")
        return wire.getvalue()

    with pytest.raises(ValueError, match="duplicate"):
        verify_archive_bytes(zip_of(("root/file.txt", b"x"), ("root/file.txt", b"y")))
    with pytest.raises(ValueError, match="unsafe"):
        verify_archive_bytes(zip_of(("root/../out.txt", b"x")))
    symlink = zipfile.ZipInfo("root/shortcut")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="symlink"):
        verify_archive_bytes(zip_of((symlink, b"outside")))
