"""Synthetic refusal tests for real-asset ThinkTank package inventory handoff.

Actual ThinkTank npm build and Chrome execution belong to the hosted pilot job.
These tests make no production authorization and never call an installer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from phios.apps.package_install import PackageArtifact
from scripts import thinktank_preinstall_handoff as gate
from scripts.thinktank_web_pilot import verify_dist

SOURCE_SHA = "a" * 40
LOCK_SHA = "b" * 64

def _fixture(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package-lock.json").write_text("not consulted by mocked lock adapter")
    dist = tmp_path / "build" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><script type="module" src="/assets/app.js"></script></html>'
    )
    (dist / "assets/app.js").write_text('document.body.append("ThinkTank")')
    manifest = {
        "schema_version": "phios.app_manifest.v0.1",
        "app_id": "phios.thinktank-web",
        "name": "Phi ThinkTank",
        "version": "0.1.0",
        "description": "Test-only candidate: not installed",
        "source": {
            "repository_url": "https://github.com/MichaelWave369/think-tank",
            "license_expression": "MIT",
            "redistribution": "unknown",
        },
        "entrypoint": {"runtime": "static_web", "target": "index.html"},
        "permissions": [],
    }
    from phios.apps.manifest import AppManifest
    manifest_sha = AppManifest.from_dict(manifest).sha256()
    candidate = {
        "source_sha": SOURCE_SHA, "manifest": manifest,
        "review": {
            "state": "HELD_FOR_OPERATOR_REVIEW", "installed": False,
            "execution_authorized": False,
            "desktop_launch_grant_verified": False, "external_done": False,
        },
    }
    receipt = {
        "schema_version": gate.HOSTED_SCHEMA,
        "app_id": "phios.thinktank-web",
        "source_repo": manifest["source"]["repository_url"],
        "source_sha": SOURCE_SHA,
        "candidate_manifest_sha256": manifest_sha,
        "observed_committed_package_lock_sha256": LOCK_SHA,
        "locked_dependency_count": 72,
        "dependency_lock_provenance": "UPSTREAM_GIT_COMMITTED_AND_SOURCE_SHA_BOUND",
        "source_review_status": "HELD_FOR_OPERATOR_REVIEW",
        "browser_render_result": "PASS_HOSTED_LOOPBACK_CHROMIUM",
        "hosted_offline_build_scope": "DOCKER_NETWORK_NONE_WITH_PRESTAGED_NPM_CACHE",
        "hosted_locked_npm_ci": True,
        "hosted_offline_cached_build_observed": True,
        "static_bundle": verify_dist(dist),
    }
    for name in (
        "dependency_reproducibility_verified", "offline_dependency_closure_verified",
        "asset_redistribution_reviewed", "browser_network_isolation_verified",
        "provider_bridge_started", "phios_registry_enrolled", "phios_app_installed",
        "phios_desktop_launch_granted", "phios_vm_boot_verified",
        "phios_rollback_verified", "production_qualified",
    ):
        receipt[name] = False
    path = tmp_path / "hosted.json"
    path.write_text(json.dumps(receipt))
    return source, dist, path, candidate, receipt

def _inspect(source, dist, path, candidate):
    with (
        patch.object(gate, "reviewed_candidate", return_value=candidate),
        patch.object(gate, "verify_committed_lock",
                     return_value={"sha256": LOCK_SHA, "package_count": 72}),
        patch.object(gate.subprocess, "check_output", return_value=SOURCE_SHA + "\n"),
    ):
        return gate.inventory(
            source=source, dist=dist, committed_lock=source / "package-lock.json",
            hosted_receipt=path,
        )

def test_verified_real_files_use_existing_package_artifact_canonical_lines(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    record = _inspect(source, dist, path, candidate)
    artifacts = tuple(PackageArtifact.from_dict(x) for x in record["package_artifacts"])
    digest = hashlib.sha256(
        b"".join(x.canonical_line() for x in artifacts)
    ).hexdigest()
    assert record["package_artifact_set_sha256"] == digest
    assert {x.path for x in artifacts} == {"dist/index.html", "dist/assets/app.js"}
    assert record["package_artifact_count"] == 2
    assert record["status"] == "REVIEW_ONLY_VERIFIED_DIST_NOT_INSTALL_APPROVAL"
    assert record["candidate_still_held"] is True
    for key in (
        "phios_app_installed", "build_execution_receipt_present",
        "npm_offline_build_receipt_present", "phios_desktop_launch_granted",
        "phios_guest_lifecycle_verified", "license_redistribution_cleared",
        "production_qualified",
    ):
        assert record[key] is False

def test_changed_static_assets_block_handoff(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    (dist / "assets" / "app.js").write_text("tampered")
    with pytest.raises(ValueError, match="HOSTED_DIST_CHANGED"):
        _inspect(source, dist, path, candidate)

def test_missing_static_asset_blocks_handoff(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    (dist / "assets" / "app.js").unlink()
    with pytest.raises(ValueError, match="missing or escaping"):
        _inspect(source, dist, path, candidate)

def test_source_pin_drift_blocks_handoff(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    candidate["source_sha"] = "e" * 40
    with pytest.raises(ValueError, match="SOURCE_PIN_DRIFT"):
        _inspect(source, dist, path, candidate)

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha", "e" * 40),
        ("observed_committed_package_lock_sha256", "f" * 64),
        ("browser_render_result", "FAIL"),
        ("candidate_manifest_sha256", "a" * 64),
        ("source_review_status", "RELEASED"),
    ],
)
def test_mismatched_hosted_evidence_refused(tmp_path: Path, field: str, value: str):
    source, dist, path, candidate, receipt = _fixture(tmp_path)
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="HOSTED_SOURCE_LOCK_OR_RENDER_MISMATCH"):
        _inspect(source, dist, path, candidate)

@pytest.mark.parametrize(
    "field",
    [
        "phios_app_installed", "phios_desktop_launch_granted", "production_qualified",
        "provider_bridge_started", "asset_redistribution_reviewed",
        "offline_dependency_closure_verified",
    ],
)
def test_hosted_receipt_cannot_smuggle_authority(tmp_path: Path, field: str):
    source, dist, path, candidate, receipt = _fixture(tmp_path)
    receipt[field] = True
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="HOSTED_AUTHORITY_SMUGGLING"):
        _inspect(source, dist, path, candidate)

def test_candidate_promotion_refused(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    candidate["review"]["installed"] = True
    with pytest.raises(ValueError, match="CANDIDATE_AUTHORITY_CHANGED"):
        _inspect(source, dist, path, candidate)

def test_hosted_receipt_symlink_refused(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(ValueError, match="UNSAFE_RECEIPT"):
        _inspect(source, dist, alias, candidate)

def test_dist_symlink_refused(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(dist)
    with pytest.raises(ValueError, match="UNSAFE_DIST_ROOT"):
        _inspect(source, alias, path, candidate)

def test_hosted_receipt_has_to_be_an_object(tmp_path: Path):
    source, dist, path, candidate, _ = _fixture(tmp_path)
    path.write_text("[]")
    with pytest.raises(ValueError, match="NOT_JSON_OBJECT"):
        _inspect(source, dist, path, candidate)
