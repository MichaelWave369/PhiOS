#!/usr/bin/env python3
"""Bridge real, pinned ThinkTank static artifacts into PhiOS package inventory.

Read-only preinstallation review. The existing PhiOS package installer still
requires independent successful build/offline receipts and exact approvals.
A hosted Chrome receipt is NOT accepted as an installation grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phios.apps.manifest import AppManifest
from phios.apps.package_install import PackageArtifact
from scripts.thinktank_guest_acceptance import reviewed_candidate
from scripts.thinktank_web_pilot import verify_committed_lock, verify_dist

SCHEMA = "phios.thinktank_preinstall_handoff.v0.1"
HOSTED_SCHEMA = "phios.thinktank_web_hosted_pilot.v0.2"
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def refuse_if(not_ok: bool, reason: str) -> None:
    if not_ok:
        raise ValueError("THINKTANK_HANDOFF_" + reason)


def load_receipt(path: Path) -> dict[str, Any]:
    refuse_if(path.is_symlink() or not path.is_file(), "UNSAFE_RECEIPT")
    refuse_if(path.stat().st_size > MAX_RECEIPT_BYTES, "OVERSIZE_RECEIPT")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    refuse_if(not isinstance(receipt, dict), "NOT_JSON_OBJECT")
    return receipt


def inventory(
    *, source: Path, dist: Path, committed_lock: Path, hosted_receipt: Path
) -> dict[str, Any]:
    """Review actual on-disk dist without copying or installing app bytes."""
    candidate = reviewed_candidate()
    manifest = AppManifest.from_dict(candidate["manifest"])
    refuse_if(
        candidate["review"]["state"] != "HELD_FOR_OPERATOR_REVIEW"
        or candidate["review"]["installed"] is not False
        or candidate["review"]["execution_authorized"] is not False
        or candidate["review"]["desktop_launch_grant_verified"] is not False
        or candidate["review"]["external_done"] is not False
        or manifest.app_id != "phios.thinktank-web"
        or manifest.source.redistribution != "unknown"
        or manifest.permissions != (),
        "CANDIDATE_AUTHORITY_CHANGED",
    )

    source = source.resolve(strict=True)
    refuse_if(source.is_symlink() or not source.is_dir(), "UNSAFE_SOURCE")
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=15
    ).strip()
    refuse_if(
        SHA40.fullmatch(commit) is None or commit != candidate["source_sha"],
        "SOURCE_PIN_DRIFT",
    )
    lock = verify_committed_lock(source, committed_lock)
    refuse_if(
        dist.is_symlink() or not dist.is_dir(), "UNSAFE_DIST_ROOT"
    )
    dist = dist.resolve(strict=True)
    bundle = verify_dist(dist)

    hosted = load_receipt(hosted_receipt)
    required_exact = {
        "schema_version": HOSTED_SCHEMA,
        "app_id": manifest.app_id,
        "source_repo": manifest.source.repository_url,
        "source_sha": commit,
        "candidate_manifest_sha256": manifest.sha256(),
        "observed_committed_package_lock_sha256": lock["sha256"],
        "locked_dependency_count": lock["package_count"],
        "dependency_lock_provenance": "UPSTREAM_GIT_COMMITTED_AND_SOURCE_SHA_BOUND",
        "source_review_status": "HELD_FOR_OPERATOR_REVIEW",
        "browser_render_result": "PASS_HOSTED_LOOPBACK_CHROMIUM",
        "hosted_offline_build_scope": "DOCKER_NETWORK_NONE_WITH_PRESTAGED_NPM_CACHE",
    }
    refuse_if(
        any(hosted.get(key) != val for key, val in required_exact.items()),
        "HOSTED_SOURCE_LOCK_OR_RENDER_MISMATCH",
    )
    for name in ("hosted_locked_npm_ci", "hosted_offline_cached_build_observed"):
        refuse_if(hosted.get(name) is not True, "HOSTED_BUILD_NOT_OBSERVED")
    for name in (
        "dependency_reproducibility_verified", "offline_dependency_closure_verified",
        "asset_redistribution_reviewed", "browser_network_isolation_verified",
        "provider_bridge_started", "phios_registry_enrolled", "phios_app_installed",
        "phios_desktop_launch_granted", "phios_vm_boot_verified",
        "phios_rollback_verified", "production_qualified",
    ):
        refuse_if(hosted.get(name) is not False, "HOSTED_AUTHORITY_SMUGGLING")

    hosted_bundle = hosted.get("static_bundle")
    refuse_if(
        not isinstance(hosted_bundle, dict)
        or hosted_bundle != bundle,
        "HOSTED_DIST_CHANGED",
    )

    rows: list[dict[str, Any]] = []
    artifacts: list[PackageArtifact] = []
    for file in sorted(dist.rglob("*")):
        refuse_if(file.is_symlink(), "DIST_SYMLINK")
        if file.is_dir():
            continue
        refuse_if(not file.is_file(), "DIST_SPECIAL_FILE")
        value = file.read_bytes()
        relative = file.relative_to(dist).as_posix()
        rows.append({
            "path": relative,
            "bytes": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        })
        artifacts.append(PackageArtifact(
            path="dist/" + relative,
            byte_count=len(value),
            sha256=hashlib.sha256(value).hexdigest(),
        ))
    bundle_digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    refuse_if(
        len(artifacts) != bundle["file_count"]
        or sum(a.byte_count for a in artifacts) != bundle["total_bytes"]
        or bundle_digest != bundle["artifact_set_sha256"],
        "DIST_CHANGED_DURING_INVENTORY",
    )
    artifacts = sorted(artifacts, key=lambda item: item.path)
    package_digest = hashlib.sha256(
        b"".join(artifact.canonical_line() for artifact in artifacts)
    ).hexdigest()

    return {
        "schema_version": SCHEMA,
        "app_id": manifest.app_id,
        "source_repo": manifest.source.repository_url,
        "source_sha": commit,
        "candidate_manifest_sha256": manifest.sha256(),
        "committed_lock_sha256": lock["sha256"],
        "verified_static_bundle_sha256": bundle_digest,
        "package_artifact_set_sha256": package_digest,
        "package_artifact_count": len(artifacts),
        "package_total_bytes": sum(a.byte_count for a in artifacts),
        "package_artifacts": [artifact.to_dict() for artifact in artifacts],
        "app_entrypoint": manifest.entrypoint.target,
        "candidate_still_held": True,
        "provider_bridge_started": False,
        "build_execution_receipt_present": False,
        "npm_offline_build_receipt_present": False,
        "phios_app_installed": False,
        "phios_desktop_launch_granted": False,
        "phios_guest_lifecycle_verified": False,
        "license_redistribution_cleared": False,
        "production_qualified": False,
        "status": "REVIEW_ONLY_VERIFIED_DIST_NOT_INSTALL_APPROVAL",
        "next_gate": "RECEIPTED_PHIOS_BUILD_AND_EXPLICIT_OPERATOR_REVIEW",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--committed-lock", type=Path, required=True)
    parser.add_argument("--hosted-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inventory(
            source=args.source, dist=args.dist, committed_lock=args.committed_lock,
            hosted_receipt=args.hosted_receipt,
        )
        if args.output.is_symlink() or args.output.exists():
            raise ValueError("refuse overwrite or symlink output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print("THINKTANK_HANDOFF_HELD: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({
        "status": report["status"], "source_sha": report["source_sha"],
        "package_artifact_count": report["package_artifact_count"],
        "package_artifact_set_sha256": report["package_artifact_set_sha256"],
        "phios_app_installed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
