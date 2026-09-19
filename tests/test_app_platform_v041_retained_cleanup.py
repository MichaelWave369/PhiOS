from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

import phios.apps.retained_cleanup as cleanup_module
from phios.apps.browser_session import plan_browser_session
from phios.apps.desktop_catalog import snapshot_desktop_catalog
from phios.apps.desktop_launch import (
    DesktopAppInstaller,
    DesktopAppRegistrationRequest,
    plan_desktop_app,
)
from phios.apps.desktop_update import (
    DesktopUpdateRequest,
    DesktopUpdateService,
    plan_desktop_update,
)
from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    AppInstallReceipt,
    BuildPackagePlan,
    PackageArtifact,
    snapshot_installed_tree,
)
from phios.apps.retained_cleanup import (
    RetainedCleanupJournal,
    RetainedCleanupPlan,
    RetainedCleanupReceipt,
    RetainedCleanupRequest,
    RetainedCleanupService,
    plan_retained_cleanup,
    review_retained_cleanup,
)
from phios.apps.static_web import plan_static_web_adapter


def _manifest(version: str) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.cleanup-example",
            "name": "Cleanup Example",
            "version": version,
            "description": f"Cleanup fixture {version}",
            "source": {
                "repository_url": "https://github.com/example/cleanup-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _install_version(
    tmp_path: Path,
    *,
    version: str,
    body: str,
    port: int,
) -> dict[str, object]:
    manifest = _manifest(version)
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    dist = payload / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    metadata.mkdir()
    (dist / "index.html").write_text(
        f"<html><body>{body}</body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(f"console.log({body!r})", encoding="utf-8")

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
    receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T17:20:00+00:00",
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
    static = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=port,
        serve_seconds=120,
    )
    browser = plan_browser_session(
        static.to_dict(),
        browser_tool="chromium",
        session_seconds=30,
        readiness_timeout_ms=2500,
    )
    desktop = plan_desktop_app(
        browser.to_dict(),
        static.to_dict(),
        receipt.to_dict(),
        install_root=install_root,
    )
    return {
        "manifest": manifest,
        "install_root": install_root,
        "install_path": install_path,
        "receipt": receipt,
        "static": static,
        "browser": browser,
        "desktop": desktop,
    }


def _updated_state(tmp_path: Path) -> dict[str, object]:
    v1 = _install_version(tmp_path, version="1.0.0", body="one", port=9601)
    v2 = _install_version(tmp_path, version="2.0.0", body="two", port=9602)
    desktop_root = tmp_path / "desktop-apps"
    applications_root = tmp_path / "applications"
    receipt_root = tmp_path / "receipts"

    initial_request = DesktopAppRegistrationRequest.from_payloads(
        v1["desktop"].to_dict(),
        v1["browser"].to_dict(),
        v1["static"].to_dict(),
        v1["receipt"].to_dict(),
        approved_desktop_app_plan_sha256=v1["desktop"].sha256(),
        approved_desktop_permissions=v1["desktop"].requested_desktop_permissions,
    )
    initial = DesktopAppInstaller().install(
        initial_request,
        install_root=v1["install_root"],
        desktop_root=desktop_root,
        applications_root=applications_root,
    )

    update_plan = plan_desktop_update(
        Path(initial.bundle_path),
        v2["browser"].to_dict(),
        v2["static"].to_dict(),
        v2["receipt"].to_dict(),
        install_root=v1["install_root"],
        desktop_root=desktop_root,
        applications_root=applications_root,
    )
    update_request = DesktopUpdateRequest.from_payloads(
        update_plan.to_dict(),
        v2["browser"].to_dict(),
        v2["static"].to_dict(),
        v2["receipt"].to_dict(),
        approved_update_plan_sha256=update_plan.sha256(),
        approved_active_grant_sha256=update_plan.active_grant_sha256,
        approved_candidate_desktop_plan_sha256=update_plan.candidate_desktop_plan_sha256,
        approved_update_permissions=update_plan.requested_update_permissions,
    )
    update_result = DesktopUpdateService().execute(
        update_request,
        install_root=v1["install_root"],
        desktop_root=desktop_root,
        applications_root=applications_root,
        receipt_root=receipt_root,
    )
    return {
        "v1": v1,
        "v2": v2,
        "desktop_root": desktop_root,
        "applications_root": applications_root,
        "receipt_root": receipt_root,
        "initial": initial,
        "update_plan": update_plan,
        "update_result": update_result,
        "marker_path": Path(update_result.receipt.retention_marker_path),
    }


