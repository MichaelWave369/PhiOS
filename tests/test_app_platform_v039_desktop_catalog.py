from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from phios.apps.browser_session import plan_browser_session
from phios.apps.desktop_catalog import (
    DesktopCatalogItem,
    DesktopCatalogReceipt,
    DesktopCatalogService,
    DesktopCatalogSnapshot,
    review_desktop_catalog,
    snapshot_desktop_catalog,
)
from phios.apps.desktop_launch import (
    DesktopAppInstaller,
    DesktopAppRegistrationRequest,
)
from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    AppInstallReceipt,
    BuildPackagePlan,
    PackageArtifact,
    snapshot_installed_tree,
)
from phios.apps.static_web import plan_static_web_adapter
from phios.apps.desktop_launch import plan_desktop_app


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.catalog-example",
            "name": "Catalog Example",
            "version": "1.0.0",
            "description": "Catalog fixture",
            "source": {
                "repository_url": "https://github.com/example/catalog-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _registered_app(tmp_path: Path):
    manifest = _manifest()
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    dist = payload / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    metadata.mkdir()
    (dist / "index.html").write_text(
        "<html><body>catalog</body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('catalog')", encoding="utf-8")

    artifacts: list[PackageArtifact] = []
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            artifacts.append(
                PackageArtifact(
                    path=path.relative_to(payload).as_posix(),
                    byte_count=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    artifact_tuple = tuple(artifacts)
    artifact_digest = hashlib.sha256()
    for artifact in artifact_tuple:
        artifact_digest.update(artifact.canonical_line())

    package_plan = BuildPackagePlan(
        app_id=manifest.app_id,
        app_version=manifest.version,
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="1" * 64,
        repository_url=manifest.source.repository_url,
        commit_sha="a" * 40,
        build_plan_sha256="2" * 64,
        execution_receipt_sha256="3" * 64,
        offline_build_receipt_sha256="4" * 64,
        artifact_set_sha256=artifact_digest.hexdigest(),
        artifacts=artifact_tuple,
        install_relative_path=f"{manifest.app_id}/{manifest.version}/artifactprefix",
        launch_authority=False,
    )
    (metadata / "package-plan.json").write_text(
        json.dumps(package_plan.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    (metadata / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    payload_sha, artifact_count, total_bytes = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    install_receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T08:00:00+00:00",
        app_id=manifest.app_id,
        app_version=manifest.version,
        package_plan_sha256=package_plan.sha256(),
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="1" * 64,
        build_plan_sha256="2" * 64,
        execution_receipt_sha256="3" * 64,
        offline_build_receipt_sha256="4" * 64,
        artifact_set_sha256=payload_sha,
        installed_payload_sha256=payload_sha,
        installed_tree_sha256=tree_sha,
        artifact_count=artifact_count,
        total_bytes=total_bytes,
        install_path=str(install_path.resolve()),
        launch_authority=False,
        status="installed",
    )

    static_plan = plan_static_web_adapter(
        install_receipt.to_dict(),
        install_root=install_root,
        loopback_port=9401,
        serve_seconds=120,
    )
    browser_plan = plan_browser_session(
        static_plan.to_dict(),
        browser_tool="chromium",
        session_seconds=30,
        readiness_timeout_ms=2500,
    )
    desktop_plan = plan_desktop_app(
        browser_plan.to_dict(),
        static_plan.to_dict(),
        install_receipt.to_dict(),
        install_root=install_root,
    )
    request = DesktopAppRegistrationRequest.from_payloads(
        desktop_plan.to_dict(),
        browser_plan.to_dict(),
        static_plan.to_dict(),
        install_receipt.to_dict(),
        approved_desktop_app_plan_sha256=desktop_plan.sha256(),
        approved_desktop_permissions=desktop_plan.requested_desktop_permissions,
    )
    desktop_root = tmp_path / "desktop-apps"
    applications_root = tmp_path / "applications"
    installed = DesktopAppInstaller().install(
        request,
        install_root=install_root,
        desktop_root=desktop_root,
        applications_root=applications_root,
    )
    return {
        "manifest": manifest,
        "install_root": install_root,
        "install_path": install_path,
        "desktop_root": desktop_root,
        "applications_root": applications_root,
        "installed": installed,
        "desktop_plan": desktop_plan,
    }


def test_empty_missing_catalog_root_is_deterministic_and_non_authoritative(
    tmp_path: Path,
) -> None:
    first = snapshot_desktop_catalog(
        desktop_root=tmp_path / "missing-desktop",
        applications_root=tmp_path / "missing-applications",
        install_root=tmp_path / "missing-installed",
    )
    second = snapshot_desktop_catalog(
        desktop_root=tmp_path / "missing-desktop",
        applications_root=tmp_path / "missing-applications",
        install_root=tmp_path / "missing-installed",
    )

    assert first.item_count == 0
    assert first.ready_count == 0
    assert first.blocked_count == 0
    assert first.root_issues == ()
    assert first.catalog_launch_authority is False
    assert first.catalog_revoke_authority is False
    assert first.sha256() == second.sha256()
    assert DesktopCatalogSnapshot.from_dict(first.to_dict()) == first


def test_valid_governed_desktop_app_is_ready(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.item_count == 1
    assert snapshot.ready_count == 1
    assert snapshot.blocked_count == 0
    item = snapshot.items[0]
    assert item.status == "ready"
    assert item.app_id == "phi.catalog-example"
    assert item.app_version == "1.0.0"
    assert item.desktop_name == "Catalog Example"
    assert item.desktop_icon == "phios-app"
    assert item.icon_asset_state == "metadata_only"
    assert item.identity_verified is True
    assert item.persistent_launch_grant_present is True
    assert item.grant_status == "enabled"
    assert item.issues == ()
    assert item.catalog_launch_authority is False
    assert item.catalog_revoke_authority is False
    assert DesktopCatalogItem.from_dict(item.to_dict()) == item


def test_repeated_catalog_snapshot_has_stable_digest_but_receipts_are_observations(
    tmp_path: Path,
) -> None:
    app = _registered_app(tmp_path)
    service = DesktopCatalogService()

    first = service.snapshot(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )
    second = service.snapshot(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert first.snapshot.sha256() == second.snapshot.sha256()
    assert first.receipt.desktop_catalog_sha256 == first.snapshot.sha256()
    assert first.receipt.sha256() != second.receipt.sha256()
    assert first.receipt.launch_authority is False
    assert first.receipt.revoke_authority is False
    assert DesktopCatalogReceipt.from_dict(first.receipt.to_dict()) == first.receipt


def test_review_exposes_summary_without_action_authority(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    review = review_desktop_catalog(snapshot.to_dict())

    assert review.desktop_catalog_sha256 == snapshot.sha256()
    assert review.ready_count == 1
    assert review.blocked_count == 0
    assert review.ready_app_ids == ("phi.catalog-example",)
    assert review.catalog_launch_authority is False
    assert review.catalog_revoke_authority is False


def test_launcher_entry_tamper_blocks_catalog_item(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    entry = Path(app["installed"].desktop_entry_path)
    entry.write_text(
        entry.read_text(encoding="utf-8") + "# changed\n",
        encoding="utf-8",
    )

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.ready_count == 0
    assert snapshot.blocked_count == 1
    assert tuple(issue.code for issue in snapshot.items[0].issues) == (
        "desktop_entry_digest_mismatch",
    )


def test_installed_app_drift_blocks_catalog_item(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    (app["install_path"] / "payload" / "dist" / "index.html").write_text(
        "changed",
        encoding="utf-8",
    )

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.items[0].status == "blocked"
    assert "installed_app_drift" in {
        issue.code for issue in snapshot.items[0].issues
    }


def test_malformed_grant_is_blocked_without_breaking_whole_catalog(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    grant_path = Path(app["installed"].bundle_path) / "grant.json"
    grant_path.write_text("{not json", encoding="utf-8")

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.item_count == 1
    assert snapshot.items[0].status == "blocked"
    assert tuple(issue.code for issue in snapshot.items[0].issues) == ("grant_invalid",)


def test_extra_bundle_file_causes_layout_block(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    (Path(app["installed"].bundle_path) / "unexpected.txt").write_text(
        "nope",
        encoding="utf-8",
    )

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert tuple(issue.code for issue in snapshot.items[0].issues) == (
        "bundle_layout_invalid",
    )


def test_missing_applications_root_blocks_launcher_evidence(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    shutil.rmtree(app["applications_root"])

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.items[0].status == "blocked"
    assert "desktop_entry_missing" in {
        issue.code for issue in snapshot.items[0].issues
    }


def test_unexpected_files_are_reported_as_root_issues(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    (app["desktop_root"] / "junk.txt").write_text("junk", encoding="utf-8")
    app_dir = app["desktop_root"] / "phi.catalog-example"
    (app_dir / "junk.txt").write_text("junk", encoding="utf-8")

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert [(issue.code, issue.relative_path) for issue in snapshot.root_issues] == [
        ("unexpected_root_entry", "junk.txt"),
        ("unexpected_app_entry", "phi.catalog-example/junk.txt"),
    ]
    assert snapshot.ready_count == 1


def test_symlinked_app_directory_is_reported_and_not_followed(tmp_path: Path) -> None:
    desktop_root = tmp_path / "desktop-apps"
    desktop_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = desktop_root / "linked-app"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("host does not permit symlink fixture")

    snapshot = snapshot_desktop_catalog(
        desktop_root=desktop_root,
        applications_root=tmp_path / "applications",
        install_root=tmp_path / "installed",
    )

    assert snapshot.item_count == 0
    assert [(issue.code, issue.relative_path) for issue in snapshot.root_issues] == [
        ("unsafe_app_directory", "linked-app")
    ]


def test_catalog_snapshot_rejects_item_digest_tampering(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )
    payload = snapshot.to_dict()
    payload["items"][0]["desktop_name"] = "Changed"

    with pytest.raises(ValueError, match="item digest"):
        DesktopCatalogSnapshot.from_dict(payload)


def test_catalog_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    result = DesktopCatalogService().snapshot(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )
    payload = result.receipt.to_dict()
    payload["ready_count"] = 0
    payload["blocked_count"] = 1

    with pytest.raises(ValueError, match="digest"):
        DesktopCatalogReceipt.from_dict(payload)


def test_catalog_item_bundle_name_is_bound_to_plan_prefix(tmp_path: Path) -> None:
    app = _registered_app(tmp_path)
    bundle = Path(app["installed"].bundle_path)
    renamed = bundle.with_name("f" * 16)
    bundle.rename(renamed)

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.items[0].status == "blocked"
    assert "binding_mismatch" in {issue.code for issue in snapshot.items[0].issues}


def test_catalog_does_not_resolve_wayland_or_execute_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _registered_app(tmp_path)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    snapshot = snapshot_desktop_catalog(
        desktop_root=app["desktop_root"],
        applications_root=app["applications_root"],
        install_root=app["install_root"],
    )

    assert snapshot.ready_count == 1
    assert snapshot.catalog_launch_authority is False
