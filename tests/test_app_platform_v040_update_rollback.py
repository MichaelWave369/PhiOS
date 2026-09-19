from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

import phios.apps.desktop_update as update_module
from phios.apps.browser_session import plan_browser_session
from phios.apps.desktop_catalog import snapshot_desktop_catalog
from phios.apps.desktop_launch import (
    DesktopAppInstaller,
    DesktopAppRegistrationRequest,
    DesktopLaunchGrant,
    plan_desktop_app,
)
from phios.apps.desktop_update import (
    DesktopRetentionMarker,
    DesktopRollbackPlan,
    DesktopRollbackReceipt,
    DesktopRollbackRequest,
    DesktopRollbackService,
    DesktopUpdatePlan,
    DesktopUpdateReceipt,
    DesktopUpdateRequest,
    DesktopUpdateService,
    plan_desktop_rollback,
    plan_desktop_update,
    review_desktop_rollback,
    review_desktop_update,
)
from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    AppInstallReceipt,
    BuildPackagePlan,
    PackageArtifact,
    snapshot_installed_tree,
)
from phios.apps.static_web import plan_static_web_adapter


def _manifest(version: str) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.update-example",
            "name": "Update Example",
            "version": version,
            "description": f"Update fixture {version}",
            "source": {
                "repository_url": "https://github.com/example/update-example",
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
    (assets / "app.js").write_text(
        f"console.log({body!r})",
        encoding="utf-8",
    )

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
        timestamp_utc="2026-09-19T16:40:00+00:00",
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


def _setup(tmp_path: Path) -> dict[str, object]:
    v1 = _install_version(
        tmp_path,
        version="1.0.0",
        body="version-one",
        port=9501,
    )
    v2 = _install_version(
        tmp_path,
        version="2.0.0",
        body="version-two",
        port=9502,
    )
    desktop_root = tmp_path / "desktop-apps"
    applications_root = tmp_path / "applications"
    request = DesktopAppRegistrationRequest.from_payloads(
        v1["desktop"].to_dict(),
        v1["browser"].to_dict(),
        v1["static"].to_dict(),
        v1["receipt"].to_dict(),
        approved_desktop_app_plan_sha256=v1["desktop"].sha256(),
        approved_desktop_permissions=v1["desktop"].requested_desktop_permissions,
    )
    installed = DesktopAppInstaller().install(
        request,
        install_root=v1["install_root"],
        desktop_root=desktop_root,
        applications_root=applications_root,
    )
    return {
        "v1": v1,
        "v2": v2,
        "desktop_root": desktop_root,
        "applications_root": applications_root,
        "installed": installed,
        "receipt_root": tmp_path / "transition-receipts",
    }


def _update_plan(state: dict[str, object]) -> DesktopUpdatePlan:
    v1 = state["v1"]
    v2 = state["v2"]
    return plan_desktop_update(
        Path(state["installed"].bundle_path),
        v2["browser"].to_dict(),
        v2["static"].to_dict(),
        v2["receipt"].to_dict(),
        install_root=v1["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )


def _update_request(
    state: dict[str, object],
    plan: DesktopUpdatePlan,
) -> DesktopUpdateRequest:
    v2 = state["v2"]
    return DesktopUpdateRequest.from_payloads(
        plan.to_dict(),
        v2["browser"].to_dict(),
        v2["static"].to_dict(),
        v2["receipt"].to_dict(),
        approved_update_plan_sha256=plan.sha256(),
        approved_active_grant_sha256=plan.active_grant_sha256,
        approved_candidate_desktop_plan_sha256=plan.candidate_desktop_plan_sha256,
        approved_update_permissions=plan.requested_update_permissions,
    )


def _execute_update(state: dict[str, object]):
    plan = _update_plan(state)
    request = _update_request(state, plan)
    result = DesktopUpdateService().execute(
        request,
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    return plan, result


def test_update_plan_binds_active_and_candidate_without_authority(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    review = review_desktop_update(plan.to_dict())

    assert plan.app_id == "phi.update-example"
    assert plan.from_version == "1.0.0"
    assert plan.to_version == "2.0.0"
    assert plan.active_grant_sha256 == state["installed"].grant.sha256()
    assert plan.candidate_desktop_plan_sha256 == state["v2"]["desktop"].sha256()
    assert plan.requested_update_permissions == ("desktop.update.switch",)
    assert plan.retain_previous_version is True
    assert plan.update_authority is False
    assert plan.rollback_authority is False
    assert review.desktop_update_plan_sha256 == plan.sha256()
    assert DesktopUpdatePlan.from_dict(plan.to_dict()) == plan


def test_update_does_not_impose_semver_ordering(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    v0 = _install_version(
        tmp_path,
        version="0.9.0",
        body="older-number",
        port=9503,
    )

    plan = plan_desktop_update(
        Path(state["installed"].bundle_path),
        v0["browser"].to_dict(),
        v0["static"].to_dict(),
        v0["receipt"].to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )

    assert plan.from_version == "1.0.0"
    assert plan.to_version == "0.9.0"


def test_update_request_requires_exact_approvals(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    v2 = state["v2"]

    with pytest.raises(ValueError, match="Approved update plan"):
        DesktopUpdateRequest.from_payloads(
            plan.to_dict(),
            v2["browser"].to_dict(),
            v2["static"].to_dict(),
            v2["receipt"].to_dict(),
            approved_update_plan_sha256="0" * 64,
            approved_active_grant_sha256=plan.active_grant_sha256,
            approved_candidate_desktop_plan_sha256=plan.candidate_desktop_plan_sha256,
            approved_update_permissions=plan.requested_update_permissions,
        )

    with pytest.raises(ValueError, match="exactly match"):
        DesktopUpdateRequest.from_payloads(
            plan.to_dict(),
            v2["browser"].to_dict(),
            v2["static"].to_dict(),
            v2["receipt"].to_dict(),
            approved_update_plan_sha256=plan.sha256(),
            approved_active_grant_sha256=plan.active_grant_sha256,
            approved_candidate_desktop_plan_sha256=plan.candidate_desktop_plan_sha256,
            approved_update_permissions=(),
        )


def test_update_switches_entry_retains_old_bundle_and_receipts_transition(
    tmp_path: Path,
) -> None:
    state = _setup(tmp_path)
    plan, result = _execute_update(state)

    old_bundle = Path(state["installed"].bundle_path)
    candidate_bundle = Path(plan.candidate_bundle_path)
    entry = Path(plan.desktop_entry_path)
    marker_path = Path(result.receipt.retention_marker_path)

    assert old_bundle.is_dir()
    assert candidate_bundle.is_dir()
    assert entry.is_file()
    assert hashlib.sha256(entry.read_bytes()).hexdigest() == plan.candidate_entry_sha256
    assert marker_path.is_file()
    marker = DesktopRetentionMarker.from_dict(
        json.loads(marker_path.read_text(encoding="utf-8"))
    )
    assert marker.retained_bundle_path == str(old_bundle.resolve())
    assert marker.active_bundle_path == str(candidate_bundle)
    assert marker.retained_version == "1.0.0"
    assert marker.active_version == "2.0.0"
    assert result.receipt.status == "updated"
    assert result.receipt.update_switch_authority is True
    assert result.receipt.rollback_authority is False
    assert DesktopUpdateReceipt.from_dict(result.receipt.to_dict()) == result.receipt
    candidate_grant = DesktopLaunchGrant.from_dict(
        json.loads((candidate_bundle / "grant.json").read_text(encoding="utf-8"))
    )
    assert candidate_grant == result.candidate_grant


def test_catalog_marks_new_version_ready_and_previous_version_retained(
    tmp_path: Path,
) -> None:
    state = _setup(tmp_path)
    _, result = _execute_update(state)

    snapshot = snapshot_desktop_catalog(
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        install_root=state["v1"]["install_root"],
    )
    by_version = {item.app_version: item for item in snapshot.items}

    assert snapshot.item_count == 2
    assert by_version["2.0.0"].status == "ready"
    assert by_version["1.0.0"].status == "blocked"
    assert tuple(issue.code for issue in by_version["1.0.0"].issues) == (
        "retained_inactive",
    )
    assert snapshot.root_issues == ()
    assert Path(result.receipt.retention_marker_path).is_file()


def test_candidate_install_drift_after_review_blocks_update_before_switch(
    tmp_path: Path,
) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    request = _update_request(state, plan)
    v2_path = state["v2"]["install_path"]
    (v2_path / "payload" / "dist" / "index.html").write_text(
        "tampered",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="installed tree changed"):
        DesktopUpdateService().execute(
            request,
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )

    assert not Path(plan.candidate_bundle_path).exists()
    assert (
        hashlib.sha256(Path(plan.desktop_entry_path).read_bytes()).hexdigest()
        == plan.active_entry_sha256
    )


def test_active_launcher_tamper_after_review_blocks_update(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    request = _update_request(state, plan)
    entry = Path(plan.desktop_entry_path)
    entry.write_text(entry.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="desktop entry"):
        DesktopUpdateService().execute(
            request,
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )

    assert not Path(plan.candidate_bundle_path).exists()


def test_update_receipt_persistence_failure_restores_old_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    request = _update_request(state, plan)
    original_writer = update_module._write_json_atomic

    def fail_receipt(path: Path, payload: dict[str, object]) -> None:
        if path.name.startswith("desktop-update-"):
            raise OSError("receipt store unavailable")
        original_writer(path, payload)

    monkeypatch.setattr(update_module, "_write_json_atomic", fail_receipt)

    with pytest.raises(OSError, match="receipt store unavailable"):
        DesktopUpdateService().execute(
            request,
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )

    assert not Path(plan.candidate_bundle_path).exists()
    assert (
        hashlib.sha256(Path(plan.desktop_entry_path).read_bytes()).hexdigest()
        == plan.active_entry_sha256
    )
    marker_name = f".retained-{plan.active_desktop_plan_sha256[:16]}.json"
    assert not (Path(plan.active_bundle_path).parent / marker_name).exists()


def test_rollback_plan_is_separate_non_authoritative_contract(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    _, update_result = _execute_update(state)

    rollback = plan_desktop_rollback(
        update_result.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    review = review_desktop_rollback(rollback.to_dict())

    assert rollback.from_version == "2.0.0"
    assert rollback.to_version == "1.0.0"
    assert rollback.active_grant_sha256 == update_result.candidate_grant.sha256()
    assert rollback.target_grant_sha256 == state["installed"].grant.sha256()
    assert rollback.requested_rollback_permissions == ("desktop.rollback.switch",)
    assert rollback.rollback_authority is False
    assert review.desktop_rollback_plan_sha256 == rollback.sha256()
    assert DesktopRollbackPlan.from_dict(rollback.to_dict()) == rollback


def _rollback_request(
    rollback: DesktopRollbackPlan,
    update_receipt: DesktopUpdateReceipt,
) -> DesktopRollbackRequest:
    return DesktopRollbackRequest.from_payloads(
        rollback.to_dict(),
        update_receipt.to_dict(),
        approved_rollback_plan_sha256=rollback.sha256(),
        approved_active_grant_sha256=rollback.active_grant_sha256,
        approved_target_grant_sha256=rollback.target_grant_sha256,
        approved_rollback_permissions=rollback.requested_rollback_permissions,
    )


def test_rollback_requires_explicit_exact_authority(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    _, update_result = _execute_update(state)
    rollback = plan_desktop_rollback(
        update_result.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )

    with pytest.raises(ValueError, match="Approved rollback plan"):
        DesktopRollbackRequest.from_payloads(
            rollback.to_dict(),
            update_result.receipt.to_dict(),
            approved_rollback_plan_sha256="0" * 64,
            approved_active_grant_sha256=rollback.active_grant_sha256,
            approved_target_grant_sha256=rollback.target_grant_sha256,
            approved_rollback_permissions=rollback.requested_rollback_permissions,
        )


def test_rollback_restores_previous_entry_and_flips_retained_version(
    tmp_path: Path,
) -> None:
    state = _setup(tmp_path)
    _, update_result = _execute_update(state)
    rollback = plan_desktop_rollback(
        update_result.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    result = DesktopRollbackService().execute(
        _rollback_request(rollback, update_result.receipt),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )

    entry = Path(rollback.desktop_entry_path)
    assert hashlib.sha256(entry.read_bytes()).hexdigest() == rollback.rollback_entry_sha256
    assert Path(rollback.target_bundle_path).is_dir()
    assert Path(rollback.active_bundle_path).is_dir()
    assert not Path(rollback.retention_marker_path).exists()
    assert Path(result.receipt.retention_marker_path).is_file()
    assert result.receipt.status == "rolled_back"
    assert result.receipt.rollback_switch_authority is True
    assert result.receipt.update_authority is False
    assert DesktopRollbackReceipt.from_dict(result.receipt.to_dict()) == result.receipt

    snapshot = snapshot_desktop_catalog(
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        install_root=state["v1"]["install_root"],
    )
    by_version = {item.app_version: item for item in snapshot.items}
    assert by_version["1.0.0"].status == "ready"
    assert by_version["2.0.0"].status == "blocked"
    assert tuple(issue.code for issue in by_version["2.0.0"].issues) == (
        "retained_inactive",
    )


def test_retention_marker_tamper_blocks_rollback_planning(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    _, update_result = _execute_update(state)
    marker_path = Path(update_result.receipt.retention_marker_path)
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    payload["active_version"] = "9.9.9"
    marker_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="marker digest"):
        plan_desktop_rollback(
            update_result.receipt.to_dict(),
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )


def test_rollback_receipt_persistence_failure_restores_updated_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(tmp_path)
    _, update_result = _execute_update(state)
    rollback = plan_desktop_rollback(
        update_result.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    request = _rollback_request(rollback, update_result.receipt)
    original_writer = update_module._write_json_atomic

    def fail_receipt(path: Path, payload: dict[str, object]) -> None:
        if path.name.startswith("desktop-rollback-"):
            raise OSError("rollback receipt unavailable")
        original_writer(path, payload)

    monkeypatch.setattr(update_module, "_write_json_atomic", fail_receipt)

    with pytest.raises(OSError, match="rollback receipt unavailable"):
        DesktopRollbackService().execute(
            request,
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )

    assert (
        hashlib.sha256(Path(rollback.desktop_entry_path).read_bytes()).hexdigest()
        == rollback.active_entry_sha256
    )
    assert Path(rollback.retention_marker_path).is_file()
    assert not Path(rollback.post_rollback_marker_path).exists()


def test_update_and_rollback_receipts_reject_digest_tampering(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    _, update_result = _execute_update(state)
    update_payload = update_result.receipt.to_dict()
    update_payload["to_version"] = "2.0.1"
    with pytest.raises(ValueError, match="digest"):
        DesktopUpdateReceipt.from_dict(update_payload)

    rollback = plan_desktop_rollback(
        update_result.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    rollback_result = DesktopRollbackService().execute(
        _rollback_request(rollback, update_result.receipt),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    rollback_payload = rollback_result.receipt.to_dict()
    rollback_payload["to_version"] = "0.0.0"
    with pytest.raises(ValueError, match="digest"):
        DesktopRollbackReceipt.from_dict(rollback_payload)
