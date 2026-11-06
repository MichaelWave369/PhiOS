"""Φ R5C Trust & Recovery Lab: audit real disposable desktop transitions.

This module *observes* receipts and files left by existing PhiOS desktop
update/rollback services. It never updates, launches, installs, or authorizes
anything. A PASS only proves an isolated filesystem rehearsal, NOT a Linux ISO,
a physical device, publisher identity, runtime health, or user-data recovery.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .desktop_catalog import snapshot_desktop_catalog
from .desktop_update import (
    DesktopRetentionMarker,
    DesktopRollbackReceipt,
    DesktopUpdateReceipt,
)

SCHEMA = "phios.disposable_recovery_lab.v0.1"
SCOPE = "disposable_linux_runner_filesystem"
FAULT = "simulated_post_update_health_probe_failure"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(path: Path, root: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label}: missing, symlinked or non-file evidence")
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"{label}: invalid evidence directory")
    safe_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved.parent != safe_root:
        raise ValueError(f"{label}: expected direct child of evidence directory")
    if path.stat().st_size > 128 * 1024:
        raise ValueError(f"{label}: excessive evidence bytes")
    return resolved


def _receipt_bytes(path: Path, root: Path, expected: dict[str, Any], label: str) -> None:
    checked = _safe_path(path, root, label)
    try:
        observed = json.loads(checked.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: invalid receipt JSON") from exc
    if observed != expected:
        raise ValueError(f"{label}: persistent receipt does not match validated receipt")


def audit_disposable_recovery(
    *,
    update_receipt_value: Any,
    rollback_receipt_value: Any,
    update_receipt_path: Path,
    rollback_receipt_path: Path,
    desktop_entry_path: Path,
    desktop_root: Path,
    applications_root: Path,
    install_root: Path,
    receipt_root: Path,
    observed_failure_mode: str,
) -> dict[str, Any]:
    """Check actual files and signed-*none* receipt lineage after explicit rollback.

    The fault is a deliberately synthetic application health-probe decision.
    No real process crash is claimed or injected by this function.
    """
    if observed_failure_mode != FAULT:
        raise ValueError("Only the explicitly simulated health-probe failure is in scope")
    update = DesktopUpdateReceipt.from_dict(update_receipt_value)
    rollback = DesktopRollbackReceipt.from_dict(rollback_receipt_value)
    if update.app_id != rollback.app_id or (
        update.from_version, update.to_version
    ) != (
        rollback.to_version, rollback.from_version
    ):
        raise ValueError("Rehearsal receipts describe different apps or versions")
    if rollback.desktop_update_receipt_sha256 != update.sha256():
        raise ValueError("Rollback receipt is not bound to the exact update receipt")
    if (
        rollback.active_bundle_path != update.previous_bundle_path
        or rollback.retained_bundle_path != update.active_bundle_path
        or rollback.active_grant_sha256 != update.previous_grant_sha256
        or rollback.retained_grant_sha256 != update.active_grant_sha256
        or rollback.active_entry_sha256 != update.previous_entry_sha256
    ):
        raise ValueError("Rollback does not restore the exact retained previous release")
    if not update.update_switch_authority or update.rollback_authority:
        raise ValueError("Update receipt has invalid authority")
    if not rollback.rollback_switch_authority or rollback.update_authority:
        raise ValueError("Rollback receipt has invalid authority")

    _receipt_bytes(update_receipt_path, receipt_root, update.to_dict(), "update receipt")
    _receipt_bytes(rollback_receipt_path, receipt_root, rollback.to_dict(), "rollback receipt")

    entry = _safe_path(desktop_entry_path, applications_root, "restored desktop entry")
    observed_entry_sha = _sha256(entry.read_bytes())
    if observed_entry_sha != update.previous_entry_sha256:
        raise ValueError("Observed desktop launcher bytes do not equal original v1 bytes")

    old_bundle = Path(update.previous_bundle_path)
    candidate_bundle = Path(update.active_bundle_path)
    if (old_bundle.is_symlink() or not old_bundle.is_dir()
        or candidate_bundle.is_symlink() or not candidate_bundle.is_dir()):
        raise ValueError("Old and candidate desktop bundles must both remain present")
    if desktop_root.is_symlink() or not desktop_root.is_dir():
        raise ValueError("Desktop root is missing or symlinked")
    root = desktop_root.resolve(strict=True)
    if root not in old_bundle.resolve(strict=True).parents or (
        root not in candidate_bundle.resolve(strict=True).parents
    ):
        raise ValueError("Rehearsal bundle path is outside disposable desktop root")
    marker_path = Path(rollback.retention_marker_path)
    checked_marker = _safe_path(marker_path, marker_path.parent, "rollback retention marker")
    marker = DesktopRetentionMarker.from_dict(json.loads(
        checked_marker.read_text(encoding="utf-8")
    ))
    if (
        marker.sha256() != rollback.retention_marker_sha256
        or marker.transition_kind != "rollback"
        or marker.active_bundle_path != rollback.active_bundle_path
        or marker.retained_bundle_path != rollback.retained_bundle_path
        or marker.active_version != rollback.to_version
        or marker.retained_version != rollback.from_version
    ):
        raise ValueError("Retention marker does not independently match rollback receipt")
    if Path(update.retention_marker_path).exists():
        raise ValueError("Superseded update retention marker remains active")

    snapshot = snapshot_desktop_catalog(
        desktop_root=desktop_root,
        applications_root=applications_root,
        install_root=install_root,
    )
    by_version = {item.app_version: item for item in snapshot.items}
    if (
        snapshot.item_count != 2
        or snapshot.root_issues
        or set(by_version) != {update.from_version, update.to_version}
        or by_version[update.from_version].status != "ready"
        or by_version[update.to_version].status != "blocked"
        or tuple(x.code for x in by_version[update.to_version].issues)
        != ("retained_inactive",)
    ):
        raise ValueError("Actual installed desktop catalog does not reflect restored v1")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "DISPOSABLE_FILESYSTEM_RECOVERY_OBSERVED",
        "scope": SCOPE,
        "app_id": update.app_id,
        "from_version": update.from_version,
        "candidate_version": update.to_version,
        "simulated_fault": FAULT,
        "update_receipt_sha256": update.sha256(),
        "rollback_receipt_sha256": rollback.sha256(),
        "observed_restored_entry_sha256": observed_entry_sha,
        "retained_candidate_bundle_exists": True,
        "restored_version_is_ready_in_catalog": True,
        "candidate_is_blocked_in_catalog": True,
        "publisher_identity_verified": False,
        "signed_artifact_bound_to_this_rehearsal": False,
        "dependency_review_cleared": False,
        "native_device_qualified": False,
        "real_process_health_probed": False,
        "user_data_rollback_verified": False,
        "install_authority": False,
        "update_authority": False,
        "rollback_authority": False,
        "operations_performed_by_auditor": [],
    }
    report["report_sha256"] = _sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8"))
    return report
