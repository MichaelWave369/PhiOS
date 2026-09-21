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
from .browser_session import (
    BrowserSessionRequest,
    BrowserSessionService,
    plan_browser_session,
    review_browser_session,
)
from .build_execution import BuildExecutionRequest, BuildExecutionService
from .cleanup_reconciliation import (
    CleanupReconciliationRequest,
    CleanupReconciliationService,
    observe_cleanup_reconciliation,
    plan_cleanup_reconciliation,
    review_cleanup_reconciliation,
)
from .build_plan import plan_build_from_payloads, review_build_plan
from .desktop_catalog import DesktopCatalogService, review_desktop_catalog
from .desktop_launch import (
    DesktopAppInstaller,
    DesktopAppLaunchService,
    DesktopAppRegistrationRequest,
    DesktopAppRevocationService,
    plan_desktop_app,
    review_desktop_app,
)
from .desktop_update import (
    DesktopRollbackRequest,
    DesktopRollbackService,
    DesktopUpdateRequest,
    DesktopUpdateService,
    plan_desktop_rollback,
    plan_desktop_update,
    review_desktop_rollback,
    review_desktop_update,
)
from .dependency_broker import (
    DependencyStageRequest,
    DependencyStagingService,
    plan_npm_dependencies,
    review_dependency_plan,
)
from .intake import inspect_public_github_app
from .lifecycle_gate import observe_lifecycle_gate
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
from .retained_cleanup import (
    RetainedCleanupRequest,
    RetainedCleanupService,
    plan_retained_cleanup,
    review_retained_cleanup,
)
from .registry import AppRegistry
from .release_advancement import advance_release_candidate
from .release_build_review import review_release_build_plan
from .release_install_proposal import propose_release_install
from .release_compatibility import ReleaseChangeEvidenceService
from .release_review import (
    MarkerChangeAcknowledgement,
    accept_release_change_evidence,
)
from .release_discovery import (
    ReleaseDiscoveryService,
    inspect_selected_release,
    select_release_candidate,
)
from .runtime import (
    InstalledRuntimeService,
    RuntimeLaunchRequest,
    plan_installed_runtime,
    review_installed_runtime,
)
from .sandbox import BuildSandboxPolicy, SandboxedBuildExecutionService
from .static_web import (
    StaticWebAdapterService,
    StaticWebServeRequest,
    plan_static_web_adapter,
    review_static_web_adapter,
)
from .visible_browser import (
    VisibleBrowserSessionRequest,
    VisibleBrowserSessionService,
    plan_visible_browser_session,
    review_visible_browser_session,
)

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

    discover_release_parser = subparsers.add_parser(
        "discover-releases",
        help="Discover bounded GitHub release evidence for one active governed desktop app.",
    )
    discover_release_parser.add_argument("active_bundle_path", type=Path)
    discover_release_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    discover_release_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    discover_release_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )

    select_release_parser = subparsers.add_parser(
        "select-release",
        help="Select one exact discovered release candidate without granting mutation authority.",
    )
    select_release_parser.add_argument("release_discovery_json", type=Path)
    select_release_parser.add_argument("--tag", required=True)
    select_release_parser.add_argument(
        "--approve-release-discovery-sha",
        required=True,
    )
    select_release_parser.add_argument(
        "--allow-prerelease",
        action="store_true",
        default=False,
    )

    inspect_release_parser = subparsers.add_parser(
        "inspect-selected-release",
        help="Inspect one selected release at its exact commit for the existing intake/acquisition pipeline.",
    )
    inspect_release_parser.add_argument("release_selection_json", type=Path)
    inspect_release_parser.add_argument(
        "--approve-release-selection-sha",
        required=True,
    )

    compare_release_parser = subparsers.add_parser(
        "compare-release-candidate",
        help=(
            "Compare verified active app structure with one approved exact-commit "
            "release candidate without issuing a compatibility verdict."
        ),
    )
    compare_release_parser.add_argument("active_bundle_path", type=Path)
    compare_release_parser.add_argument("release_candidate_intake_json", type=Path)
    compare_release_parser.add_argument(
        "--approve-release-candidate-intake-sha",
        required=True,
    )
    compare_release_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    compare_release_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    compare_release_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )

    accept_release_parser = subparsers.add_parser(
        "accept-release-changes",
        help=(
            "Record human acknowledgement of the exact observed v0.45 release "
            "changes without granting compatibility or mutation authority."
        ),
    )
    accept_release_parser.add_argument("release_change_evidence_json", type=Path)
    accept_release_parser.add_argument(
        "--approve-release-change-evidence-sha",
        required=True,
    )
    accept_release_parser.add_argument(
        "--ack-manifest-change",
        action="append",
        default=[],
        dest="ack_manifest_changes",
    )
    accept_release_parser.add_argument(
        "--ack-permission-added",
        action="append",
        default=[],
        dest="ack_permissions_added",
    )
    accept_release_parser.add_argument(
        "--ack-permission-removed",
        action="append",
        default=[],
        dest="ack_permissions_removed",
    )
    accept_release_parser.add_argument(
        "--ack-marker-change",
        action="append",
        default=[],
        dest="ack_marker_changes",
        help="Acknowledge one observed marker change using PATH=CHANGE.",
    )
    accept_release_parser.add_argument("--review-note", default=None)

    advance_release_parser = subparsers.add_parser(
        "advance-release-candidate",
        help=(
            "Bind exact v0.44 candidate, v0.45 evidence, and v0.46 human "
            "acceptance into a non-authoritative v0.47 advancement record."
        ),
    )
    advance_release_parser.add_argument("release_candidate_intake_json", type=Path)
    advance_release_parser.add_argument("release_change_evidence_json", type=Path)
    advance_release_parser.add_argument("release_change_acceptance_json", type=Path)
    advance_release_parser.add_argument(
        "--approve-release-change-acceptance-sha",
        required=True,
    )

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
    plan_parser.add_argument("--release-change-evidence-json", type=Path, default=None)
    plan_parser.add_argument("--release-change-acceptance-json", type=Path, default=None)
    plan_parser.add_argument("--release-candidate-advancement-json", type=Path, default=None)
    plan_parser.add_argument(
        "--approve-release-candidate-advancement-sha",
        default=None,
    )

    review_plan_parser = subparsers.add_parser(
        "review-build-plan",
        help="Validate and expose the exact digest and requested authority of a build plan.",
    )
    review_plan_parser.add_argument("build_plan_json", type=Path)

    release_review_parser = subparsers.add_parser(
        "review-release-build-plan",
        help=(
            "Bind one exact v0.47 advancement record to one exact release BuildPlan "
            "without granting build execution authority."
        ),
    )
    release_review_parser.add_argument("build_plan_json", type=Path)
    release_review_parser.add_argument("release_candidate_advancement_json", type=Path)
    release_review_parser.add_argument(
        "--approve-release-candidate-advancement-sha",
        required=True,
    )

    execute_parser = subparsers.add_parser(
        "execute-build",
        help="Execute one explicitly approved build plan in an isolated working copy.",
    )
    execute_parser.add_argument("build_plan_json", type=Path)
    execute_parser.add_argument("acquisition_receipt_json", type=Path)
    execute_parser.add_argument("--approve-plan-sha", required=True)
    execute_parser.add_argument("--approve-source-sha", required=True)
    execute_parser.add_argument("--release-build-review-json", type=Path, default=None)
    execute_parser.add_argument("--approve-release-build-review-sha", default=None)
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
    sandbox_parser.add_argument("--release-build-review-json", type=Path, default=None)
    sandbox_parser.add_argument("--approve-release-build-review-sha", default=None)
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
    offline_execute_parser.add_argument(
        "--release-build-review-json",
        type=Path,
        default=None,
    )
    offline_execute_parser.add_argument(
        "--approve-release-build-review-sha",
        default=None,
    )
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

    release_install_proposal_parser = subparsers.add_parser(
        "propose-release-install",
        help=(
            "Bind one exact v0.49 release-lineage package plan into a non-authoritative "
            "v0.50 side-by-side install proposal."
        ),
    )
    release_install_proposal_parser.add_argument("package_plan_json", type=Path)
    release_install_proposal_parser.add_argument(
        "--approve-package-plan-sha",
        required=True,
    )

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
        "--release-install-proposal-json",
        type=Path,
        default=None,
    )
    install_parser.add_argument(
        "--approve-release-install-proposal-sha",
        default=None,
    )
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

    static_plan_parser = subparsers.add_parser(
        "plan-static-web",
        help="Map one unchanged install to a reviewed static-web serving plan.",
    )
    static_plan_parser.add_argument("install_receipt_json", type=Path)
    static_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    static_plan_parser.add_argument("--loopback-port", type=int, default=8787)
    static_plan_parser.add_argument("--serve-seconds", type=int, default=300)

    static_review_parser = subparsers.add_parser(
        "review-static-web",
        help="Expose the exact v0.35 static-web mapping and loopback serve authority.",
    )
    static_review_parser.add_argument("static_web_plan_json", type=Path)

    static_serve_parser = subparsers.add_parser(
        "serve-static-web",
        help="Serve one explicitly approved static-web plan on reviewed loopback.",
    )
    static_serve_parser.add_argument("static_web_plan_json", type=Path)
    static_serve_parser.add_argument("install_receipt_json", type=Path)
    static_serve_parser.add_argument("--approve-static-web-plan-sha", required=True)
    static_serve_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    static_serve_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    browser_plan_parser = subparsers.add_parser(
        "plan-browser-session",
        help="Create a reviewed headless Chromium session above one v0.35 static-web plan.",
    )
    browser_plan_parser.add_argument("static_web_plan_json", type=Path)
    browser_plan_parser.add_argument(
        "--browser-tool",
        choices=("chromium", "chromium-browser"),
        default="chromium",
    )
    browser_plan_parser.add_argument("--session-seconds", type=int, default=60)
    browser_plan_parser.add_argument("--readiness-timeout-ms", type=int, default=3000)

    browser_review_parser = subparsers.add_parser(
        "review-browser-session",
        help="Expose the exact v0.36 browser-session digest and requested browser authority.",
    )
    browser_review_parser.add_argument("browser_session_plan_json", type=Path)

    browser_run_parser = subparsers.add_parser(
        "run-browser-session",
        help="Run one explicitly approved coordinated static-server + headless browser session.",
    )
    browser_run_parser.add_argument("browser_session_plan_json", type=Path)
    browser_run_parser.add_argument("static_web_plan_json", type=Path)
    browser_run_parser.add_argument("install_receipt_json", type=Path)
    browser_run_parser.add_argument("--approve-browser-session-plan-sha", required=True)
    browser_run_parser.add_argument("--approve-static-web-plan-sha", required=True)
    browser_run_parser.add_argument(
        "--allow-browser-permission",
        action="append",
        default=[],
        dest="browser_permissions",
    )
    browser_run_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    browser_run_parser.add_argument(
        "--session-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "browser-sessions",
    )
    browser_run_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    visible_plan_parser = subparsers.add_parser(
        "plan-visible-browser",
        help="Create a reviewed Wayland-visible browser plan above one v0.36 browser plan.",
    )
    visible_plan_parser.add_argument("browser_session_plan_json", type=Path)
    visible_plan_parser.add_argument("--wayland-socket", type=Path, required=True)

    visible_review_parser = subparsers.add_parser(
        "review-visible-browser",
        help="Expose the exact v0.37 visible-browser digest and display authority.",
    )
    visible_review_parser.add_argument("visible_browser_plan_json", type=Path)

    visible_run_parser = subparsers.add_parser(
        "run-visible-browser",
        help="Run one explicitly approved visible Wayland browser session.",
    )
    visible_run_parser.add_argument("visible_browser_plan_json", type=Path)
    visible_run_parser.add_argument("browser_session_plan_json", type=Path)
    visible_run_parser.add_argument("static_web_plan_json", type=Path)
    visible_run_parser.add_argument("install_receipt_json", type=Path)
    visible_run_parser.add_argument("--approve-visible-browser-plan-sha", required=True)
    visible_run_parser.add_argument("--approve-browser-session-plan-sha", required=True)
    visible_run_parser.add_argument("--approve-static-web-plan-sha", required=True)
    visible_run_parser.add_argument(
        "--allow-browser-permission",
        action="append",
        default=[],
        dest="visible_browser_permissions",
    )
    visible_run_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    visible_run_parser.add_argument(
        "--session-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "browser-sessions",
    )
    visible_run_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    desktop_plan_parser = subparsers.add_parser(
        "plan-desktop-app",
        help="Create a persistent desktop-launch plan above one v0.36 browser plan.",
    )
    desktop_plan_parser.add_argument("browser_session_plan_json", type=Path)
    desktop_plan_parser.add_argument("static_web_plan_json", type=Path)
    desktop_plan_parser.add_argument("install_receipt_json", type=Path)
    desktop_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )

    desktop_review_parser = subparsers.add_parser(
        "review-desktop-app",
        help="Expose the exact v0.38 desktop plan and persistent launch authority.",
    )
    desktop_review_parser.add_argument("desktop_app_plan_json", type=Path)

    desktop_install_parser = subparsers.add_parser(
        "install-desktop-app",
        help="Install one explicitly approved persistent PhiOS desktop launcher.",
    )
    desktop_install_parser.add_argument("desktop_app_plan_json", type=Path)
    desktop_install_parser.add_argument("browser_session_plan_json", type=Path)
    desktop_install_parser.add_argument("static_web_plan_json", type=Path)
    desktop_install_parser.add_argument("install_receipt_json", type=Path)
    desktop_install_parser.add_argument("--approve-desktop-app-plan-sha", required=True)
    desktop_install_parser.add_argument(
        "--allow-desktop-permission",
        action="append",
        default=[],
        dest="desktop_permissions",
    )
    desktop_install_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    desktop_install_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    desktop_install_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )

    desktop_launch_parser = subparsers.add_parser(
        "launch-desktop-bundle",
        help="Launch one installed persistent desktop bundle using current-user Wayland.",
    )
    desktop_launch_parser.add_argument("bundle_path", type=Path)
    desktop_launch_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    desktop_launch_parser.add_argument(
        "--session-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "browser-sessions",
    )
    desktop_launch_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    desktop_revoke_parser = subparsers.add_parser(
        "revoke-desktop-app",
        help="Revoke one persistent desktop-launch grant and remove its launcher.",
    )
    desktop_revoke_parser.add_argument("bundle_path", type=Path)
    desktop_revoke_parser.add_argument("--approve-desktop-launch-grant-sha", required=True)
    desktop_revoke_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    desktop_revoke_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    desktop_revoke_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    catalog_parser = subparsers.add_parser(
        "catalog-desktop-apps",
        help="Snapshot governed PhiOS desktop apps without granting launch authority.",
    )
    catalog_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    catalog_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    catalog_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )

    catalog_review_parser = subparsers.add_parser(
        "review-desktop-catalog",
        help="Validate one v0.39 catalog snapshot and expose its non-authoritative summary.",
    )
    catalog_review_parser.add_argument("desktop_catalog_json", type=Path)

    update_plan_parser = subparsers.add_parser(
        "plan-desktop-update",
        help="Plan one governed desktop-version transition while retaining the active version.",
    )
    update_plan_parser.add_argument("active_bundle_path", type=Path)
    update_plan_parser.add_argument("candidate_browser_plan_json", type=Path)
    update_plan_parser.add_argument("candidate_static_plan_json", type=Path)
    update_plan_parser.add_argument("candidate_install_receipt_json", type=Path)
    update_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    update_plan_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    update_plan_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )

    update_review_parser = subparsers.add_parser(
        "review-desktop-update",
        help="Validate and expose the exact v0.40 update authority request.",
    )
    update_review_parser.add_argument("desktop_update_plan_json", type=Path)

    update_execute_parser = subparsers.add_parser(
        "execute-desktop-update",
        help="Execute one explicitly approved desktop-version switch.",
    )
    update_execute_parser.add_argument("desktop_update_plan_json", type=Path)
    update_execute_parser.add_argument("candidate_browser_plan_json", type=Path)
    update_execute_parser.add_argument("candidate_static_plan_json", type=Path)
    update_execute_parser.add_argument("candidate_install_receipt_json", type=Path)
    update_execute_parser.add_argument("--approve-update-plan-sha", required=True)
    update_execute_parser.add_argument("--approve-active-grant-sha", required=True)
    update_execute_parser.add_argument(
        "--approve-candidate-desktop-plan-sha",
        required=True,
    )
    update_execute_parser.add_argument(
        "--allow-update-permission",
        action="append",
        default=[],
        dest="update_permissions",
    )
    update_execute_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    update_execute_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    update_execute_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    update_execute_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    rollback_plan_parser = subparsers.add_parser(
        "plan-desktop-rollback",
        help="Plan rollback of one completed v0.40 update to its retained prior version.",
    )
    rollback_plan_parser.add_argument("desktop_update_receipt_json", type=Path)
    rollback_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    rollback_plan_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    rollback_plan_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )

    rollback_review_parser = subparsers.add_parser(
        "review-desktop-rollback",
        help="Validate and expose the exact v0.40 rollback authority request.",
    )
    rollback_review_parser.add_argument("desktop_rollback_plan_json", type=Path)

    rollback_execute_parser = subparsers.add_parser(
        "execute-desktop-rollback",
        help="Execute one explicitly approved rollback to the retained previous version.",
    )
    rollback_execute_parser.add_argument("desktop_rollback_plan_json", type=Path)
    rollback_execute_parser.add_argument("desktop_update_receipt_json", type=Path)
    rollback_execute_parser.add_argument("--approve-rollback-plan-sha", required=True)
    rollback_execute_parser.add_argument("--approve-active-grant-sha", required=True)
    rollback_execute_parser.add_argument("--approve-target-grant-sha", required=True)
    rollback_execute_parser.add_argument(
        "--allow-rollback-permission",
        action="append",
        default=[],
        dest="rollback_permissions",
    )
    rollback_execute_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    rollback_execute_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    rollback_execute_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    rollback_execute_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    cleanup_plan_parser = subparsers.add_parser(
        "plan-retained-cleanup",
        help="Plan cleanup of one proven inactive retained desktop version.",
    )
    cleanup_plan_parser.add_argument("retention_marker_path", type=Path)
    cleanup_plan_parser.add_argument(
        "--scope",
        choices=["desktop_bundle_only", "desktop_bundle_and_install"],
        default="desktop_bundle_only",
    )
    cleanup_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    cleanup_plan_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    cleanup_plan_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )

    cleanup_review_parser = subparsers.add_parser(
        "review-retained-cleanup",
        help="Validate and expose one exact v0.41 retained cleanup plan.",
    )
    cleanup_review_parser.add_argument("retained_cleanup_plan_json", type=Path)

    cleanup_execute_parser = subparsers.add_parser(
        "execute-retained-cleanup",
        help="Execute one explicitly approved retained-version cleanup.",
    )
    cleanup_execute_parser.add_argument("retained_cleanup_plan_json", type=Path)
    cleanup_execute_parser.add_argument("--approve-cleanup-plan-sha", required=True)
    cleanup_execute_parser.add_argument("--approve-retained-grant-sha", required=True)
    cleanup_execute_parser.add_argument("--approve-active-grant-sha", required=True)
    cleanup_execute_parser.add_argument("--approve-retention-marker-sha", required=True)
    cleanup_execute_parser.add_argument(
        "--allow-cleanup-permission",
        action="append",
        default=[],
        dest="cleanup_permissions",
    )
    cleanup_execute_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    cleanup_execute_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    cleanup_execute_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    cleanup_execute_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    lifecycle_gate_parser = subparsers.add_parser(
        "observe-lifecycle-gate",
        help="Observe unresolved prepared cleanup journals that block app lifecycle mutation.",
    )
    lifecycle_gate_parser.add_argument("app_id")
    lifecycle_gate_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    reconciliation_observe_parser = subparsers.add_parser(
        "observe-cleanup-reconciliation",
        help="Classify one stranded v0.41 cleanup journal without granting action authority.",
    )
    reconciliation_observe_parser.add_argument("cleanup_journal_json", type=Path)
    reconciliation_observe_parser.add_argument("retained_cleanup_plan_json", type=Path)
    reconciliation_observe_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    reconciliation_observe_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    reconciliation_observe_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    reconciliation_observe_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    reconciliation_plan_parser = subparsers.add_parser(
        "plan-cleanup-reconciliation",
        help="Plan one explicit recovery action for a classified cleanup journal.",
    )
    reconciliation_plan_parser.add_argument("cleanup_journal_json", type=Path)
    reconciliation_plan_parser.add_argument("retained_cleanup_plan_json", type=Path)
    reconciliation_plan_parser.add_argument(
        "--action",
        choices=["cancel", "complete", "finalize"],
        required=True,
    )
    reconciliation_plan_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    reconciliation_plan_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    reconciliation_plan_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    reconciliation_plan_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )

    reconciliation_review_parser = subparsers.add_parser(
        "review-cleanup-reconciliation",
        help="Validate one exact v0.42 cleanup reconciliation plan.",
    )
    reconciliation_review_parser.add_argument(
        "cleanup_reconciliation_plan_json",
        type=Path,
    )

    reconciliation_execute_parser = subparsers.add_parser(
        "execute-cleanup-reconciliation",
        help="Execute one explicitly approved cleanup reconciliation action.",
    )
    reconciliation_execute_parser.add_argument(
        "cleanup_reconciliation_plan_json",
        type=Path,
    )
    reconciliation_execute_parser.add_argument("cleanup_journal_json", type=Path)
    reconciliation_execute_parser.add_argument("retained_cleanup_plan_json", type=Path)
    reconciliation_execute_parser.add_argument(
        "--approve-reconciliation-plan-sha",
        required=True,
    )
    reconciliation_execute_parser.add_argument(
        "--approve-observation-sha",
        required=True,
    )
    reconciliation_execute_parser.add_argument(
        "--approve-journal-sha",
        required=True,
    )
    reconciliation_execute_parser.add_argument(
        "--approve-cleanup-plan-sha",
        required=True,
    )
    reconciliation_execute_parser.add_argument(
        "--allow-reconciliation-permission",
        action="append",
        default=[],
        dest="reconciliation_permissions",
    )
    reconciliation_execute_parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "installed",
    )
    reconciliation_execute_parser.add_argument(
        "--desktop-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "phios" / "desktop-apps",
    )
    reconciliation_execute_parser.add_argument(
        "--applications-root",
        type=Path,
        default=Path.home() / ".local" / "share" / "applications",
    )
    reconciliation_execute_parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "runtime-receipts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "discover-releases":
        try:
            discovery = ReleaseDiscoveryService().discover(
                args.active_bundle_path,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(discovery.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "select-release":
        try:
            discovery_payload = _load_json_file(args.release_discovery_json)
            selection = select_release_candidate(
                discovery_payload,
                tag_name=args.tag,
                approved_release_discovery_sha256=args.approve_release_discovery_sha,
                allow_prerelease=args.allow_prerelease,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(selection.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "inspect-selected-release":
        try:
            selection_payload = _load_json_file(args.release_selection_json)
            candidate_intake = inspect_selected_release(
                selection_payload,
                approved_release_candidate_selection_sha256=(
                    args.approve_release_selection_sha
                ),
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(candidate_intake.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "compare-release-candidate":
        try:
            candidate_payload = _load_json_file(args.release_candidate_intake_json)
            change_evidence = ReleaseChangeEvidenceService().compare(
                args.active_bundle_path,
                candidate_payload,
                approved_release_candidate_intake_sha256=(
                    args.approve_release_candidate_intake_sha
                ),
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(change_evidence.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "accept-release-changes":
        try:
            evidence_payload = _load_json_file(args.release_change_evidence_json)
            marker_acknowledgements = tuple(
                MarkerChangeAcknowledgement.from_text(item)
                for item in args.ack_marker_changes
            )
            acceptance = accept_release_change_evidence(
                evidence_payload,
                approved_release_change_evidence_sha256=(
                    args.approve_release_change_evidence_sha
                ),
                acknowledged_manifest_changes=tuple(args.ack_manifest_changes),
                acknowledged_permissions_added=tuple(args.ack_permissions_added),
                acknowledged_permissions_removed=tuple(args.ack_permissions_removed),
                acknowledged_source_marker_changes=marker_acknowledgements,
                review_note=args.review_note,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(acceptance.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "advance-release-candidate":
        try:
            candidate_payload = _load_json_file(args.release_candidate_intake_json)
            evidence_payload = _load_json_file(args.release_change_evidence_json)
            acceptance_payload = _load_json_file(args.release_change_acceptance_json)
            advancement = advance_release_candidate(
                candidate_payload,
                evidence_payload,
                acceptance_payload,
                approved_release_change_acceptance_sha256=(
                    args.approve_release_change_acceptance_sha
                ),
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(advancement.to_dict(), sort_keys=True, indent=2))
        return 0

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
            release_evidence_payload = (
                _load_json_file(args.release_change_evidence_json)
                if args.release_change_evidence_json is not None
                else None
            )
            release_acceptance_payload = (
                _load_json_file(args.release_change_acceptance_json)
                if args.release_change_acceptance_json is not None
                else None
            )
            release_advancement_payload = (
                _load_json_file(args.release_candidate_advancement_json)
                if args.release_candidate_advancement_json is not None
                else None
            )
            plan = plan_build_from_payloads(
                intake_payload,
                receipt_payload,
                release_change_evidence_value=release_evidence_payload,
                release_change_acceptance_value=release_acceptance_payload,
                release_candidate_advancement_value=release_advancement_payload,
                approved_release_candidate_advancement_sha256=(
                    args.approve_release_candidate_advancement_sha
                ),
            )
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

    if args.command == "review-release-build-plan":
        try:
            plan_payload = _load_json_file(args.build_plan_json)
            advancement_payload = _load_json_file(
                args.release_candidate_advancement_json
            )
            release_build_review = review_release_build_plan(
                plan_payload,
                advancement_payload,
                approved_release_candidate_advancement_sha256=(
                    args.approve_release_candidate_advancement_sha
                ),
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(release_build_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-build":
        try:
            plan_payload = _load_json_file(args.build_plan_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            release_build_review_payload = (
                _load_json_file(args.release_build_review_json)
                if args.release_build_review_json is not None
                else None
            )
            execution_request = BuildExecutionRequest.from_payloads(
                plan_payload,
                receipt_payload,
                approved_plan_sha256=args.approve_plan_sha,
                approved_source_snapshot_sha256=args.approve_source_sha,
                approved_permissions=tuple(args.build_permissions),
                release_build_review_value=release_build_review_payload,
                approved_release_build_review_sha256=(
                    args.approve_release_build_review_sha
                ),
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
            release_build_review_payload = (
                _load_json_file(args.release_build_review_json)
                if args.release_build_review_json is not None
                else None
            )
            sandbox_request = BuildExecutionRequest.from_payloads(
                plan_payload,
                receipt_payload,
                approved_plan_sha256=args.approve_plan_sha,
                approved_source_snapshot_sha256=args.approve_source_sha,
                approved_permissions=tuple(args.build_permissions),
                release_build_review_value=release_build_review_payload,
                approved_release_build_review_sha256=(
                    args.approve_release_build_review_sha
                ),
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
            release_review_payload = (
                _load_json_file(args.release_build_review_json)
                if args.release_build_review_json is not None
                else None
            )
            offline_request = NpmOfflineBuildRequest.from_payloads(
                offline_payload,
                acquisition_payload,
                cache_payload,
                approved_offline_plan_sha256=args.approve_offline_plan_sha,
                release_build_review_value=release_review_payload,
                approved_release_build_review_sha256=(
                    args.approve_release_build_review_sha
                ),
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

    if args.command == "propose-release-install":
        try:
            package_payload = _load_json_file(args.package_plan_json)
            proposal = propose_release_install(
                package_payload,
                approved_package_plan_sha256=args.approve_package_plan_sha,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(proposal.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "install-package":
        try:
            package_payload = _load_json_file(args.package_plan_json)
            registry = AppRegistry.load(args.registry_json)
            execution_payload = _load_json_file(args.build_execution_receipt_json)
            offline_build_payload = _load_json_file(args.offline_build_receipt_json)
            release_install_proposal_payload = (
                _load_json_file(args.release_install_proposal_json)
                if args.release_install_proposal_json is not None
                else None
            )
            install_receipt = AppInstallService().install(
                package_payload,
                registry,
                execution_payload,
                offline_build_payload,
                approved_package_plan_sha256=args.approve_package_plan_sha,
                install_root=args.install_root,
                receipt_root=args.receipt_root,
                release_install_proposal_value=release_install_proposal_payload,
                approved_release_install_proposal_sha256=(
                    args.approve_release_install_proposal_sha
                ),
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

    if args.command == "plan-static-web":
        try:
            install_payload = _load_json_file(args.install_receipt_json)
            static_plan = plan_static_web_adapter(
                install_payload,
                install_root=args.install_root,
                loopback_port=args.loopback_port,
                serve_seconds=args.serve_seconds,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(static_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-static-web":
        try:
            static_payload = _load_json_file(args.static_web_plan_json)
            static_review = review_static_web_adapter(static_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(static_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "serve-static-web":
        try:
            static_payload = _load_json_file(args.static_web_plan_json)
            install_payload = _load_json_file(args.install_receipt_json)
            static_request = StaticWebServeRequest.from_payloads(
                static_payload,
                install_payload,
                approved_static_web_plan_sha256=args.approve_static_web_plan_sha,
            )
            static_result = StaticWebAdapterService().serve(
                static_request,
                install_root=args.install_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(static_result.to_dict(), sort_keys=True, indent=2))
        return (
            0
            if static_result.receipt.status
            in {"serve_window_complete", "server_exited"}
            else 1
        )

    if args.command == "plan-browser-session":
        try:
            static_payload = _load_json_file(args.static_web_plan_json)
            browser_plan = plan_browser_session(
                static_payload,
                browser_tool=args.browser_tool,
                session_seconds=args.session_seconds,
                readiness_timeout_ms=args.readiness_timeout_ms,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(browser_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-browser-session":
        try:
            browser_payload = _load_json_file(args.browser_session_plan_json)
            browser_review = review_browser_session(browser_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(browser_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "run-browser-session":
        try:
            browser_payload = _load_json_file(args.browser_session_plan_json)
            static_payload = _load_json_file(args.static_web_plan_json)
            install_payload = _load_json_file(args.install_receipt_json)
            browser_request = BrowserSessionRequest.from_payloads(
                browser_payload,
                static_payload,
                install_payload,
                approved_browser_session_plan_sha256=(
                    args.approve_browser_session_plan_sha
                ),
                approved_static_web_plan_sha256=args.approve_static_web_plan_sha,
                approved_browser_permissions=tuple(args.browser_permissions),
            )
            browser_result = BrowserSessionService().run(
                browser_request,
                install_root=args.install_root,
                session_root=args.session_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(browser_result.to_dict(), sort_keys=True, indent=2))
        return 0 if browser_result.receipt.status == "completed" else 1

    if args.command == "plan-visible-browser":
        try:
            browser_payload = _load_json_file(args.browser_session_plan_json)
            visible_plan = plan_visible_browser_session(
                browser_payload,
                wayland_socket_path=args.wayland_socket,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(visible_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-visible-browser":
        try:
            visible_payload = _load_json_file(args.visible_browser_plan_json)
            visible_review = review_visible_browser_session(visible_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(visible_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "run-visible-browser":
        try:
            visible_payload = _load_json_file(args.visible_browser_plan_json)
            browser_payload = _load_json_file(args.browser_session_plan_json)
            static_payload = _load_json_file(args.static_web_plan_json)
            install_payload = _load_json_file(args.install_receipt_json)
            visible_request = VisibleBrowserSessionRequest.from_payloads(
                visible_payload,
                browser_payload,
                static_payload,
                install_payload,
                approved_visible_browser_plan_sha256=(
                    args.approve_visible_browser_plan_sha
                ),
                approved_parent_browser_plan_sha256=(
                    args.approve_browser_session_plan_sha
                ),
                approved_static_web_plan_sha256=args.approve_static_web_plan_sha,
                approved_browser_permissions=tuple(args.visible_browser_permissions),
            )
            visible_result = VisibleBrowserSessionService().run(
                visible_request,
                install_root=args.install_root,
                session_root=args.session_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(visible_result.to_dict(), sort_keys=True, indent=2))
        return 0 if visible_result.receipt.status == "completed" else 1

    if args.command == "plan-desktop-app":
        try:
            browser_payload = _load_json_file(args.browser_session_plan_json)
            static_payload = _load_json_file(args.static_web_plan_json)
            install_payload = _load_json_file(args.install_receipt_json)
            desktop_plan = plan_desktop_app(
                browser_payload,
                static_payload,
                install_payload,
                install_root=args.install_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(desktop_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-desktop-app":
        try:
            desktop_payload = _load_json_file(args.desktop_app_plan_json)
            desktop_review = review_desktop_app(desktop_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(desktop_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "install-desktop-app":
        try:
            desktop_payload = _load_json_file(args.desktop_app_plan_json)
            browser_payload = _load_json_file(args.browser_session_plan_json)
            static_payload = _load_json_file(args.static_web_plan_json)
            install_payload = _load_json_file(args.install_receipt_json)
            desktop_request = DesktopAppRegistrationRequest.from_payloads(
                desktop_payload,
                browser_payload,
                static_payload,
                install_payload,
                approved_desktop_app_plan_sha256=args.approve_desktop_app_plan_sha,
                approved_desktop_permissions=tuple(args.desktop_permissions),
            )
            desktop_install_result = DesktopAppInstaller().install(
                desktop_request,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(desktop_install_result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "launch-desktop-bundle":
        try:
            desktop_launch_result = DesktopAppLaunchService().launch(
                args.bundle_path,
                install_root=args.install_root,
                session_root=args.session_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(desktop_launch_result.to_dict(), sort_keys=True, indent=2))
        return 0 if desktop_launch_result.receipt.status == "completed" else 1

    if args.command == "revoke-desktop-app":
        try:
            revoke_receipt = DesktopAppRevocationService().revoke(
                args.bundle_path,
                approved_desktop_launch_grant_sha256=(
                    args.approve_desktop_launch_grant_sha
                ),
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(revoke_receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "catalog-desktop-apps":
        try:
            catalog_result = DesktopCatalogService().snapshot(
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                install_root=args.install_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(catalog_result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-desktop-catalog":
        try:
            catalog_payload = _load_json_file(args.desktop_catalog_json)
            if (
                isinstance(catalog_payload, dict)
                and set(catalog_payload) == {"snapshot", "receipt"}
            ):
                catalog_payload = catalog_payload["snapshot"]
            catalog_review = review_desktop_catalog(catalog_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(catalog_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-desktop-update":
        try:
            candidate_browser = _load_json_file(args.candidate_browser_plan_json)
            candidate_static = _load_json_file(args.candidate_static_plan_json)
            candidate_install = _load_json_file(args.candidate_install_receipt_json)
            update_plan = plan_desktop_update(
                args.active_bundle_path,
                candidate_browser,
                candidate_static,
                candidate_install,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(update_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-desktop-update":
        try:
            update_payload = _load_json_file(args.desktop_update_plan_json)
            update_review = review_desktop_update(update_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(update_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-desktop-update":
        try:
            update_payload = _load_json_file(args.desktop_update_plan_json)
            candidate_browser = _load_json_file(args.candidate_browser_plan_json)
            candidate_static = _load_json_file(args.candidate_static_plan_json)
            candidate_install = _load_json_file(args.candidate_install_receipt_json)
            update_request = DesktopUpdateRequest.from_payloads(
                update_payload,
                candidate_browser,
                candidate_static,
                candidate_install,
                approved_update_plan_sha256=args.approve_update_plan_sha,
                approved_active_grant_sha256=args.approve_active_grant_sha,
                approved_candidate_desktop_plan_sha256=(
                    args.approve_candidate_desktop_plan_sha
                ),
                approved_update_permissions=tuple(args.update_permissions),
            )
            update_result = DesktopUpdateService().execute(
                update_request,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(update_result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-desktop-rollback":
        try:
            update_receipt = _load_json_file(args.desktop_update_receipt_json)
            rollback_plan = plan_desktop_rollback(
                update_receipt,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(rollback_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-desktop-rollback":
        try:
            rollback_payload = _load_json_file(args.desktop_rollback_plan_json)
            rollback_review = review_desktop_rollback(rollback_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(rollback_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-desktop-rollback":
        try:
            rollback_payload = _load_json_file(args.desktop_rollback_plan_json)
            update_receipt = _load_json_file(args.desktop_update_receipt_json)
            rollback_request = DesktopRollbackRequest.from_payloads(
                rollback_payload,
                update_receipt,
                approved_rollback_plan_sha256=args.approve_rollback_plan_sha,
                approved_active_grant_sha256=args.approve_active_grant_sha,
                approved_target_grant_sha256=args.approve_target_grant_sha,
                approved_rollback_permissions=tuple(args.rollback_permissions),
            )
            rollback_result = DesktopRollbackService().execute(
                rollback_request,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(rollback_result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-retained-cleanup":
        try:
            cleanup_plan = plan_retained_cleanup(
                args.retention_marker_path,
                scope=args.scope,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(cleanup_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-retained-cleanup":
        try:
            cleanup_payload = _load_json_file(args.retained_cleanup_plan_json)
            cleanup_review = review_retained_cleanup(cleanup_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(cleanup_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-retained-cleanup":
        try:
            cleanup_payload = _load_json_file(args.retained_cleanup_plan_json)
            cleanup_request = RetainedCleanupRequest.from_payload(
                cleanup_payload,
                approved_cleanup_plan_sha256=args.approve_cleanup_plan_sha,
                approved_retained_grant_sha256=args.approve_retained_grant_sha,
                approved_active_grant_sha256=args.approve_active_grant_sha,
                approved_retention_marker_sha256=args.approve_retention_marker_sha,
                approved_cleanup_permissions=tuple(args.cleanup_permissions),
            )
            cleanup_result = RetainedCleanupService().execute(
                cleanup_request,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(cleanup_result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "observe-lifecycle-gate":
        try:
            gate_observation = observe_lifecycle_gate(
                args.receipt_root,
                app_id=args.app_id,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(gate_observation.to_dict(), sort_keys=True, indent=2))
        return 0 if gate_observation.clear else 1

    if args.command == "observe-cleanup-reconciliation":
        try:
            journal_payload = _load_json_file(args.cleanup_journal_json)
            cleanup_payload = _load_json_file(args.retained_cleanup_plan_json)
            observation = observe_cleanup_reconciliation(
                journal_payload,
                cleanup_payload,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(observation.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-cleanup-reconciliation":
        try:
            journal_payload = _load_json_file(args.cleanup_journal_json)
            cleanup_payload = _load_json_file(args.retained_cleanup_plan_json)
            reconciliation_plan = plan_cleanup_reconciliation(
                journal_payload,
                cleanup_payload,
                action=args.action,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(reconciliation_plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-cleanup-reconciliation":
        try:
            reconciliation_payload = _load_json_file(
                args.cleanup_reconciliation_plan_json
            )
            reconciliation_review = review_cleanup_reconciliation(
                reconciliation_payload
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(reconciliation_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-cleanup-reconciliation":
        try:
            reconciliation_payload = _load_json_file(
                args.cleanup_reconciliation_plan_json
            )
            journal_payload = _load_json_file(args.cleanup_journal_json)
            cleanup_payload = _load_json_file(args.retained_cleanup_plan_json)
            reconciliation_request = CleanupReconciliationRequest.from_payloads(
                reconciliation_payload,
                journal_payload,
                cleanup_payload,
                approved_reconciliation_plan_sha256=(
                    args.approve_reconciliation_plan_sha
                ),
                approved_observation_sha256=args.approve_observation_sha,
                approved_journal_sha256=args.approve_journal_sha,
                approved_cleanup_plan_sha256=args.approve_cleanup_plan_sha,
                approved_reconciliation_permissions=tuple(
                    args.reconciliation_permissions
                ),
            )
            reconciliation_result = CleanupReconciliationService().execute(
                reconciliation_request,
                install_root=args.install_root,
                desktop_root=args.desktop_root,
                applications_root=args.applications_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(reconciliation_result.to_dict(), sort_keys=True, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
