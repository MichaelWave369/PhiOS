from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from phios.apps.build_execution import (
    BuildArtifact,
    BuildExecutionReceipt,
)
from phios.apps.manifest import AppManifest
from phios.apps.npm_offline import NpmOfflineBuildReceipt
from phios.apps.package_install import (
    AppInstallReceipt,
    AppInstallService,
    AppUninstallService,
    BuildPackagePlan,
    plan_build_package,
    review_build_package,
)
from phios.apps.registry import AppRegistry


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.example",
            "name": "Example",
            "version": "1.2.3",
            "description": "Example app",
            "source": {
                "repository_url": "https://github.com/example/example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _artifact_set(artifacts: tuple[BuildArtifact, ...]) -> str:
    digest = hashlib.sha256()
    for artifact in artifacts:
        digest.update(artifact.canonical_line())
    return digest.hexdigest()


def _receipts(tmp_path: Path) -> tuple[dict, dict, Path]:
    workspace = tmp_path / "execution" / "source"
    dist = workspace / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html>phi</html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('phi')", encoding="utf-8")

    artifacts = (
        BuildArtifact(
            path="dist/assets/app.js",
            byte_count=(assets / "app.js").stat().st_size,
            sha256=hashlib.sha256((assets / "app.js").read_bytes()).hexdigest(),
        ),
        BuildArtifact(
            path="dist/index.html",
            byte_count=(dist / "index.html").stat().st_size,
            sha256=hashlib.sha256((dist / "index.html").read_bytes()).hexdigest(),
        ),
    )
    execution = BuildExecutionReceipt(
        execution_id="11111111-1111-1111-1111-111111111111",
        timestamp_utc="2026-09-19T04:00:00+00:00",
        app_id="phi.example",
        repository_url="https://github.com/example/example",
        commit_sha="a" * 40,
        plan_sha256="b" * 64,
        source_snapshot_sha256="c" * 64,
        acquisition_tree_sha256="d" * 64,
        approved_permissions=("build.process.execute", "build.workspace.write"),
        isolation_mode="bubblewrap_linux_namespaces",
        network_sandbox_enforced=True,
        source_workspace_path=str((tmp_path / "source").resolve()),
        execution_workspace_path=str(workspace.resolve()),
        tool_identities=(),
        steps=(),
        artifacts=artifacts,
        artifact_set_sha256=_artifact_set(artifacts),
        status="success",
        failure_reason=None,
    )
    offline = NpmOfflineBuildReceipt(
        receipt_id="22222222-2222-2222-2222-222222222222",
        timestamp_utc="2026-09-19T04:01:00+00:00",
        app_id="phi.example",
        commit_sha="a" * 40,
        npm_offline_plan_sha256="e" * 64,
        original_build_plan_sha256="f" * 64,
        derived_build_plan_sha256="b" * 64,
        npm_cache_receipt_sha256="1" * 64,
        cache_tree_sha256="2" * 64,
        cache_mount_target="/phios/npm-cache",
        build_execution_receipt_sha256=execution.sha256(),
        sandbox_receipt_sha256="3" * 64,
        network_mode="deny",
        network_namespace_enforced=True,
        build_status="success",
    )
    return execution.to_dict(), offline.to_dict(), workspace


def _registry(tmp_path: Path) -> tuple[AppManifest, AppRegistry, Path]:
    manifest = _manifest()
    registry = AppRegistry()
    registry.register(manifest)
    path = tmp_path / "registry.json"
    registry.save(path)
    return manifest, registry, path


def test_registry_snapshot_digest_is_deterministic(tmp_path: Path) -> None:
    manifest, registry, path = _registry(tmp_path)
    loaded = AppRegistry.load(path)

    assert loaded.get(manifest.app_id).sha256() == manifest.sha256()
    assert loaded.snapshot_sha256() == registry.snapshot_sha256()


def test_package_plan_binds_registry_and_successful_artifacts(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)

    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    review = review_build_package(plan.to_dict())

    assert plan.app_id == manifest.app_id
    assert plan.app_version == "1.2.3"
    assert plan.launch_authority is False
    assert plan.registry_snapshot_sha256 == registry.snapshot_sha256()
    assert plan.artifact_set_sha256 == execution["artifact_set_sha256"]
    assert review.package_plan_sha256 == plan.sha256()
    assert review.launch_authority is False
    assert BuildPackagePlan.from_dict(plan.to_dict()) == plan


def test_package_plan_rejects_failed_or_unsandboxed_build(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)

    execution["network_sandbox_enforced"] = False
    body = dict(execution)
    body.pop("receipt_sha256")
    execution["receipt_sha256"] = hashlib.sha256(
        __import__("json").dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    with pytest.raises(ValueError, match="network-sandboxed"):
        plan_build_package(manifest.to_dict(), registry, execution, offline)


def test_package_plan_rejects_offline_receipt_from_different_execution(
    tmp_path: Path,
) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    offline["build_execution_receipt_sha256"] = "9" * 64
    body = dict(offline)
    body.pop("npm_offline_build_receipt_sha256")
    offline["npm_offline_build_receipt_sha256"] = hashlib.sha256(
        __import__("json").dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    with pytest.raises(ValueError, match="does not bind"):
        plan_build_package(manifest.to_dict(), registry, execution, offline)


def test_install_copies_only_receipted_artifacts_atomically(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, workspace = _receipts(tmp_path)
    (workspace / "secret-source.txt").write_text("do not install", encoding="utf-8")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "junk.js").write_text("junk", encoding="utf-8")

    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    receipt = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution,
        offline,
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )

    install = Path(receipt.install_path)
    assert receipt.status == "installed"
    assert receipt.launch_authority is False
    assert (install / "payload" / "dist" / "index.html").is_file()
    assert (install / "payload" / "dist" / "assets" / "app.js").is_file()
    assert not (install / "payload" / "secret-source.txt").exists()
    assert not (install / "payload" / "node_modules").exists()
    assert (install / ".phios" / "package-plan.json").is_file()
    assert (install / ".phios" / "manifest.json").is_file()
    assert AppInstallReceipt.from_dict(receipt.to_dict()) == receipt


def test_install_rejects_artifact_tampering_after_build(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, workspace = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    (workspace / "dist" / "index.html").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="changed"):
        AppInstallService().install(
            plan.to_dict(),
            registry,
            execution,
            offline,
            approved_package_plan_sha256=plan.sha256(),
            install_root=tmp_path / "apps",
        )


def test_install_requires_exact_package_plan_approval(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)

    with pytest.raises(ValueError, match="Approved package-plan"):
        AppInstallService().install(
            plan.to_dict(),
            registry,
            execution,
            offline,
            approved_package_plan_sha256="0" * 64,
            install_root=tmp_path / "apps",
        )


def test_install_fails_if_registry_changes_after_review(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)

    registry.register(
        AppManifest.from_dict(
            {
                "schema_version": "phios.app_manifest.v0.1",
                "app_id": "phi.other",
                "name": "Other",
                "version": "1.0.0",
                "description": "Other",
                "source": {
                    "repository_url": "https://github.com/example/other",
                    "license_expression": "MIT",
                    "redistribution": "permitted",
                },
                "entrypoint": {"runtime": "static_web", "target": "index.html"},
                "permissions": [],
            }
        )
    )

    with pytest.raises(ValueError, match="registry changed"):
        AppInstallService().install(
            plan.to_dict(),
            registry,
            execution,
            offline,
            approved_package_plan_sha256=plan.sha256(),
            install_root=tmp_path / "apps",
        )


def test_existing_install_is_never_overwritten(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    service = AppInstallService()

    service.install(
        plan.to_dict(),
        registry,
        execution,
        offline,
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )

    with pytest.raises(ValueError, match="already exists"):
        service.install(
            plan.to_dict(),
            registry,
            execution,
            offline,
            approved_package_plan_sha256=plan.sha256(),
            install_root=tmp_path / "apps",
        )


def test_uninstall_requires_exact_receipt_and_unchanged_payload(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    install = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution,
        offline,
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )

    with pytest.raises(ValueError, match="Approved install-receipt"):
        AppUninstallService().uninstall(
            install.to_dict(),
            approved_install_receipt_sha256="0" * 64,
            install_root=tmp_path / "apps",
        )

    target = Path(install.install_path)
    (target / "payload" / "dist" / "index.html").write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since install"):
        AppUninstallService().uninstall(
            install.to_dict(),
            approved_install_receipt_sha256=install.sha256(),
            install_root=tmp_path / "apps",
        )


def test_uninstall_removes_only_receipted_install(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    install = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution,
        offline,
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )
    neighbor = tmp_path / "apps" / "neighbor"
    neighbor.mkdir(parents=True)
    (neighbor / "keep.txt").write_text("keep", encoding="utf-8")

    uninstall = AppUninstallService().uninstall(
        install.to_dict(),
        approved_install_receipt_sha256=install.sha256(),
        install_root=tmp_path / "apps",
    )

    assert uninstall.status == "uninstalled"
    assert not Path(install.install_path).exists()
    assert (neighbor / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_uninstall_rejects_metadata_or_extra_file_drift(tmp_path: Path) -> None:
    manifest, registry, _ = _registry(tmp_path)
    execution, offline, _ = _receipts(tmp_path)
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    install = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution,
        offline,
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )

    target = Path(install.install_path)
    (target / ".phios" / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="installed tree changed"):
        AppUninstallService().uninstall(
            install.to_dict(),
            approved_install_receipt_sha256=install.sha256(),
            install_root=tmp_path / "apps",
        )