def test_cleanup_plan_proves_retained_inactive_and_exposes_no_authority(
    tmp_path: Path,
) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    review = review_retained_cleanup(plan.to_dict())

    assert plan.app_id == "phi.cleanup-example"
    assert plan.retained_version == "1.0.0"
    assert plan.active_version == "2.0.0"
    assert plan.requested_cleanup_permissions == ("desktop.cleanup.retained",)
    assert plan.cleanup_authority is False
    assert plan.rollback_authority is False
    assert review.retained_cleanup_plan_sha256 == plan.sha256()
    assert RetainedCleanupPlan.from_dict(plan.to_dict()) == plan


def test_full_cleanup_scope_requires_second_permission(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_and_install",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )

    assert plan.requested_cleanup_permissions == (
        "desktop.cleanup.retained",
        "install.cleanup.retained",
    )


def test_cleanup_request_requires_exact_approvals(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )

    with pytest.raises(ValueError, match="Approved cleanup plan"):
        RetainedCleanupRequest.from_payload(
            plan.to_dict(),
            approved_cleanup_plan_sha256="0" * 64,
            approved_retained_grant_sha256=plan.retained_grant_sha256,
            approved_active_grant_sha256=plan.active_grant_sha256,
            approved_retention_marker_sha256=plan.retention_marker_sha256,
            approved_cleanup_permissions=plan.requested_cleanup_permissions,
        )

    with pytest.raises(ValueError, match="exactly match"):
        RetainedCleanupRequest.from_payload(
            plan.to_dict(),
            approved_cleanup_plan_sha256=plan.sha256(),
            approved_retained_grant_sha256=plan.retained_grant_sha256,
            approved_active_grant_sha256=plan.active_grant_sha256,
            approved_retention_marker_sha256=plan.retention_marker_sha256,
            approved_cleanup_permissions=(),
        )


def _request(plan: RetainedCleanupPlan) -> RetainedCleanupRequest:
    return RetainedCleanupRequest.from_payload(
        plan.to_dict(),
        approved_cleanup_plan_sha256=plan.sha256(),
        approved_retained_grant_sha256=plan.retained_grant_sha256,
        approved_active_grant_sha256=plan.active_grant_sha256,
        approved_retention_marker_sha256=plan.retention_marker_sha256,
        approved_cleanup_permissions=plan.requested_cleanup_permissions,
    )


def test_desktop_only_cleanup_removes_bundle_and_marker_but_keeps_install(
    tmp_path: Path,
) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    result = RetainedCleanupService().execute(
        _request(plan),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )

    assert not Path(plan.retained_bundle_path).exists()
    assert not Path(plan.retention_marker_path).exists()
    assert Path(plan.retained_install_path).is_dir()
    assert result.receipt.scope == "desktop_bundle_only"
    assert result.receipt.removed_install_path is None
    assert result.receipt.cleanup_authority is True
    assert result.receipt.rollback_authority is False
    assert RetainedCleanupJournal.from_dict(result.journal.to_dict()) == result.journal
    assert RetainedCleanupReceipt.from_dict(result.receipt.to_dict()) == result.receipt

    snapshot = snapshot_desktop_catalog(
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        install_root=state["v1"]["install_root"],
    )
    assert snapshot.item_count == 1
    assert snapshot.ready_count == 1
    assert snapshot.items[0].app_version == "2.0.0"


def test_full_cleanup_removes_retained_bundle_marker_and_install_tree(
    tmp_path: Path,
) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_and_install",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    result = RetainedCleanupService().execute(
        _request(plan),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )

    assert not Path(plan.retained_bundle_path).exists()
    assert not Path(plan.retention_marker_path).exists()
    assert not Path(plan.retained_install_path).exists()
    assert result.receipt.removed_install_path == plan.retained_install_path
    assert (
        result.receipt.removed_install_receipt_sha256
        == plan.retained_install_receipt_sha256
    )
    assert (
        result.receipt.removed_installed_tree_sha256
        == plan.retained_installed_tree_sha256
    )


