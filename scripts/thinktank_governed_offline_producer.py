#!/usr/bin/env python3
"""Opt-in production-service ThinkTank offline build (NO INSTALL / NO RELEASE).

Preflight is read-only. Execution requires separate, exact approval arguments
and delegates receipt creation solely to PhiOS v0.32 NpmOfflineBuildService.
Do not use this command as a way to grant operator or redistribution authority.
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

from phios.apps.npm_offline import (
    NpmOfflineBuildPlan,
    NpmOfflineBuildRequest,
    NpmOfflineBuildService,
)
from phios.apps.sandbox import BuildSandboxPolicy
from scripts.thinktank_guest_acceptance import reviewed_candidate
from scripts.thinktank_package_plan_gate import (
    artifacts_from_handoff,
    load_json,
    review as review_package_plan,
)

SCHEMA = "phios.thinktank_governed_offline_execution.v0.1"
SOURCE_SHA = "655d96f7ff892c9989f75cf874e74689f7694127"
APP_ID = "phios.thinktank-web"
_REVIEW_NOTE = "DISPOSABLE_OFFLINE_BUILD_ONLY_NO_PACKAGE_INSTALL_APPROVAL"
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def demand(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("THINKTANK_V066_" + message)


def preflight(
    handoff: dict[str, Any],
    offline_plan_payload: dict[str, Any],
    acquisition_payload: dict[str, Any],
    cache_payload: dict[str, Any],
    *,
    approval_sha: str | None = None,
) -> tuple[NpmOfflineBuildRequest, dict[str, Any]]:
    candidate = reviewed_candidate()
    artifacts = artifacts_from_handoff(handoff, candidate)
    plan = NpmOfflineBuildPlan.from_dict(offline_plan_payload)
    derived = plan.derived_build_plan
    demand(
        candidate["source_sha"] == SOURCE_SHA
        and derived.app_id == APP_ID
        and derived.repository_url == candidate["manifest"]["source"]["repository_url"]
        and derived.commit_sha == SOURCE_SHA
        and derived.manifest_sha256 == handoff["candidate_manifest_sha256"]
        and derived.status == "ready_for_review"
        and derived.package_manager == "npm"
        and derived.working_directory == "."
        and "build.network.dependencies" not in derived.requested_build_permissions
        and set(derived.requested_build_permissions) == {
            "build.process.execute", "build.workspace.write"
        }
        and len(derived.steps) == 2
        and any(s.phase == "dependencies" and s.tool == "npm" and
                s.argv == ("npm", "ci", "--offline", "--cache", "/phios/npm-cache")
                and s.requires_network is False for s in derived.steps)
        and any(s.phase == "build" and s.tool == "npm" and
                s.argv == ("npm", "run", "build") and
                s.requires_network is False for s in derived.steps)
        and any(p.startswith("dist") for p in derived.expected_outputs)
        and plan.cache_mount_target == "/phios/npm-cache"
        and len(artifacts) == handoff["package_artifact_count"],
        "PINNED_PLAN_OR_BUILD_STEPS_DRIFT",
    )
    # This requests exact self-consistency; it does not independently
    # authenticate the acquisition or npm-cache receipt producer.
    request = NpmOfflineBuildRequest.from_payloads(
        offline_plan_payload, acquisition_payload, cache_payload,
        approved_offline_plan_sha256=plan.sha256(),
    )
    demand(request.release_build_review_sha256 is None,
           "RELEASE_BUILD_LINEAGE_FORBIDDEN")
    if approval_sha is not None:
        demand(isinstance(approval_sha, str) and
               SHA64.fullmatch(approval_sha) is not None and
               approval_sha == plan.sha256(), "EXACT_OFFLINE_PLAN_APPROVAL_REQUIRED")
    return request, {
        "schema_version": SCHEMA,
        "status": "OFFLINE_BUILD_PLAN_REVIEW_ONLY",
        "app_id": APP_ID,
        "source_sha": SOURCE_SHA,
        "offline_plan_sha256": plan.sha256(),
        "verified_handoff_artifact_set_sha256": handoff["package_artifact_set_sha256"],
        "cache_receipt_sha256": request.npm_cache.sha256(),
        "build_executed": False,
        "app_installed": False,
        "desktop_authorized": False,
        "release_authorized": False,
        "next_gate": "EXPLICIT_OPERATOR_APPROVAL_FOR_PRIVATE_DISPOSABLE_OFFLINE_BUILD",
    }


def execute(
    handoff: dict[str, Any],
    offline_plan_payload: dict[str, Any],
    acquisition_payload: dict[str, Any],
    cache_payload: dict[str, Any],
    *,
    approved_offline_plan_sha: str,
    approved_source_sha: str,
    private_execution_root: Path,
    private_receipt_root: Path,
    service: NpmOfflineBuildService | None = None,
) -> dict[str, Any]:
    demand(approved_source_sha == SOURCE_SHA, "EXACT_SOURCE_APPROVAL_REQUIRED")
    request, baseline = preflight(
        handoff, offline_plan_payload, acquisition_payload, cache_payload,
        approval_sha=approved_offline_plan_sha,
    )
    demand(
        private_execution_root.is_absolute()
        and private_receipt_root.is_absolute()
        and not private_execution_root.is_symlink()
        and not private_receipt_root.is_symlink()
        and private_execution_root != private_receipt_root
        and not private_execution_root.is_relative_to(private_receipt_root)
        and not private_receipt_root.is_relative_to(private_execution_root),
        "PRIVATE_ROOTS_MUST_BE_SEPARATE_ABSOLUTE_NONLINKED_PATHS",
    )
    producer = service or NpmOfflineBuildService(
        sandbox_policy=BuildSandboxPolicy(network_mode="deny"),
    )
    # Only this existing PhiOS service creates the real execution and offline
    # receipts; the script must never manufacture or rewrite those records.
    result = producer.execute(
        request, execution_root=private_execution_root,
        receipt_root=private_receipt_root,
    )
    sandbox = result.sandboxed_build
    demand(
        result.offline_receipt_persisted is True
        and sandbox.sandbox_receipt_persisted is True
        and sandbox.control_plane_receipt_persisted is True
        and sandbox.execution.status == "success"
        and sandbox.execution.network_sandbox_enforced is True
        and result.offline_receipt.build_status == "success"
        and result.offline_receipt.network_mode == "deny"
        and result.offline_receipt.network_namespace_enforced is True
        and sandbox.sandbox.controls.network_namespace_enforced is True
        and sandbox.sandbox.controls.host_network_inherited is False,
        "SANDBOX_OR_RECEIPT_PRODUCTION_NOT_QUALIFIED",
    )
    # Actual compiled bytes must match the separate v0.64 hosted inventory.
    # If the pinned build differs, fail rather than promoting to packaging.
    package = review_package_plan(
        handoff, sandbox.execution.to_dict(), result.offline_receipt.to_dict(),
    )
    return {
        **baseline,
        "status": "REAL_PHIOS_OFFLINE_BUILD_RECEIPTS_MATCH_HANDOFF_REVIEW_ONLY",
        "build_executed": True,
        "execution_receipt_sha256": sandbox.execution.sha256(),
        "offline_receipt_sha256": result.offline_receipt.sha256(),
        "sandbox_receipt_sha256": sandbox.sandbox.sha256(),
        "canonical_package_plan_sha256": package["package_plan"]["package_plan_sha256"],
        "operator_package_approval_present": False,
        "receipt_producer_independently_attested": False,
        "next_gate": "INDEPENDENT_RECEIPT_PROVENANCE_AND_EXPLICIT_DISPOSABLE_INSTALL_REVIEW",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--offline-plan", type=Path, required=True)
    parser.add_argument("--acquisition-receipt", type=Path, required=True)
    parser.add_argument("--npm-cache-receipt", type=Path, required=True)
    parser.add_argument("--execute-disposable", action="store_true")
    parser.add_argument("--approve-offline-plan-sha")
    parser.add_argument("--approve-source-sha")
    parser.add_argument("--private-execution-root", type=Path)
    parser.add_argument("--private-receipt-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        inputs = tuple(
            load_json(path.absolute()) for path in (
                args.handoff, args.offline_plan, args.acquisition_receipt,
                args.npm_cache_receipt,
            )
        )
        if args.execute_disposable:
            demand(
                args.approve_offline_plan_sha is not None
                and args.approve_source_sha is not None
                and args.private_execution_root is not None
                and args.private_receipt_root is not None,
                "EXECUTION_REQUIRES_EXPLICIT_SOURCE_PLAN_APPROVAL_AND_ROOTS",
            )
            report = execute(
                *inputs, approved_offline_plan_sha=args.approve_offline_plan_sha,
                approved_source_sha=args.approve_source_sha,
                private_execution_root=args.private_execution_root,
                private_receipt_root=args.private_receipt_root,
            )
        else:
            demand(
                args.approve_offline_plan_sha is None
                and args.approve_source_sha is None
                and args.private_execution_root is None
                and args.private_receipt_root is None,
                "PREFLIGHT_REJECTS_EXECUTION_ARGUMENTS",
            )
            _, report = preflight(*inputs)
        if args.output is not None:
            output = args.output.absolute()
            demand(not output.exists() and not output.is_symlink(),
                   "OUTPUT_EXISTS_OR_SYMLINK")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            json.JSONDecodeError) as exc:
        print("HELD: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
