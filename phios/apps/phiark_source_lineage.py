"""PhiARK R1.0: verify claimed source commit against installed package lineage.

Read-only provenance check for an existing local PhiOS installation. An exact
commit *claim* in a package plan is NOT independent source attestation, an
operator permission, or a license/sandbox qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .package_install import AppInstallReceipt, BuildPackagePlan
from .phiark_service_plan import APP_ID, SOURCE, inspect_phiark_service

_MAX_PLAN_BYTES = 256 * 1024
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _read_package_plan(path: Path) -> BuildPackagePlan:
    """Read an already-installed bounded regular metadata file, no symlinks."""
    metadata = path.parent
    info = metadata.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("PhiARK installed metadata directory is unsafe")
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError("PhiARK package plan is missing; cannot attest source lineage") from exc
    if (
        not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
        or info.st_size <= 0 or info.st_size > _MAX_PLAN_BYTES
    ):
        raise ValueError("PhiARK package plan must be a bounded regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size != info.st_size or opened.st_ino != info.st_ino:
            raise ValueError("PhiARK package plan changed during opening")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(_MAX_PLAN_BYTES + 1)
        if len(raw) > _MAX_PLAN_BYTES:
            raise ValueError("PhiARK package plan exceeds read limit")
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PhiARK package plan is not valid JSON") from exc
    finally:
        os.close(fd)
    return BuildPackagePlan.from_dict(data)


def review_phiark_source_lineage(
    install_receipt_value: Any,
    *, install_root: Path,
    data_directory: Path,
    expected_commit: str,
) -> dict[str, Any]:
    """Check local installed provenance without creating or executing anything."""
    if not isinstance(install_receipt_value, dict):
        raise ValueError("PhiARK installed receipt must be a mapping")
    if not _COMMIT.fullmatch(expected_commit):
        raise ValueError("PhiARK expected commit must be an exact 40-char lowercase SHA")
    preview = inspect_phiark_service(
        install_receipt_value,
        install_root=install_root,
        data_directory=data_directory,
        source_commit_candidate=expected_commit,
    )
    receipt = AppInstallReceipt.from_dict(install_receipt_value)
    metadata = Path(preview.install_path) / ".phios" / "package-plan.json"
    plan = _read_package_plan(metadata)
    checks = {
        "package_plan_digest": plan.sha256() == receipt.package_plan_sha256,
        "app_identity": plan.app_id == APP_ID and plan.app_id == receipt.app_id,
        "version": plan.app_version == receipt.app_version,
        "source_repo": plan.repository_url == SOURCE,
        "commit": plan.commit_sha == expected_commit,
        "manifest": plan.manifest_sha256 == receipt.manifest_sha256,
        "registry": plan.registry_snapshot_sha256 == receipt.registry_snapshot_sha256,
        "build": plan.build_plan_sha256 == receipt.build_plan_sha256,
        "execution": plan.execution_receipt_sha256 == receipt.execution_receipt_sha256,
        "offline_build": plan.offline_build_receipt_sha256 == receipt.offline_build_receipt_sha256,
        "artifacts": plan.artifact_set_sha256 == receipt.artifact_set_sha256
                    and len(plan.artifacts) == receipt.artifact_count
                    and sum(item.byte_count for item in plan.artifacts) == receipt.total_bytes,
        "no_launch_authority": not plan.launch_authority and not receipt.launch_authority,
    }
    if not all(checks.values()):
        failures = ", ".join(sorted(k for k, ok in checks.items() if not ok))
        raise ValueError("PhiARK package/installation lineage mismatch: " + failures)

    # A valid package-plan hash plus installed-tree hash binds the claim to the
    # installed bytes. A malicious author could still fabricate a self-consistent
    # claim, so there is deliberately no source authentication or launch grant.
    body: dict[str, Any] = {
        "schema": "phios.phiark_package_lineage.v0.1",
        "status": "HELD_FOR_SOURCE_ATTESTATION",
        "app_id": APP_ID,
        "source_repository": SOURCE,
        "source_commit_claim": plan.commit_sha,
        "expected_commit": expected_commit,
        "package_plan_sha256": receipt.package_plan_sha256,
        "install_receipt_sha256": receipt.sha256(),
        "installed_tree_sha256": receipt.installed_tree_sha256,
        "runtime_preview_sha256": preview.to_dict()["preview_sha256"],
        "local_package_lineage_consistent": True,
        "source_archive_attested": False,
        "build_source_lineage_independently_verified": False,
        "toolchain_attested": False,
        "service_supervision_verified": False,
        "physical_network_isolation_qualified": False,
        "offline_cold_start_verified": False,
        "install_authority": False,
        "launch_authority": False,
        "gateway_authority": False,
    }
    body["review_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return body