def test_active_bundle_cannot_be_misidentified_as_cleanup_target(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    marker_path = state["marker_path"]
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    payload["retained_bundle_path"] = payload["active_bundle_path"]
    payload["retained_version"] = payload["active_version"]
    payload["retained_desktop_plan_sha256"] = payload["active_desktop_plan_sha256"]
    payload["retained_grant_sha256"] = payload["active_grant_sha256"]
    marker_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        plan_retained_cleanup(
            marker_path,
            scope="desktop_bundle_only",
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )


def test_retention_marker_tamper_blocks_cleanup_planning(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    marker_path = state["marker_path"]
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    payload["active_version"] = "9.9.9"
    marker_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="marker digest"):
        plan_retained_cleanup(
            marker_path,
            scope="desktop_bundle_only",
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )


def test_duplicate_marker_for_same_retained_bundle_blocks_cleanup(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    marker_path = state["marker_path"]
    duplicate = marker_path.with_name(".retained-duplicate.json")
    duplicate.write_bytes(marker_path.read_bytes())

    with pytest.raises(ValueError, match="exactly one retention marker"):
        plan_retained_cleanup(
            marker_path,
            scope="desktop_bundle_only",
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )


def test_retained_install_drift_blocks_cleanup(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    (state["v1"]["install_path"] / "payload" / "dist" / "index.html").write_text(
        "changed",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="installed tree changed"):
        plan_retained_cleanup(
            state["marker_path"],
            scope="desktop_bundle_and_install",
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )


def test_active_launcher_drift_blocks_cleanup(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    entry = Path(state["update_plan"].desktop_entry_path)
    entry.write_text(entry.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    with pytest.raises(ValueError, match="desktop entry"):
        plan_retained_cleanup(
            state["marker_path"],
            scope="desktop_bundle_only",
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )


def test_journal_is_persisted_before_first_destructive_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    original_unlink = Path.unlink
    observed_journals: list[Path] = []

    def fail_marker_unlink(path: Path, *args, **kwargs):
        if path == Path(plan.retention_marker_path):
            observed_journals.extend(
                Path(state["receipt_root"]).glob("retained-cleanup-journal-*.json")
            )
            raise OSError("simulated destructive boundary failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_marker_unlink)

    with pytest.raises(OSError, match="destructive boundary"):
        RetainedCleanupService().execute(
            _request(plan),
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )

    assert len(observed_journals) == 1
    journal = RetainedCleanupJournal.from_dict(
        json.loads(observed_journals[0].read_text(encoding="utf-8"))
    )
    assert journal.status == "prepared"
    assert Path(plan.retained_bundle_path).is_dir()
    assert Path(plan.retention_marker_path).is_file()


def test_final_receipt_failure_leaves_predeletion_journal_as_partial_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    original_writer = cleanup_module._write_json_atomic

    def fail_final_receipt(path: Path, payload: dict[str, object]) -> None:
        if path.name.startswith("retained-cleanup-") and "journal" not in path.name:
            raise OSError("final cleanup receipt unavailable")
        original_writer(path, payload)

    monkeypatch.setattr(cleanup_module, "_write_json_atomic", fail_final_receipt)

    with pytest.raises(OSError, match="final cleanup receipt unavailable"):
        RetainedCleanupService().execute(
            _request(plan),
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )

    journals = list(Path(state["receipt_root"]).glob("retained-cleanup-journal-*.json"))
    receipts = list(Path(state["receipt_root"]).glob("retained-cleanup-*.json"))
    receipts = [p for p in receipts if "journal" not in p.name]
    assert len(journals) == 1
    assert receipts == []
    assert not Path(plan.retained_bundle_path).exists()
    assert not Path(plan.retention_marker_path).exists()
    assert Path(plan.retained_install_path).is_dir()


def test_cleanup_plan_and_receipt_reject_digest_tampering(tmp_path: Path) -> None:
    state = _updated_state(tmp_path)
    plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    plan_payload = plan.to_dict()
    plan_payload["active_version"] = "2.0.1"
    with pytest.raises(ValueError, match="digest"):
        RetainedCleanupPlan.from_dict(plan_payload)

    result = RetainedCleanupService().execute(
        _request(plan),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    receipt_payload = result.receipt.to_dict()
    receipt_payload["active_version"] = "3.0.0"
    with pytest.raises(ValueError, match="digest"):
        RetainedCleanupReceipt.from_dict(receipt_payload)
