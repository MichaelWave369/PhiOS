from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.apps.build_execution import BuildArtifact, BuildExecutionReceipt
from phios.apps.manifest import AppManifest
from phios.apps.npm_offline import NpmOfflineBuildReceipt
from phios.apps.package_install import (
    BuildPackagePlan,
    SuccessfulBuildBinding,
    plan_build_package,
    review_build_package,
)
from phios.apps.registry import AppRegistry


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.release.example",
            "name": "Release Example",
            "version": "2.0.0",
            "description": "v0.49 lineage fixture",
            "source": {
                "repository_url": "https://github.com/example/release-example",
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
    artifact_path = dist / "index.html"
    artifact_path.write_text("<html>release</html>", encoding="utf-8")
    artifact = BuildArtifact(
        path="dist/index.html",
        byte_count=artifact_path.stat().st_size,
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    artifacts = (artifact,)
    return BuildExecutionReceipt(
        execution_id="11111111-1111-1111-1111-111111111111",
        timestamp_utc="2026-09-21T02:30:00+00:00",
        app_id="phi.release.example",
        repository_url="https://github.com/example/release-example",
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
        timestamp_utc="2026-09-21T02:31:00+00:00",
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


def _canonical_sha(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_v049_execution_receipt_digest_binds_exact_release_review(tmp_path: Path) -> None:
    first = _execution(tmp_path / "first", release_build_review_sha256="4" * 64)
    second = _execution(tmp_path / "second", release_build_review_sha256="5" * 64)

    assert first.release_build_review_sha256 == "4" * 64
    assert first.to_dict()["release_build_review_sha256"] == "4" * 64
    assert first.sha256() != second.sha256()


def test_v049_ordinary_execution_receipt_has_explicit_null_lineage(tmp_path: Path) -> None:
    execution = _execution(tmp_path, release_build_review_sha256=None)

    assert execution.release_build_review_sha256 is None
    assert execution.to_dict()["release_build_review_sha256"] is None


def test_v049_package_plan_and_review_preserve_release_lineage(tmp_path: Path) -> None:
    manifest, registry = _registry()
    execution = _execution(tmp_path, release_build_review_sha256="4" * 64)
    offline = _offline(execution)

    plan = plan_build_package(
        manifest.to_dict(),
        registry,
        execution.to_dict(),
        offline.to_dict(),
    )
    review = review_build_package(plan.to_dict())

    assert plan.release_build_review_sha256 == "4" * 64
    assert review.release_build_review_sha256 == "4" * 64
    assert BuildPackagePlan.from_dict(plan.to_dict()) == plan
    assert plan.launch_authority is False
    assert review.launch_authority is False


def test_v049_successful_build_binding_rejects_malformed_release_review_digest(
    tmp_path: Path,
) -> None:
    execution = _execution(tmp_path, release_build_review_sha256="4" * 64)
    offline = _offline(execution)
    payload = execution.to_dict()
    payload["release_build_review_sha256"] = "not-a-digest"
    body = dict(payload)
    body.pop("receipt_sha256")
    payload["receipt_sha256"] = _canonical_sha(body)

    with pytest.raises(ValueError, match="release_build_review_sha256"):
        SuccessfulBuildBinding.from_payloads(payload, offline.to_dict())


def test_v049_package_plan_digest_changes_with_release_lineage(tmp_path: Path) -> None:
    manifest, registry = _registry()
    release_execution = _execution(
        tmp_path / "release",
        release_build_review_sha256="4" * 64,
    )
    ordinary_execution = _execution(
        tmp_path / "ordinary",
        release_build_review_sha256=None,
    )
    release_plan = plan_build_package(
        manifest.to_dict(),
        registry,
        release_execution.to_dict(),
        _offline(release_execution).to_dict(),
    )
    ordinary_plan = plan_build_package(
        manifest.to_dict(),
        registry,
        ordinary_execution.to_dict(),
        _offline(ordinary_execution).to_dict(),
    )

    assert release_plan.release_build_review_sha256 == "4" * 64
    assert ordinary_plan.release_build_review_sha256 is None
    assert release_plan.sha256() != ordinary_plan.sha256()


def test_v049_legacy_v01_execution_receipt_remains_package_readable(
    tmp_path: Path,
) -> None:
    manifest, registry = _registry()
    current = _execution(tmp_path, release_build_review_sha256=None)
    legacy_execution = current.to_dict()
    legacy_execution.pop("release_build_review_sha256")
    legacy_execution["schema_version"] = "phios.build_execution_receipt.v0.1"
    legacy_body = dict(legacy_execution)
    legacy_body.pop("receipt_sha256")
    legacy_execution["receipt_sha256"] = _canonical_sha(legacy_body)

    offline = _offline(current).to_dict()
    offline["build_execution_receipt_sha256"] = legacy_execution["receipt_sha256"]
    offline_body = dict(offline)
    offline_body.pop("npm_offline_build_receipt_sha256")
    offline["npm_offline_build_receipt_sha256"] = _canonical_sha(offline_body)

    plan = plan_build_package(
        manifest.to_dict(),
        registry,
        legacy_execution,
        offline,
    )

    assert plan.release_build_review_sha256 is None
    assert plan.schema_version == "phios.build_package_plan.v0.2"


def test_v049_legacy_v01_package_plan_round_trip_remains_supported(
    tmp_path: Path,
) -> None:
    manifest, registry = _registry()
    execution = _execution(tmp_path, release_build_review_sha256=None)
    current = plan_build_package(
        manifest.to_dict(),
        registry,
        execution.to_dict(),
        _offline(execution).to_dict(),
    )
    legacy = current.to_dict()
    legacy.pop("release_build_review_sha256")
    legacy["schema_version"] = "phios.build_package_plan.v0.1"
    legacy_body = dict(legacy)
    legacy_body.pop("package_plan_sha256")
    legacy["package_plan_sha256"] = _canonical_sha(legacy_body)

    restored = BuildPackagePlan.from_dict(legacy)

    assert restored.schema_version == "phios.build_package_plan.v0.1"
    assert restored.release_build_review_sha256 is None
    assert restored.to_dict() == legacy
