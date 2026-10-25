"""PhiARK R0.9 synthetic installed-tree command tests. No launch or network."""
from __future__ import annotations

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
    assert command[-3:] == ("--", "/usr/bin/node", "/app/src/server.mjs")
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
    with pytest.raises(ValueError, match="40-character SHA"):
        inspect_phiark_service(receipt, data_directory=data, install_root=installed,
                               source_commit_candidate="abc")
