from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path

import pytest

import phios.apps.cleanup_reconciliation as reconciliation_module
from phios.apps.browser_session import plan_browser_session
from phios.apps.cleanup_reconciliation import (
    CleanupReconciliationObservation,
    CleanupReconciliationPlan,
    CleanupReconciliationReceipt,
    CleanupReconciliationRequest,
    CleanupReconciliationService,
    observe_cleanup_reconciliation,
    plan_cleanup_reconciliation,
    review_cleanup_reconciliation,
)
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
    RetainedCleanupRequest,
    RetainedCleanupService,
    plan_retained_cleanup,
)
from phios.apps.static_web import plan_static_web_adapter


def _manifest(version: str) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.reconcile-example",
            "name": "Reconcile Example",
            "version": version,
            "description": f"Reconciliation fixture {version}",
            "source": {
                "repository_url": "https://github.com/example/reconcile-example",
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
        timestamp_utc="2026-09-19T17:50:00+00:00",
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
    v1 = _install_version(tmp_path, version="1.0.0", body="one", port=9701)
    v2 = _install_version(tmp_path, version="2.0.0", body="two", port=9702)
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


def _prepared_cleanup(
    tmp_path: Path,
    *,
    scope: str = "desktop_bundle_only",
) -> dict[str, object]:
    state = _updated_state(tmp_path)
    cleanup_plan = plan_retained_cleanup(
        state["marker_path"],
        scope=scope,
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    journal = RetainedCleanupJournal(
        journal_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T17:55:00+00:00",
        retained_cleanup_plan_sha256=cleanup_plan.sha256(),
        app_id=cleanup_plan.app_id,
        retained_version=cleanup_plan.retained_version,
        active_version=cleanup_plan.active_version,
        scope=cleanup_plan.scope,
        retained_bundle_path=cleanup_plan.retained_bundle_path,
        retained_install_path=cleanup_plan.retained_install_path,
        retention_marker_path=cleanup_plan.retention_marker_path,
        retained_grant_sha256=cleanup_plan.retained_grant_sha256,
        active_grant_sha256=cleanup_plan.active_grant_sha256,
        retention_marker_sha256=cleanup_plan.retention_marker_sha256,
        approved_cleanup_permissions=cleanup_plan.requested_cleanup_permissions,
    )
    journal_path = (
        Path(state["receipt_root"])
        / f"retained-cleanup-journal-{journal.journal_id}.json"
    )
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(
        json.dumps(journal.to_dict(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    state["cleanup_plan"] = cleanup_plan
    state["journal"] = journal
    state["journal_path"] = journal_path
    return state


def _observe(state: dict[str, object]) -> CleanupReconciliationObservation:
    return observe_cleanup_reconciliation(
        state["journal"].to_dict(),
        state["cleanup_plan"].to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )


def _reconciliation_request(
    state: dict[str, object],
    plan: CleanupReconciliationPlan,
) -> CleanupReconciliationRequest:
    return CleanupReconciliationRequest.from_payloads(
        plan.to_dict(),
        state["journal"].to_dict(),
        state["cleanup_plan"].to_dict(),
        approved_reconciliation_plan_sha256=plan.sha256(),
        approved_observation_sha256=plan.cleanup_reconciliation_observation_sha256,
        approved_journal_sha256=state["journal"].sha256(),
        approved_cleanup_plan_sha256=state["cleanup_plan"].sha256(),
        approved_reconciliation_permissions=plan.requested_reconciliation_permissions,
    )


def _plan_action(
    state: dict[str, object],
    action: str,
) -> CleanupReconciliationPlan:
    return plan_cleanup_reconciliation(
        state["journal"].to_dict(),
        state["cleanup_plan"].to_dict(),
        action=action,
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )


def _execute_action(
    state: dict[str, object],
    plan: CleanupReconciliationPlan,
):
    return CleanupReconciliationService().execute(
        _reconciliation_request(state, plan),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )


def test_untouched_observation_allows_cancel_or_complete(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path)
    observation = _observe(state)

    assert observation.classification == "untouched"
    assert observation.allowed_actions == ("cancel", "complete")
    assert observation.marker_state == "present_verified"
    assert observation.retained_bundle_state == "present_verified"
    assert observation.retained_install_state == "present_verified"
    assert observation.active_state == "verified"
    assert observation.issues == ()
    assert observation.reconciliation_authority is False
    assert observation.cleanup_authority is False
    assert observation.rollback_authority is False
    assert CleanupReconciliationObservation.from_dict(observation.to_dict()) == observation


def test_cancel_plan_and_execution_leave_cleanup_targets_untouched(
    tmp_path: Path,
) -> None:
    state = _prepared_cleanup(tmp_path)
    plan = _plan_action(state, "cancel")
    review = review_cleanup_reconciliation(plan.to_dict())

    assert plan.classification == "untouched"
    assert plan.requested_reconciliation_permissions == (
        "cleanup.reconcile.cancel",
    )
    assert review.cleanup_reconciliation_plan_sha256 == plan.sha256()
    assert review.reconciliation_authority is False

    result = _execute_action(state, plan)

    assert Path(state["cleanup_plan"].retention_marker_path).is_file()
    assert Path(state["cleanup_plan"].retained_bundle_path).is_dir()
    assert Path(state["cleanup_plan"].retained_install_path).is_dir()
    assert result.cleanup_receipt is None
    assert result.receipt.status == "cancelled"
    assert result.receipt.action == "cancel"
    assert result.receipt.reconciliation_authority is True
    assert result.receipt.cleanup_authority is False
    assert result.receipt.rollback_authority is False
    assert CleanupReconciliationReceipt.from_dict(
        result.receipt.to_dict()
    ) == result.receipt

    repeated = _observe(state)
    assert repeated.classification == "invalid"
    assert "bound_reconciliation_receipt_exists" in repeated.issues


def test_partial_observation_after_marker_loss_allows_complete(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path, scope="desktop_bundle_and_install")
    Path(state["cleanup_plan"].retention_marker_path).unlink()

    observation = _observe(state)

    assert observation.classification == "partial"
    assert observation.allowed_actions == ("complete",)
    assert observation.marker_state == "absent"
    assert observation.retained_bundle_state == "present_verified"
    assert observation.retained_install_state == "present_verified"


def test_complete_partial_cleanup_reapproves_destructive_permissions_and_finishes(
    tmp_path: Path,
) -> None:
    state = _prepared_cleanup(tmp_path, scope="desktop_bundle_and_install")
    Path(state["cleanup_plan"].retention_marker_path).unlink()
    plan = _plan_action(state, "complete")

    assert plan.requested_reconciliation_permissions == (
        "cleanup.reconcile.complete",
        "desktop.cleanup.retained",
        "install.cleanup.retained",
    )

    result = _execute_action(state, plan)

    assert not Path(state["cleanup_plan"].retention_marker_path).exists()
    assert not Path(state["cleanup_plan"].retained_bundle_path).exists()
    assert not Path(state["cleanup_plan"].retained_install_path).exists()
    assert result.cleanup_receipt is not None
    assert result.cleanup_receipt.status == "cleaned"
    assert result.receipt.status == "completed"
    assert result.receipt.classification_before == "partial"
    assert result.receipt.classification_after == "effectively_complete"
    assert result.receipt.cleanup_authority is True


def test_untouched_complete_is_explicit_fresh_destructive_authority(
    tmp_path: Path,
) -> None:
    state = _prepared_cleanup(tmp_path)
    plan = _plan_action(state, "complete")

    assert plan.requested_reconciliation_permissions == (
        "cleanup.reconcile.complete",
        "desktop.cleanup.retained",
    )
    result = _execute_action(state, plan)

    assert result.receipt.status == "completed"
    assert not Path(state["cleanup_plan"].retention_marker_path).exists()
    assert not Path(state["cleanup_plan"].retained_bundle_path).exists()
    assert Path(state["cleanup_plan"].retained_install_path).is_dir()


def test_effectively_complete_observation_allows_finalize_only(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path, scope="desktop_bundle_and_install")
    Path(state["cleanup_plan"].retention_marker_path).unlink()
    shutil.rmtree(Path(state["cleanup_plan"].retained_bundle_path))
    shutil.rmtree(Path(state["cleanup_plan"].retained_install_path))

    observation = _observe(state)

    assert observation.classification == "effectively_complete"
    assert observation.allowed_actions == ("finalize",)
    assert observation.marker_state == "absent"
    assert observation.retained_bundle_state == "absent"
    assert observation.retained_install_state == "absent"


def test_finalize_writes_missing_cleanup_receipt_without_deleting_more(
    tmp_path: Path,
) -> None:
    state = _prepared_cleanup(tmp_path)
    Path(state["cleanup_plan"].retention_marker_path).unlink()
    shutil.rmtree(Path(state["cleanup_plan"].retained_bundle_path))
    retained_install = Path(state["cleanup_plan"].retained_install_path)
    before_tree, _, _ = snapshot_installed_tree(retained_install)

    plan = _plan_action(state, "finalize")
    assert plan.requested_reconciliation_permissions == (
        "cleanup.reconcile.finalize",
    )
    result = _execute_action(state, plan)

    after_tree, _, _ = snapshot_installed_tree(retained_install)
    assert before_tree == after_tree
    assert result.cleanup_receipt is not None
    assert result.cleanup_receipt.scope == "desktop_bundle_only"
    assert result.cleanup_receipt.removed_install_path is None
    assert result.receipt.status == "finalized"
    assert result.receipt.classification_before == "effectively_complete"
    assert result.receipt.cleanup_authority is True


def test_desktop_only_missing_install_is_invalid_not_partial(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path, scope="desktop_bundle_only")
    shutil.rmtree(Path(state["cleanup_plan"].retained_install_path))

    observation = _observe(state)

    assert observation.classification == "invalid"
    assert observation.allowed_actions == ()


def test_active_launcher_drift_is_invalid_and_grants_no_action(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path)
    entry = Path(state["cleanup_plan"].desktop_entry_path)
    entry.write_text(entry.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    observation = _observe(state)

    assert observation.classification == "invalid"
    assert observation.active_state == "invalid"
    assert observation.allowed_actions == ()


def test_retained_target_tamper_is_invalid(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path)
    target = Path(state["cleanup_plan"].retained_bundle_path) / "grant.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["app_version"] = "9.9.9"
    target.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    observation = _observe(state)

    assert observation.classification == "invalid"
    assert observation.retained_bundle_state == "present_invalid"
    assert observation.allowed_actions == ()


def test_existing_v041_cleanup_receipt_blocks_duplicate_reconciliation(
    tmp_path: Path,
) -> None:
    state = _updated_state(tmp_path)
    cleanup_plan = plan_retained_cleanup(
        state["marker_path"],
        scope="desktop_bundle_only",
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    request = RetainedCleanupRequest.from_payload(
        cleanup_plan.to_dict(),
        approved_cleanup_plan_sha256=cleanup_plan.sha256(),
        approved_retained_grant_sha256=cleanup_plan.retained_grant_sha256,
        approved_active_grant_sha256=cleanup_plan.active_grant_sha256,
        approved_retention_marker_sha256=cleanup_plan.retention_marker_sha256,
        approved_cleanup_permissions=cleanup_plan.requested_cleanup_permissions,
    )
    finished = RetainedCleanupService().execute(
        request,
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )

    observation = observe_cleanup_reconciliation(
        finished.journal.to_dict(),
        cleanup_plan.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )

    assert observation.classification == "invalid"
    assert observation.bound_cleanup_receipt_count == 1
    assert "bound_cleanup_receipt_exists" in observation.issues
    assert observation.allowed_actions == ()


def test_reconciliation_request_requires_exact_observation_and_permissions(
    tmp_path: Path,
) -> None:
    state = _prepared_cleanup(tmp_path)
    plan = _plan_action(state, "cancel")

    with pytest.raises(ValueError, match="Approved observation"):
        CleanupReconciliationRequest.from_payloads(
            plan.to_dict(),
            state["journal"].to_dict(),
            state["cleanup_plan"].to_dict(),
            approved_reconciliation_plan_sha256=plan.sha256(),
            approved_observation_sha256="0" * 64,
            approved_journal_sha256=state["journal"].sha256(),
            approved_cleanup_plan_sha256=state["cleanup_plan"].sha256(),
            approved_reconciliation_permissions=plan.requested_reconciliation_permissions,
        )

    with pytest.raises(ValueError, match="exactly match"):
        CleanupReconciliationRequest.from_payloads(
            plan.to_dict(),
            state["journal"].to_dict(),
            state["cleanup_plan"].to_dict(),
            approved_reconciliation_plan_sha256=plan.sha256(),
            approved_observation_sha256=plan.cleanup_reconciliation_observation_sha256,
            approved_journal_sha256=state["journal"].sha256(),
            approved_cleanup_plan_sha256=state["cleanup_plan"].sha256(),
            approved_reconciliation_permissions=(),
        )


def test_illegal_action_for_classification_is_blocked(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path)
    Path(state["cleanup_plan"].retention_marker_path).unlink()
    shutil.rmtree(Path(state["cleanup_plan"].retained_bundle_path))

    with pytest.raises(ValueError, match="not allowed"):
        _plan_action(state, "cancel")


def test_cleanup_receipt_write_then_reconciliation_receipt_failure_prevents_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _prepared_cleanup(tmp_path)
    Path(state["cleanup_plan"].retention_marker_path).unlink()
    shutil.rmtree(Path(state["cleanup_plan"].retained_bundle_path))
    plan = _plan_action(state, "finalize")
    original_writer = reconciliation_module._write_json_atomic

    def fail_reconciliation_receipt(path: Path, payload: dict[str, object]) -> None:
        if path.name.startswith("retained-cleanup-reconciliation-"):
            raise OSError("reconciliation receipt unavailable")
        original_writer(path, payload)

    monkeypatch.setattr(
        reconciliation_module,
        "_write_json_atomic",
        fail_reconciliation_receipt,
    )

    with pytest.raises(OSError, match="reconciliation receipt unavailable"):
        _execute_action(state, plan)

    cleanup_receipts = [
        path
        for path in Path(state["receipt_root"]).glob("retained-cleanup-*.json")
        if "journal" not in path.name and "reconciliation" not in path.name
    ]
    assert len(cleanup_receipts) == 1

    observation = _observe(state)
    assert observation.classification == "invalid"
    assert observation.bound_cleanup_receipt_count == 1
    assert observation.allowed_actions == ()


def test_observation_plan_and_receipt_reject_digest_tampering(tmp_path: Path) -> None:
    state = _prepared_cleanup(tmp_path)
    observation = _observe(state)
    observation_payload = observation.to_dict()
    observation_payload["active_version"] = "2.0.1"
    with pytest.raises(ValueError, match="digest"):
        CleanupReconciliationObservation.from_dict(observation_payload)

    plan = _plan_action(state, "cancel")
    plan_payload = plan.to_dict()
    plan_payload["active_version"] = "2.0.1"
    with pytest.raises(ValueError, match="digest"):
        CleanupReconciliationPlan.from_dict(plan_payload)

    result = _execute_action(state, plan)
    receipt_payload = result.receipt.to_dict()
    receipt_payload["app_id"] = "phi.changed"
    with pytest.raises(ValueError, match="digest"):
        CleanupReconciliationReceipt.from_dict(receipt_payload)
