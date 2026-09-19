from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .acquisition import (
    SourceAcquisitionRequest,
    SourceAcquisitionService,
    review_intake_for_acquisition,
)
from .build_execution import BuildExecutionRequest, BuildExecutionService
from .build_plan import plan_build_from_payloads, review_build_plan
from .dependency_broker import (
    DependencyStageRequest,
    DependencyStagingService,
    plan_npm_dependencies,
    review_dependency_plan,
)
from .intake import inspect_public_github_app
from .npm_offline import (
    NpmCachePreparationRequest,
    NpmOfflineBuildRequest,
    NpmOfflineBuildService,
    NpmOfflineCacheService,
    derive_npm_offline_build_plan,
    review_npm_offline_build_plan,
)
from .package_install import (
    AppInstallService,
    AppUninstallService,
    plan_build_package,
    review_build_package,
)
from .registry import AppRegistry
from .runtime import (
    InstalledRuntimeService,
    RuntimeLaunchRequest,
    plan_installed_runtime,
    review_installed_runtime,
)
from .sandbox import BuildSandboxPolicy, SandboxedBuildExecutionService

_MAX_INTAKE_RESULT_BYTES = 2 * 1024 * 1024


def _load_json_file(path: Path) -> Any:
    source = path.expanduser().resolve()
    size = source.stat().st_size
    if size > _MAX_INTAKE_RESULT_BYTES:
        raise ValueError("Intake result JSON exceeds the bounded input size")
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid intake result JSON: {exc.msg}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi-app",
        description="PhiOS App Platform utilities.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect-github",
        help="Read a bounded public GitHub repository snapshot and propose app metadata.",
    )
    inspect_parser.add_argument("repository_url")

    review_parser = subparsers.add_parser(
        "review-intake",
        help="Show the exact commit and manifest digest that must be approved for acquisition.",
    )
    review_parser.add_argument("intake_json", type=Path)

    acquire_parser = subparsers.add_parser(
        "acquire-github",
        help="Acquire one explicitly approved intake result at its exact commit SHA.",
    )
    acquire_parser.add_argument("intake_json", type=Path)
    acquire_parser.add_argument("--approve-commit-sha", required=True)
    acquire_parser.add_argument("--approve-manifest-sha", required=True)
    acquire_parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "source",
    )
    acquire_parser.add_argument("--receipt-root", type=Path, default=None)

    plan_parser = subparsers.add_parser(
        "plan-build",
        help="Create a deterministic non-executing build plan from intake + acquisition receipt.",
    )
    plan_parser.add_argument("intake_json", type=Path)
    plan_parser.add_argument("acquisition_receipt_json", type=Path)

    review_plan_parser = subparsers.add_parser(
        "review-build-plan",
        help="Validate and expose the exact digest and requested authority of a build plan.",
    )
    review_plan_parser.add_argument("build_plan_json", type=Path)

    execute_parser = subparsers.add_parser(
        "execute-build",
        help="Execute one explicitly approved build plan in an isolated working copy.",
    )
    execute_parser.add_argument("build_plan_json", type=Path)
    execute_parser.add_argument("acquisition_receipt_json", type=Path)
    execute_parser.add_argument("--approve-plan-sha", required=True)
    execute_parser.add_argument("--approve-source-sha", required=True)
    execute_parser.add_argument(
        "--allow-build-permission",
        action="append",
        default=[],
        dest="build_permissions",
    )
    execute_parser.add_argument(
        "--execution-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "builds",
    )
    execute_parser.add_argument("--receipt-root", type=Path, default=None)
    execute_parser.add_argument("--step-timeout-seconds", type=int, default=900)

    sandbox_parser = subparsers.add_parser(
        "execute-sandboxed-build",
        help="Execute one explicitly approved build plan using the Linux Bubblewrap sandbox.",
    )
    sandbox_parser.add_argument("build_plan_json", type=Path)
    sandbox_parser.add_argument("acquisition_receipt_json", type=Path)
    sandbox_parser.add_argument("--approve-plan-sha", required=True)
    sandbox_parser.add_argument("--approve-source-sha", required=True)
    sandbox_parser.add_argument(
        "--allow-build-permission",
        action="append",
        default=[],
        dest="build_permissions",
    )
    sandbox_parser.add_argument(
        "--sandbox-network",
        choices=("deny", "inherit"),
        default="deny",
    )
    sandbox_parser.add_argument("--sandbox-wall-seconds", type=int, default=900)
    sandbox_parser.add_argument("--sandbox-cpu-seconds", type=int, default=600)
    sandbox_parser.add_argument("--sandbox-memory-mib", type=int, default=8192)
    sandbox_parser.add_argument("--sandbox-open-files", type=int, default=1024)
    sandbox_parser.add_argument("--sandbox-max-file-mib", type=int, default=512)
    sandbox_parser.add_argument(
        "--execution-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "builds",
    )
    sandbox_parser.add_argument("--receipt-root", type=Path, default=None)

    dependency_plan_parser = subparsers.add_parser(
        "plan-dependencies",
        help="Create a deterministic npm dependency staging plan from a reviewed build plan.",
    )
    dependency_plan_parser.add_argument("build_plan_json", type=Path)
    dependency_plan_parser.add_argument("acquisition_receipt_json", type=Path)

    dependency_review_parser = subparsers.add_parser(
        "review-dependency-plan",
        help="Expose exact dependency-plan digest and host approvals required for staging.",
    )
    dependency_review_parser.add_argument("dependency_plan_json", type=Path)

    dependency_stage_parser = subparsers.add_parser(
        "stage-dependencies",
        help="Download and content-address exact approved npm lockfile artifacts.",
    )
    dependency_stage_parser.add_argument("dependency_plan_json", type=Path)
    dependency_stage_parser.add_argument("--approve-dependency-plan-sha", required=True)
    dependency_stage_parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        dest="dependency_hosts",
    )
    dependency_stage_parser.add_argument(
        "--store-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "dependencies",
    )
    dependency_stage_parser.add_argument("--receipt-root", type=Path, default=None)

    npm_cache_parser = subparsers.add_parser(
        "prepare-npm-cache",
        help="Prepare an isolated npm cache from one explicitly approved dependency receipt.",
    )
    npm_cache_parser.add_argument("dependency_receipt_json", type=Path)
    npm_cache_parser.add_argument("--approve-dependency-receipt-sha", required=True)
    npm_cache_parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "npm-cache",
    )
    npm_cache_parser.add_argument("--receipt-root", type=Path, default=None)

    offline_plan_parser = subparsers.add_parser(
        "plan-offline-npm-build",
        help="Derive a separately reviewable network-free npm build plan.",
    )
    offline_plan_parser.add_argument("build_plan_json", type=Path)
    offline_plan_parser.add_argument("npm_cache_receipt_json", type=Path)

    offline_review_parser = subparsers.add_parser(
        "review-offline-npm-build",
        help="Expose the exact v0.32 offline plan digest and reduced authority.",
    )
    offline_review_parser.add_argument("offline_plan_json", type=Path)

    offline_execute_parser = subparsers.add_parser(
        "execute-offline-npm-build",
        help="Execute an approved v0.32 npm plan in the network-denied Linux sandbox.",
    )
    offline_execute_parser.add_argument("offline_plan_json", type=Path)
    offline_execute_parser.add_argument("acquisition_receipt_json", type=Path)
    offline_execute_parser.add_argument("npm_cache_receipt_json", type=Path)
    offline_execute_parser.add_argument("--approve-offline-plan-sha", required=True)
    offline_execute_parser.add_argument("--sandbox-wall-seconds", type=int, default=900)
    offline_execute_parser.add_argument("--sandbox-cpu-seconds", type=int, default=600)
    offline_execute_parser.add_argument("--sandbox-memory-mib", type=int, default=8192)
    offline_execute_parser.add_argument("--sandbox-open-files", type=int, default=1024)
    offline_execute_parser.add_argument("--sandbox-max-file-mib", type=int, default=512)
    offline_execute_parser.add_argument(
        "--execution-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "builds",
    )
    offline_execute_parser.add_argument("--receipt-root", type=Path, default=None)

    package_plan_parser = subparsers.add_parser(
        "plan-package",
        help="Create a deterministic install package plan from successful receipted artifacts.",
    )
    package_plan_parser.add_argument("manifest_json", type=Path)
    package_plan_parser.add_argument("registry_json", type=Path)
    package_plan_parser.add_argument("build_execution_receipt_json", type=Path)
    package_plan_parser.add_argument("offline_build_receipt_json", type=Path)

    package_review_parser = subparsers.add_parser(
        "review-package",
        help="Expose the exact v0.33 package-plan digest and install destination.",
    )
    package_review_parser.add_argument("package_plan_json", type=Path)

    install_parser = subparsers.add_parser(
        "install-package",
        help="Atomically install one explicitly approved artifact package.",
    )
    install_parser.add_argument("package_plan_json", type=Path)
    install_parser.add_argument("registry_json", type=Path)
    install_parser.add_argument("build_execution_receipt_json", type=Path)
    install_parser.add_argument("offline_build_receipt_json", type=Path)
    install_parser.add_argument("--approve-package-plan-sha", required=True)
    install_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    install_parser.add_argument("--receipt-root", type=Path, default=None)

    uninstall_parser = subparsers.add_parser(
        "uninstall-package",
        help="Remove one unchanged install bound to an explicitly approved install receipt.",
    )
    uninstall_parser.add_argument("install_receipt_json", type=Path)
    uninstall_parser.add_argument("--approve-install-receipt-sha", required=True)
    uninstall_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    uninstall_parser.add_argument("--receipt-root", type=Path, default=None)

    runtime_plan_parser = subparsers.add_parser(
        "plan-runtime",
        help="Create a reviewed runtime plan from one unchanged v0.33 install.",
    )
    runtime_plan_parser.add_argument("install_receipt_json", type=Path)
    runtime_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    runtime_plan_parser.add_argument("--runtime-wall-seconds", type=int, default=300)
    runtime_plan_parser.add_argument("--runtime-cpu-seconds", type=int, default=300)
    runtime_plan_parser.add_argument("--runtime-memory-mib", type=int, default=2048)
    runtime_plan_parser.add_argument("--runtime-open-files", type=int, default=512)
    runtime_plan_parser.add_argument("--runtime-max-file-mib", type=int, default=128)

    runtime_review_parser = subparsers.add_parser(
        "review-runtime",
        help="Expose the exact v0.34 runtime-plan digest and requested runtime authority.",
    )
    runtime_review_parser.add_argument("runtime_plan_json", type=Path)

    runtime_launch_parser = subparsers.add_parser(
        "launch-runtime",
        help="Launch one explicitly approved installed-app runtime plan.",
    )
    runtime_launch_parser.add_argument("runtime_plan_json", type=Path)
    runtime_launch_parser.add_argument("install_receipt_json", type=Path)
    runtime_launch_parser.add_argument("--approve-runtime-plan-sha", required=True)
    runtime_launch_parser.add_argument(
        "--allow-runtime-permission",
        action="append",
        default=[],
        dest="runtime_permissions",
    )
    runtime_launch_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    runtime_launch_parser.add_argument(
        "--data-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "data",
    )
    runtime_launch_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "inspect-github":
        try:
            result = inspect_public_github_app(args.repository_url)
        except ValueError as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-intake":
        try:
            payload = _load_json_file(args.intake_json)
            review = review_intake_for_acquisition(payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "acquire-github":
        try:
            payload = _load_json_file(args.intake_json)
            request = SourceAcquisitionRequest.from_intake_payload(
                payload,
                approved_commit_sha=args.approve_commit_sha,
                approved_manifest_sha256=args.approve_manifest_sha,
            )
            receipt = SourceAcquisitionService().acquire(
                request,
                workspace_root=args.workspace_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-build":
        try:
            intake_payload = _load_json_file(args.intake_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            plan = plan_build_from_payloads(intake_payload, receipt_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-build-plan":
        try:
            payload = _load_json_file(args.build_plan_json)
            build_review = review_build_plan(payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(build_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-build":
        try:
            plan_payload = _load_json_file(args.build_plan_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            execution_request = BuildExecutionRequest.from_payloads(
                plan_payload,
                receipt_payload,
                approved_plan_sha256=args.approve_plan_sha,
                approved_source_snapshot_sha256=args.approve_source_sha,
                approved_permissions=tuple(args.build_permissions),
            )
            execution = BuildExecutionService(
                step_timeout_seconds=args.step_timeout_seconds,
            ).execute(
                execution_request,
                execution_root=args.execution_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(execution.to_dict(), sort_keys=True, indent=2))
        return 0 if execution.status in {"success", "no_build_required"} else 1

    if args.command == "execute-sandboxed-build":
        try:
            plan_payload = _load_json_file(args.build_plan_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            sandbox_request = BuildExecutionRequest.from_payloads(
                plan_payload,
                receipt_payload,
                approved_plan_sha256=args.approve_plan_sha,
                approved_source_snapshot_sha256=args.approve_source_sha,
                approved_permissions=tuple(args.build_permissions),
            )
            sandbox_policy = BuildSandboxPolicy(
                network_mode=args.sandbox_network,
                wall_clock_seconds=args.sandbox_wall_seconds,
                cpu_seconds=args.sandbox_cpu_seconds,
                address_space_bytes=args.sandbox_memory_mib * 1024 * 1024,
                max_open_files=args.sandbox_open_files,
                max_file_size_bytes=args.sandbox_max_file_mib * 1024 * 1024,
            )
            sandbox_result = SandboxedBuildExecutionService(
                sandbox_policy,
            ).execute(
                sandbox_request,
                execution_root=args.execution_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(sandbox_result.to_dict(), sort_keys=True, indent=2))
        if not sandbox_result.sandbox_receipt_persisted:
            return 1
        return (
            0
            if sandbox_result.execution.status in {"success", "no_build_required"}
            else 1
        )

    if args.command == "plan-dependencies":
        try:
            build_plan_payload = _load_json_file(args.build_plan_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            dependency_plan = plan_npm_dependencies(
                build_plan_payload,
                receipt_payload,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(dependency_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-dependency-plan":
        try:
            dependency_payload = _load_json_file(args.dependency_plan_json)
            dependency_review = review_dependency_plan(dependency_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(dependency_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "stage-dependencies":
        try:
            dependency_payload = _load_json_file(args.dependency_plan_json)
            stage_request = DependencyStageRequest.from_payload(
                dependency_payload,
                approved_dependency_plan_sha256=args.approve_dependency_plan_sha,
                approved_hosts=tuple(args.dependency_hosts),
            )
            dependency_receipt = DependencyStagingService().stage(
                stage_request,
                store_root=args.store_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(dependency_receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "prepare-npm-cache":
        try:
            dependency_payload = _load_json_file(args.dependency_receipt_json)
            cache_request = NpmCachePreparationRequest.from_payload(
                dependency_payload,
                approved_dependency_receipt_sha256=args.approve_dependency_receipt_sha,
            )
            npm_cache_receipt = NpmOfflineCacheService().prepare(
                cache_request,
                cache_root=args.cache_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(npm_cache_receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-offline-npm-build":
        try:
            build_payload = _load_json_file(args.build_plan_json)
            cache_payload = _load_json_file(args.npm_cache_receipt_json)
            offline_plan = derive_npm_offline_build_plan(build_payload, cache_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(offline_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-offline-npm-build":
        try:
            offline_payload = _load_json_file(args.offline_plan_json)
            offline_review = review_npm_offline_build_plan(offline_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(offline_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-offline-npm-build":
        try:
            offline_payload = _load_json_file(args.offline_plan_json)
            acquisition_payload = _load_json_file(args.acquisition_receipt_json)
            cache_payload = _load_json_file(args.npm_cache_receipt_json)
            offline_request = NpmOfflineBuildRequest.from_payloads(
                offline_payload,
                acquisition_payload,
                cache_payload,
                approved_offline_plan_sha256=args.approve_offline_plan_sha,
            )
            offline_policy = BuildSandboxPolicy(
                network_mode="deny",
                wall_clock_seconds=args.sandbox_wall_seconds,
                cpu_seconds=args.sandbox_cpu_seconds,
                address_space_bytes=args.sandbox_memory_mib * 1024 * 1024,
                max_open_files=args.sandbox_open_files,
                max_file_size_bytes=args.sandbox_max_file_mib * 1024 * 1024,
            )
            offline_result = NpmOfflineBuildService(
                sandbox_policy=offline_policy,
            ).execute(
                offline_request,
                execution_root=args.execution_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(offline_result.to_dict(), sort_keys=True, indent=2))
        if not offline_result.offline_receipt_persisted:
            return 1
        if not offline_result.sandboxed_build.sandbox_receipt_persisted:
            return 1
        return (
            0
            if offline_result.sandboxed_build.execution.status
            in {"success", "no_build_required"}
            else 1
        )

    if args.command == "plan-package":
        try:
            manifest_payload = _load_json_file(args.manifest_json)
            registry = AppRegistry.load(args.registry_json)
            execution_payload = _load_json_file(args.build_execution_receipt_json)
            offline_build_payload = _load_json_file(args.offline_build_receipt_json)
            package_plan = plan_build_package(
                manifest_payload,
                registry,
                execution_payload,
                offline_build_payload,
            )
        except (OSError, ValueError, KeyError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(package_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-package":
        try:
            package_payload = _load_json_file(args.package_plan_json)
            package_review = review_build_package(package_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(package_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "install-package":
        try:
            package_payload = _load_json_file(args.package_plan_json)
            registry = AppRegistry.load(args.registry_json)
            execution_payload = _load_json_file(args.build_execution_receipt_json)
            offline_build_payload = _load_json_file(args.offline_build_receipt_json)
            install_receipt = AppInstallService().install(
                package_payload,
                registry,
                execution_payload,
                offline_build_payload,
                approved_package_plan_sha256=args.approve_package_plan_sha,
                install_root=args.install_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError, KeyError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(install_receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "uninstall-package":
        try:
            install_payload = _load_json_file(args.install_receipt_json)
            uninstall_receipt = AppUninstallService().uninstall(
                install_payload,
                approved_install_receipt_sha256=args.approve_install_receipt_sha,
                install_root=args.install_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(uninstall_receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-runtime":
        try:
            install_payload = _load_json_file(args.install_receipt_json)
            runtime_plan = plan_installed_runtime(
                install_payload,
                install_root=args.install_root,
                wall_clock_seconds=args.runtime_wall_seconds,
                cpu_seconds=args.runtime_cpu_seconds,
                address_space_bytes=args.runtime_memory_mib * 1024 * 1024,
                max_open_files=args.runtime_open_files,
                max_file_size_bytes=args.runtime_max_file_mib * 1024 * 1024,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(runtime_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-runtime":
        try:
            runtime_payload = _load_json_file(args.runtime_plan_json)
            runtime_review = review_installed_runtime(runtime_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(runtime_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "launch-runtime":
        try:
            runtime_payload = _load_json_file(args.runtime_plan_json)
            install_payload = _load_json_file(args.install_receipt_json)
            launch_request = RuntimeLaunchRequest.from_payloads(
                runtime_payload,
                install_payload,
                approved_runtime_plan_sha256=args.approve_runtime_plan_sha,
                approved_runtime_permissions=tuple(args.runtime_permissions),
            )
            launch_result = InstalledRuntimeService().launch(
                launch_request,
                install_root=args.install_root,
                data_root=args.data_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(launch_result.to_dict(), sort_keys=True, indent=2))
        return 0 if launch_result.receipt.status == "exited_success" else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
