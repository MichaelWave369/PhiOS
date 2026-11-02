#!/usr/bin/env python3
"""Read-only PhiOS ThinkTank guest lifecycle acceptance assessor.

Does not install, launch, authorize, run network probes, or claim to attest a VM.
Designed to run inside an *already provisioned* isolated PhiOS guest, using
existing PhiOS App Platform validators rather than a second installer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phios.apps.desktop_catalog import snapshot_desktop_catalog
from phios.apps.desktop_launch import DesktopLaunchReceipt
from phios.apps.desktop_update import DesktopRollbackReceipt, DesktopUpdateReceipt
from phios.apps.package_install import AppInstallReceipt, BuildPackagePlan
from scripts.verify_ecosystem_app_candidates import CANDIDATES, CATALOG_FILE, inspect_candidates

SCHEMA = "phios.thinktank_guest_lifecycle_assessment.v0.1"
APP_ID = "phios.thinktank-web"
SOURCE_REPO = "https://github.com/MichaelWave369/think-tank"
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_JSON_BYTES = 2 * 1024 * 1024


def demand(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError("THINKTANK_GUEST_" + code)


def read_json(path: Path) -> dict[str, Any]:
    demand(path.is_absolute() and not path.is_symlink() and path.is_file(), "JSON_PATH_INVALID")
    demand(path.stat().st_size <= MAX_JSON_BYTES, "JSON_OVERSIZE")
    value = json.loads(path.read_text(encoding="utf-8"))
    demand(isinstance(value, dict), "JSON_NOT_OBJECT")
    return value


def reviewed_candidate() -> dict[str, Any]:
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    inspect_candidates(candidates, catalog)
    entries = [item for item in candidates["candidates"] if item["app_key"] == "thinktank-web"]
    demand(len(entries) == 1, "CANDIDATE_MISSING_OR_DUPLICATE")
    candidate = entries[0]
    review = candidate["review"]
    demand(
        review["state"] == "HELD_FOR_OPERATOR_REVIEW"
        and review["installed"] is False
        and review["execution_authorized"] is False
        and review["desktop_launch_grant_verified"] is False
        and review["external_done"] is False
        and candidate["manifest"]["app_id"] == APP_ID
        and candidate["manifest"]["source"]["repository_url"] == SOURCE_REPO
        and candidate["manifest"]["source"]["redistribution"] == "unknown"
        and candidate["manifest"]["permissions"] == []
        and SHA.fullmatch(candidate["source_sha"]) is not None,
        "CANDIDATE_PROMOTION_OR_DRIFT",
    )
    return candidate


def safe_root(path: Path) -> Path:
    demand(path.is_absolute() and path.exists() and path.is_dir(), "ROOT_UNAVAILABLE")
    demand(not path.is_symlink(), "ROOT_SYMLINK")
    return path.resolve(strict=True)


def assess(
    *,
    desktop_root: Path,
    applications_root: Path,
    install_root: Path,
    launch_receipt: Path | None = None,
    update_receipt: Path | None = None,
    rollback_receipt: Path | None = None,
) -> dict[str, Any]:
    """Observe local guest filesystem and optional *self-consistent* receipts.

    A receipt does not authenticate the VM or prove that any host observed its
    boot or network controls. No input file or installed state is mutated.
    """
    candidate = reviewed_candidate()
    roots = [safe_root(x) for x in (desktop_root, applications_root, install_root)]
    demand((update_receipt is None) == (rollback_receipt is None), "UPDATE_ROLLBACK_PAIR_REQUIRED")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "app_id": APP_ID,
        "reviewed_source_sha": candidate["source_sha"],
        "status": "HOLD_FOR_OPERATOR_REVIEW",
        "candidate_still_held": True,
        "guest_local_installed_tree_observed": False,
        "guest_local_desktop_catalog_ready": False,
        "launch_receipt_consistency_checked": False,
        "rollback_receipt_consistency_checked": False,
        "actual_guest_boot_attested": False,
        "network_denial_attested": False,
        "post_reboot_state_persistence_tested": False,
        "physical_device_tested": False,
        "license_redistribution_cleared": False,
        "installer_or_release_authorized": False,
        "production_qualified": False,
        "external_done": False,
        "next_gate": "REAL_ISOLATED_GUEST_INSTALL_LAUNCH_PERSISTENCE_ROLLBACK_WITH_OPERATOR_APPROVAL",
    }
    snapshot = snapshot_desktop_catalog(
        desktop_root=roots[0], applications_root=roots[1], install_root=roots[2]
    )
    demand(not snapshot.root_issues, "CATALOG_ROOT_ISSUES")
    matching = [item for item in snapshot.items if item.app_id == APP_ID]
    demand(len(matching) <= 2, "TOO_MANY_THINKTANK_BUNDLES")
    ready = [item for item in matching if item.status == "ready"]
    demand(len(ready) <= 1, "MULTIPLE_ACTIVE_THINKTANK_VERSIONS")
    if not ready:
        demand(not any((launch_receipt, update_receipt, rollback_receipt)),
               "RECEIPTS_WITHOUT_ACTIVE_INSTALL")
        result["next_gate"] = "NO_READY_INSTALLED_THINKTANK_BUNDLE_IN_SELECTED_GUEST_ROOTS"
        return result

    item = ready[0]
    bundle = Path(item.bundle_path)
    install = AppInstallReceipt.from_dict(read_json(bundle / "install-receipt.json"))
    demand(install.app_id == APP_ID and install.app_version == item.app_version,
           "INSTALL_IDENTITY_MISMATCH")
    path = Path(install.install_path)
    demand(path.is_relative_to(roots[2]), "INSTALL_OUTSIDE_ROOT")
    package = BuildPackagePlan.from_dict(read_json(path / ".phios" / "package-plan.json"))
    demand(
        package.sha256() == install.package_plan_sha256
        and package.app_id == APP_ID
        and package.app_version == install.app_version
        and package.repository_url == SOURCE_REPO
        and package.commit_sha == candidate["source_sha"]
        and package.manifest_sha256 == install.manifest_sha256
        and package.artifact_set_sha256 == install.artifact_set_sha256
        and package.launch_authority is False,
        "INSTALLED_SOURCE_OR_PACKAGE_LINEAGE_DRIFT",
    )
    result["guest_local_installed_tree_observed"] = True
    result["guest_local_desktop_catalog_ready"] = True
    result["installed_payload_sha256"] = install.installed_payload_sha256
    result["desktop_app_plan_sha256"] = item.desktop_app_plan_sha256

    if launch_receipt is not None:
        launch = DesktopLaunchReceipt.from_dict(read_json(launch_receipt))
        demand(
            launch.app_id == APP_ID
            and launch.app_version == item.app_version
            and launch.status == "completed"
            and launch.desktop_launch_grant_sha256 == item.desktop_launch_grant_sha256
            and launch.desktop_app_plan_sha256 == item.desktop_app_plan_sha256
            and launch.install_receipt_sha256 == install.sha256(),
            "LAUNCH_RECEIPT_NOT_BOUND_TO_CURRENT_APP",
        )
        result["launch_receipt_consistency_checked"] = True

    if update_receipt is not None and rollback_receipt is not None:
        updated = DesktopUpdateReceipt.from_dict(read_json(update_receipt))
        rolled = DesktopRollbackReceipt.from_dict(read_json(rollback_receipt))
        demand(
            updated.app_id == APP_ID
            and rolled.app_id == APP_ID
            and rolled.desktop_update_receipt_sha256 == updated.sha256()
            and rolled.from_version == updated.to_version
            and rolled.to_version == updated.from_version
            and rolled.active_bundle_path == updated.previous_bundle_path
            and rolled.retained_bundle_path == updated.active_bundle_path
            and rolled.active_bundle_path == item.bundle_path
            and rolled.active_grant_sha256 == item.desktop_launch_grant_sha256,
            "ROLLBACK_RECEIPT_NOT_BOUND_TO_CURRENT_APP",
        )
        result["rollback_receipt_consistency_checked"] = True

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-root", type=Path, required=True)
    parser.add_argument("--applications-root", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path)
    parser.add_argument("--update-receipt", type=Path)
    parser.add_argument("--rollback-receipt", type=Path)
    parser.add_argument("--require-complete-lifecycle", action="store_true",
                        help="Fail unless install, launch and rollback receipt chain is observed")
    args = parser.parse_args()
    try:
        receipt = assess(
            desktop_root=args.desktop_root,
            applications_root=args.applications_root,
            install_root=args.install_root,
            launch_receipt=args.launch_receipt,
            update_receipt=args.update_receipt,
            rollback_receipt=args.rollback_receipt,
        )
        if args.require_complete_lifecycle:
            demand(
                receipt["guest_local_desktop_catalog_ready"]
                and receipt["launch_receipt_consistency_checked"]
                and receipt["rollback_receipt_consistency_checked"],
                "COMPLETE_LOCAL_LIFECYCLE_NOT_OBSERVED",
            )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print("HELD: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
