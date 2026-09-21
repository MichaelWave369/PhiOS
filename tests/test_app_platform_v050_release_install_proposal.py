from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.apps.build_execution import BuildArtifact, BuildExecutionReceipt
from phios.apps.manifest import AppManifest
from phios.apps.npm_offline import NpmOfflineBuildReceipt
from phios.apps.package_install import (
    AppInstallReceipt,
    AppInstallService,
    BuildPackagePlan,
    plan_build_package,
)
from phios.apps.registry import AppRegistry
from phios.apps.release_install_proposal import (
    ReleaseInstallProposalRecord,
    propose_release_install,
    validate_release_install_proposal,
)


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.release.install",
            "name": "Release Install",
            "version": "2.0.0",
            "description": "v0.50 fixture",
            "source": {
                "repository_url": "https://github.com/example/release-install",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _artifact_set(artifacts: tuple[BuildArtifact, ...]) -> str:
    digest = hashlib.sha256()
    for artifact in artifacts:
        digest.update(artifact.canonical_line())
    return digest.hexdigest()


def _execution(
    tmp_path: Path,
    *,
    release_build_review_sha256: str | None,
) -> BuildExecutionReceipt:
    workspace = tmp_path / "execution" / "source"
    dist = workspace / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / "index.html"
    target.write_text("<html>v0.50</html>", encoding="utf-8")
    artifact = BuildArtifact(
        path="dist/index.html",
        byte_count=target.stat().st_size,
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    artifacts = (artifact,)
    return BuildExecutionReceipt(
        execution_id="11111111-1111-1111-1111-111111111111",
        timestamp_utc="2026-09-21T03:00:00+00:00",
        app_id="phi.release.install",
        repository_url="https://github.com/example/release-install",
        commit_sha="a" * 40,
        plan_sha256="b" * 64,
        source_snapshot_sha256="c" * 64,
        acquisition_tree_sha256="d" * 64,
        approved_permissions=("build.process.execute", "build.workspace.write"),
        isolation_mode="bubblewrap_linux_namespaces",
        network_sandbox_enforced=True,
        source_workspace_path=str((tmp_path / "source").resolve()),
        execution_workspace_path=str(workspace.resolve()),
        tool_identities=(),
        steps=(),
        artifacts=artifacts,
        artifact_set_sha256=_artifact_set(artifacts),
        status="success",
        failure_reason=None,
        release_build_review_sha256=release_build_review_sha256,
    )


def _offline(execution: BuildExecutionReceipt) -> NpmOfflineBuildReceipt:
    return NpmOfflineBuildReceipt(
        receipt_id="22222222-2222-2222-2222-222222222222",
        timestamp_utc="2026-09-21T03:01:00+00:00",
        app_id=execution.app_id,
        commit_sha=execution.commit_sha,
        npm_offline_plan_sha256="e" * 64,
        original_build_plan_sha256="f" * 64,
        derived_build_plan_sha256=execution.plan_sha256,
        npm_cache_receipt_sha256="1" * 64,
        cache_tree_sha256="2" * 64,
        cache_mount_target="/phios/npm-cache",
        build_execution_receipt_sha256=execution.sha256(),
        sandbox_receipt_sha256="3" * 64,
        network_mode="deny",
        network_namespace_enforced=True,
        build_status="success",
    )


def _registry() -> tuple[AppManifest, AppRegistry]:
    manifest = _manifest()
    registry = AppRegistry()
    registry.register(manifest)
    return manifest, registry


def _package(
    tmp_path: Path,
    *,
    release: bool,
) -> tuple[AppManifest, AppRegistry, BuildExecutionReceipt, NpmOfflineBuildReceipt, BuildPackagePlan]:
    manifest, registry = _registry()
    execution = _execution(
        tmp_path,
        release_build_review_sha256=("4" * 64 if release else None),
    )
    offline = _offline(execution)
    plan = plan_build_package(
        manifest.to_dict(),
        registry,
        execution.to_dict(),
        offline.to_dict(),
    )
    return manifest, registry, execution, offline, plan


def _canonical_sha(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_v050_proposal_binds_exact_release_package_and_grants_no_authority(
    tmp_path: Path,
) -> None:
    _, _, _, _, plan = _package(tmp_path, release=True)

    proposal = propose_release_install(
        plan.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
    )

    assert proposal.package_plan_sha256 == plan.sha256()
    assert proposal.release_build_review_sha256 == "4" * 64
    assert proposal.artifact_set_sha256 == plan.artifact_set_sha256
    assert proposal.proposal_state == "proposed_for_side_by_side_install_review"
    assert proposal.proposal_scope == "release_candidate_install_only"
    assert proposal.compatibility_verdict == "not_assessed"
    assert proposal.install_authority is False
    assert proposal.launch_authority is False
    assert proposal.update_authority is False
    assert proposal.rollback_authority is False
    assert ReleaseInstallProposalRecord.from_dict(proposal.to_dict()) == proposal


def test_v050_proposal_requires_exact_package_plan_approval(tmp_path: Path) -> None:
    _, _, _, _, plan = _package(tmp_path, release=True)

    with pytest.raises(ValueError, match="approved package-plan digest"):
        propose_release_install(
            plan.to_dict(),
            approved_package_plan_sha256="0" * 64,
        )


def test_v050_ordinary_package_cannot_mint_release_install_proposal(
    tmp_path: Path,
) -> None:
    _, _, _, _, plan = _package(tmp_path, release=False)

    with pytest.raises(ValueError, match="release-lineage package plan"):
        propose_release_install(
            plan.to_dict(),
            approved_package_plan_sha256=plan.sha256(),
        )


def test_v050_tampered_proposal_is_rejected(tmp_path: Path) -> None:
    _, _, _, _, plan = _package(tmp_path, release=True)
    proposal = propose_release_install(
        plan.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
    )
    payload = proposal.to_dict()
    payload["install_authority"] = True

    with pytest.raises(ValueError):
        ReleaseInstallProposalRecord.from_dict(payload)


def test_v050_release_install_is_blocked_without_proposal(tmp_path: Path) -> None:
    _, registry, execution, offline, plan = _package(tmp_path, release=True)

    with pytest.raises(ValueError, match="requires v0.50 proposal"):
        AppInstallService().install(
            plan.to_dict(),
            registry,
            execution.to_dict(),
            offline.to_dict(),
            approved_package_plan_sha256=plan.sha256(),
            install_root=tmp_path / "apps",
        )


def test_v050_exact_proposal_allows_side_by_side_install_and_is_receipted(
    tmp_path: Path,
) -> None:
    _, registry, execution, offline, plan = _package(tmp_path, release=True)
    proposal = propose_release_install(
        plan.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
    )

    receipt = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution.to_dict(),
        offline.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
        release_install_proposal_value=proposal.to_dict(),
        approved_release_install_proposal_sha256=proposal.sha256(),
    )

    assert receipt.status == "installed"
    assert receipt.launch_authority is False
    assert receipt.release_install_proposal_sha256 == proposal.sha256()
    assert receipt.schema_version == "phios.app_install_receipt.v0.2"
    assert AppInstallReceipt.from_dict(receipt.to_dict()) == receipt


def test_v050_stale_proposal_approval_blocks_install(tmp_path: Path) -> None:
    _, registry, execution, offline, plan = _package(tmp_path, release=True)
    proposal = propose_release_install(
        plan.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
    )

    with pytest.raises(ValueError, match="approved release install proposal digest"):
        AppInstallService().install(
            plan.to_dict(),
            registry,
            execution.to_dict(),
            offline.to_dict(),
            approved_package_plan_sha256=plan.sha256(),
            install_root=tmp_path / "apps",
            release_install_proposal_value=proposal.to_dict(),
            approved_release_install_proposal_sha256="0" * 64,
        )


def test_v050_proposal_for_other_package_cannot_authorize_install(tmp_path: Path) -> None:
    _, _, _, _, original = _package(tmp_path / "original", release=True)
    proposal = propose_release_install(
        original.to_dict(),
        approved_package_plan_sha256=original.sha256(),
    )
    changed = BuildPackagePlan(
        app_id=original.app_id,
        app_version="2.0.1",
        manifest_sha256=original.manifest_sha256,
        registry_snapshot_sha256=original.registry_snapshot_sha256,
        repository_url=original.repository_url,
        commit_sha=original.commit_sha,
        build_plan_sha256=original.build_plan_sha256,
        execution_receipt_sha256=original.execution_receipt_sha256,
        offline_build_receipt_sha256=original.offline_build_receipt_sha256,
        artifact_set_sha256=original.artifact_set_sha256,
        artifacts=original.artifacts,
        install_relative_path=original.install_relative_path.replace(
            "/2.0.0/",
            "/2.0.1/",
        ),
        release_build_review_sha256=original.release_build_review_sha256,
        launch_authority=False,
    )

    with pytest.raises(ValueError, match="package_plan_sha256"):
        validate_release_install_proposal(
            changed,
            proposal.to_dict(),
            approved_release_install_proposal_sha256=proposal.sha256(),
        )


def test_v050_ordinary_install_remains_unchanged(tmp_path: Path) -> None:
    _, registry, execution, offline, plan = _package(tmp_path, release=False)

    receipt = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution.to_dict(),
        offline.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )

    assert receipt.release_install_proposal_sha256 is None
    assert receipt.launch_authority is False


def test_v050_ordinary_install_rejects_irrelevant_release_proposal_inputs(
    tmp_path: Path,
) -> None:
    _, registry, execution, offline, ordinary = _package(
        tmp_path / "ordinary",
        release=False,
    )
    _, _, _, _, release = _package(tmp_path / "release", release=True)
    proposal = propose_release_install(
        release.to_dict(),
        approved_package_plan_sha256=release.sha256(),
    )

    with pytest.raises(ValueError, match="valid only for a release-lineage package"):
        AppInstallService().install(
            ordinary.to_dict(),
            registry,
            execution.to_dict(),
            offline.to_dict(),
            approved_package_plan_sha256=ordinary.sha256(),
            install_root=tmp_path / "apps",
            release_install_proposal_value=proposal.to_dict(),
            approved_release_install_proposal_sha256=proposal.sha256(),
        )


def test_v050_legacy_v01_install_receipt_round_trip_remains_supported(
    tmp_path: Path,
) -> None:
    _, registry, execution, offline, plan = _package(tmp_path, release=False)
    current = AppInstallService().install(
        plan.to_dict(),
        registry,
        execution.to_dict(),
        offline.to_dict(),
        approved_package_plan_sha256=plan.sha256(),
        install_root=tmp_path / "apps",
    )
    legacy = current.to_dict()
    legacy.pop("release_install_proposal_sha256")
    legacy["schema_version"] = "phios.app_install_receipt.v0.1"
    body = dict(legacy)
    body.pop("install_receipt_sha256")
    legacy["install_receipt_sha256"] = _canonical_sha(body)

    restored = AppInstallReceipt.from_dict(legacy)

    assert restored.schema_version == "phios.app_install_receipt.v0.1"
    assert restored.release_install_proposal_sha256 is None
    assert restored.to_dict() == legacy
