#!/usr/bin/env python3
"""Review a pinned ThinkTank artifact handoff against *real PhiOS-format* receipts.

Does not produce build/offline receipts; consumes externally supplied existing
PhiOS receipts. No install, launch, registry write, release or authority change.
A canonical digest is self-consistency evidence, NOT producer attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    PackageArtifact,
    SuccessfulBuildBinding,
    plan_build_package,
    review_build_package,
)
from phios.apps.registry import AppRegistry
from scripts.thinktank_guest_acceptance import reviewed_candidate

SCHEMA = "phios.thinktank_package_plan_gate.v0.1"
HANDOFF_SCHEMA = "phios.thinktank_preinstall_handoff.v0.1"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_DIST_FILES = 512
MAX_DIST_BYTES = 64 * 1024 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
_HANDOFF_FIELDS = {
    "schema_version", "app_id", "source_repo", "source_sha",
    "candidate_manifest_sha256", "committed_lock_sha256",
    "verified_static_bundle_sha256", "package_artifact_set_sha256",
    "package_artifact_count", "package_total_bytes", "package_artifacts",
    "app_entrypoint", "candidate_still_held", "provider_bridge_started",
    "build_execution_receipt_present", "npm_offline_build_receipt_present",
    "phios_app_installed", "phios_desktop_launch_granted",
    "phios_guest_lifecycle_verified", "license_redistribution_cleared",
    "production_qualified", "status", "next_gate",
}
_HANDOFF_FALSE = (
    "provider_bridge_started", "build_execution_receipt_present",
    "npm_offline_build_receipt_present", "phios_app_installed",
    "phios_desktop_launch_granted", "phios_guest_lifecycle_verified",
    "license_redistribution_cleared", "production_qualified",
)


def demand(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError("THINKTANK_PLAN_" + code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        demand(key not in result, "DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _no_constant(value: str) -> Any:
    raise ValueError("THINKTANK_PLAN_NONFINITE_JSON_VALUE")


def load_json(path: Path) -> dict[str, Any]:
    demand(path.is_absolute() and not path.is_symlink() and path.is_file(),
           "INPUT_NOT_ABSOLUTE_REGULAR_FILE")
    demand(0 < path.stat().st_size <= MAX_JSON_BYTES, "INPUT_SIZE_OUT_OF_BOUNDS")
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw, object_pairs_hook=_unique_object,
                       parse_constant=_no_constant)
    demand(type(value) is dict, "INPUT_NOT_OBJECT")
    return value


def artifacts_from_handoff(handoff: dict[str, Any], candidate: dict[str, Any]
                          ) -> tuple[PackageArtifact, ...]:
    manifest = AppManifest.from_dict(candidate["manifest"])
    demand(set(handoff) == _HANDOFF_FIELDS, "HANDOFF_FIELDS_DRIFT")
    demand(
        handoff["schema_version"] == HANDOFF_SCHEMA
        and handoff["app_id"] == manifest.app_id
        and handoff["source_repo"] == manifest.source.repository_url
        and handoff["source_sha"] == candidate["source_sha"]
        and handoff["candidate_manifest_sha256"] == manifest.sha256()
        and handoff["app_entrypoint"] == manifest.entrypoint.target
        and manifest.app_id == "phios.thinktank-web"
        and manifest.permissions == ()
        and manifest.source.redistribution == "unknown"
        and candidate["review"]["state"] == "HELD_FOR_OPERATOR_REVIEW"
        and candidate["review"]["installed"] is False
        and candidate["review"]["execution_authorized"] is False
        and candidate["review"]["desktop_launch_grant_verified"] is False
        and candidate["review"]["external_done"] is False
        and handoff["candidate_still_held"] is True
        and handoff["status"] == "REVIEW_ONLY_VERIFIED_DIST_NOT_INSTALL_APPROVAL"
        and handoff["next_gate"] == "RECEIPTED_PHIOS_BUILD_AND_EXPLICIT_OPERATOR_REVIEW"
        and all(handoff[name] is False for name in _HANDOFF_FALSE)
        and isinstance(handoff["committed_lock_sha256"], str)
        and SHA256.fullmatch(handoff["committed_lock_sha256"]) is not None
        and isinstance(handoff["verified_static_bundle_sha256"], str)
        and SHA256.fullmatch(handoff["verified_static_bundle_sha256"]) is not None,
        "UNREVIEWED_HANDOFF_OR_CANDIDATE",
    )
    values = handoff["package_artifacts"]
    demand(type(values) is list and 1 <= len(values) <= MAX_DIST_FILES,
           "ARTIFACT_COUNT_INVALID")
    artifacts = tuple(PackageArtifact.from_dict(x) for x in values)
    names = tuple(item.path for item in artifacts)
    demand(
        names == tuple(sorted(names)) and len(set(names)) == len(names)
        and all(name.startswith("dist/") for name in names)
        and "dist/index.html" in names,
        "ARTIFACT_PATHS_INVALID",
    )
    total = sum(item.byte_count for item in artifacts)
    digest = hashlib.sha256(
        b"".join(item.canonical_line() for item in artifacts)
    ).hexdigest()
    demand(
        type(handoff["package_artifact_count"]) is int
        and handoff["package_artifact_count"] == len(artifacts)
        and type(handoff["package_total_bytes"]) is int
        and handoff["package_total_bytes"] == total
        and total <= MAX_DIST_BYTES
        and handoff["package_artifact_set_sha256"] == digest,
        "HANDOFF_ARTIFACT_DIGEST_MISMATCH",
    )
    return artifacts


def verify_actual_workspace(workspace: Path,
                            artifacts: tuple[PackageArtifact, ...]) -> None:
    demand(workspace.is_absolute() and not workspace.is_symlink()
           and workspace.is_dir(), "WORKSPACE_UNSAFE")
    root = workspace.resolve(strict=True)
    dist = root / "dist"
    demand(dist.is_dir() and not dist.is_symlink(), "WORKSPACE_DIST_MISSING")
    actual: set[str] = set()
    for child in dist.rglob("*"):
        demand(not child.is_symlink(), "WORKSPACE_SYMLINK")
        if child.is_dir():
            continue
        demand(child.is_file(), "WORKSPACE_SPECIAL_FILE")
        actual.add(child.relative_to(root).as_posix())
        demand(len(actual) <= MAX_DIST_FILES, "WORKSPACE_TOO_MANY_FILES")
    demand(actual == {item.path for item in artifacts}, "WORKSPACE_FILE_SET_DRIFT")
    for artifact in artifacts:
        path = root / artifact.path
        demand(path.is_file() and not path.is_symlink()
               and path.resolve(strict=True).is_relative_to(root),
               "WORKSPACE_ARTIFACT_UNSAFE")
        data = path.read_bytes()
        demand(len(data) == artifact.byte_count
               and hashlib.sha256(data).hexdigest() == artifact.sha256,
               "WORKSPACE_BYTES_DRIFT")


def review(
    handoff: dict[str, Any], execution: dict[str, Any], offline: dict[str, Any]
) -> dict[str, Any]:
    candidate = reviewed_candidate()
    manifest = AppManifest.from_dict(candidate["manifest"])
    artifacts = artifacts_from_handoff(handoff, candidate)
    # Use PhiOS's existing exact canonical receipt validator. Hosted pilot
    # receipts cannot satisfy this interface and are rejected.
    binding = SuccessfulBuildBinding.from_payloads(execution, offline)
    demand(
        binding.app_id == manifest.app_id
        and binding.repository_url == manifest.source.repository_url
        and binding.commit_sha == candidate["source_sha"]
        and binding.artifacts == artifacts
        and binding.artifact_set_sha256 == handoff["package_artifact_set_sha256"]
        and binding.release_build_review_sha256 is None,
        "GOVERNED_BUILD_OR_RELEASE_LINEAGE_MISMATCH",
    )
    verify_actual_workspace(Path(binding.execution_workspace_path), artifacts)
    registry = AppRegistry()
    registry.register(manifest)  # ephemeral, never persisted to a PhiOS installation
    plan = plan_build_package(manifest.to_dict(), registry, execution, offline)
    package_review = review_build_package(plan.to_dict())
    demand(
        plan.launch_authority is False
        and plan.artifacts == artifacts
        and plan.commit_sha == candidate["source_sha"]
        and plan.artifact_set_sha256 == handoff["package_artifact_set_sha256"]
        and plan.release_build_review_sha256 is None
        and package_review.launch_authority is False,
        "PACKAGE_PLAN_DRIFT",
    )
    return {
        "schema_version": SCHEMA,
        "status": "CANONICAL_PHIOS_PACKAGE_PLAN_REVIEW_ONLY",
        "app_id": manifest.app_id,
        "source_sha": candidate["source_sha"],
        "package_artifact_set_sha256": plan.artifact_set_sha256,
        "package_plan": plan.to_dict(),
        "package_review": package_review.to_dict(),
        "candidate_still_held": True,
        "receipt_producer_independently_attested": False,
        "operator_package_approval_present": False,
        "app_installed": False,
        "desktop_launch_authorized": False,
        "release_authorized": False,
        "production_qualified": False,
        "next_gate": "INDEPENDENT_RECEIPT_PROVENANCE_AND_OPERATOR_APPROVED_DISPOSABLE_INSTALL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--execution-receipt", type=Path, required=True)
    parser.add_argument("--offline-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = review(
            load_json(args.handoff.absolute()),
            load_json(args.execution_receipt.absolute()),
            load_json(args.offline_receipt.absolute()),
        )
        dest = args.output.absolute()
        demand(not dest.exists() and not dest.is_symlink(),
               "OUTPUT_ALREADY_EXISTS_OR_SYMLINK")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    except (ValueError, OSError, KeyError, TypeError, UnicodeError,
            json.JSONDecodeError) as exc:
        print("HELD: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({
        "status": result["status"],
        "package_plan_sha256": result["package_plan"]["package_plan_sha256"],
        "app_installed": False, "release_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
