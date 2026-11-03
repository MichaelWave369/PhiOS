"""Synthetic PhiOS-format receipt tests for the ThinkTank v0.65 review gate.

These receipts are created in tests, not by a qualified real ThinkTank builder.
A successful test only proves the gate's canonical matching and refusal rules.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from phios.apps.build_execution import BuildArtifact, BuildExecutionReceipt
from phios.apps.manifest import AppManifest
from phios.apps.npm_offline import NpmOfflineBuildReceipt
from phios.apps.package_install import PackageArtifact
from scripts import thinktank_package_plan_gate as gate
from scripts.thinktank_guest_acceptance import reviewed_candidate
from scripts.thinktank_web_pilot import verify_dist


def fixture(tmp_path: Path):
    candidate = reviewed_candidate()
    manifest = AppManifest.from_dict(candidate["manifest"])
    workspace = tmp_path / "execution" / "source"
    dist = workspace / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><script type="module" src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text(
        'document.body.textContent="Phi ThinkTank"', encoding="utf-8",
    )

    artifacts = tuple(
        PackageArtifact(
            path=p.relative_to(workspace).as_posix(),
            byte_count=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in sorted(dist.rglob("*")) if p.is_file()
    )
    package_sha = hashlib.sha256(
        b"".join(a.canonical_line() for a in artifacts)
    ).hexdigest()
    source_sha = candidate["source_sha"]
    execution = BuildExecutionReceipt(
        execution_id=str(uuid.uuid4()),
        timestamp_utc="2026-11-02T00:00:00+00:00",
        app_id=manifest.app_id,
        repository_url=manifest.source.repository_url,
        commit_sha=source_sha,
        plan_sha256="b" * 64,
        source_snapshot_sha256="c" * 64,
        acquisition_tree_sha256="d" * 64,
        approved_permissions=("build.process.execute", "build.workspace.write"),
        isolation_mode="bubblewrap_linux_namespaces",
        network_sandbox_enforced=True,
        source_workspace_path=str((tmp_path / "source").resolve()),
        execution_workspace_path=str(workspace.resolve()),
        tool_identities=(), steps=(),
        artifacts=tuple(BuildArtifact(
            path=a.path, byte_count=a.byte_count, sha256=a.sha256
        ) for a in artifacts),
        artifact_set_sha256=package_sha,
        status="success",
        failure_reason=None,
    ).to_dict()
    offline = NpmOfflineBuildReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-11-02T00:01:00+00:00",
        app_id=manifest.app_id,
        commit_sha=source_sha,
        npm_offline_plan_sha256="e" * 64,
        original_build_plan_sha256="f" * 64,
        derived_build_plan_sha256="b" * 64,
        npm_cache_receipt_sha256="1" * 64,
        cache_tree_sha256="2" * 64,
        cache_mount_target="/phios/npm-cache",
        build_execution_receipt_sha256=execution["receipt_sha256"],
        sandbox_receipt_sha256="3" * 64,
        network_mode="deny", network_namespace_enforced=True,
        build_status="success",
    ).to_dict()
    static = verify_dist(dist)
    handoff = {
        "schema_version": gate.HANDOFF_SCHEMA,
        "app_id": manifest.app_id,
        "source_repo": manifest.source.repository_url,
        "source_sha": source_sha,
        "candidate_manifest_sha256": manifest.sha256(),
        "committed_lock_sha256": "9" * 64,
        "verified_static_bundle_sha256": static["artifact_set_sha256"],
        "package_artifact_set_sha256": package_sha,
        "package_artifact_count": len(artifacts),
        "package_total_bytes": sum(a.byte_count for a in artifacts),
        "package_artifacts": [a.to_dict() for a in artifacts],
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
    return handoff, execution, offline, workspace


def test_actual_package_planner_creates_review_only_plan_for_matching_receipts(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    result = gate.review(handoff, execution, offline)
    assert result["status"] == "CANONICAL_PHIOS_PACKAGE_PLAN_REVIEW_ONLY"
    assert result["package_plan"]["artifact_set_sha256"] == handoff["package_artifact_set_sha256"]
    assert result["package_review"]["artifact_count"] == handoff["package_artifact_count"]
    assert result["package_plan"]["commit_sha"] == handoff["source_sha"]
    assert result["package_plan"]["release_build_review_sha256"] is None
    assert result["package_plan"]["launch_authority"] is False
    for field in ("operator_package_approval_present", "app_installed",
                  "desktop_launch_authorized", "release_authorized",
                  "production_qualified", "receipt_producer_independently_attested"):
        assert result[field] is False


def test_missing_governed_receipts_cannot_use_hosted_pilot_instead(tmp_path):
    handoff, _, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError):
        gate.review(handoff, {"schema_version": "phios.thinktank_web_hosted_pilot.v0.2"},
                    {"schema_version": "phios.thinktank_preinstall_handoff.v0.1"})


def test_tampered_output_bytes_are_rejected(tmp_path):
    handoff, execution, offline, workspace = fixture(tmp_path)
    (workspace / "dist/assets/app.js").write_text("tampered output")
    with pytest.raises(ValueError, match="WORKSPACE_STATIC_BUNDLE_DRIFT|WORKSPACE_BYTES_DRIFT"):
        gate.review(handoff, execution, offline)


def test_extra_unreceipted_file_is_rejected(tmp_path):
    handoff, execution, offline, workspace = fixture(tmp_path)
    (workspace / "dist/hidden.js").write_text("not receipted")
    with pytest.raises(ValueError, match="WORKSPACE_FILE_SET_DRIFT"):
        gate.review(handoff, execution, offline)


def test_symlinked_artifact_refused(tmp_path):
    handoff, execution, offline, workspace = fixture(tmp_path)
    original = workspace / "dist/assets/app.js"
    target = workspace / "other.js"
    original.rename(target)
    original.symlink_to(target)
    with pytest.raises(ValueError, match="WORKSPACE_SYMLINK"):
        gate.review(handoff, execution, offline)


@pytest.mark.parametrize("field", [
    "phios_app_installed", "phios_desktop_launch_granted",
    "license_redistribution_cleared", "production_qualified",
    "build_execution_receipt_present",
])
def test_handoff_authority_promotion_refused(tmp_path, field):
    handoff, execution, offline, _ = fixture(tmp_path)
    handoff[field] = True
    with pytest.raises(ValueError, match="UNREVIEWED_HANDOFF_OR_CANDIDATE"):
        gate.review(handoff, execution, offline)


def test_source_commit_mismatch_refused(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    handoff["source_sha"] = "f" * 40
    with pytest.raises(ValueError, match="UNREVIEWED_HANDOFF_OR_CANDIDATE"):
        gate.review(handoff, execution, offline)


def test_handoff_digest_mismatch_refused(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    handoff["package_artifact_set_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="HANDOFF_ARTIFACT_DIGEST_MISMATCH"):
        gate.review(handoff, execution, offline)


def test_handoff_static_digest_mismatch_refused(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    handoff["verified_static_bundle_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="WORKSPACE_STATIC_BUNDLE_DRIFT"):
        gate.review(handoff, execution, offline)


def test_mutated_execution_receipt_digest_refused(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    execution["status"] = "failed"
    with pytest.raises(ValueError):
        gate.review(handoff, execution, offline)


def test_mutated_offline_receipt_digest_refused(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    offline["network_mode"] = "inherit"
    with pytest.raises(ValueError):
        gate.review(handoff, execution, offline)


def test_producer_source_mismatch_even_if_canonical_receipts_regenerated(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    execution["commit_sha"] = "0" * 40
    body = copy.deepcopy(execution)
    body.pop("receipt_sha256")
    execution["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    offline["commit_sha"] = "0" * 40
    offline["build_execution_receipt_sha256"] = execution["receipt_sha256"]
    body = copy.deepcopy(offline)
    body.pop("npm_offline_build_receipt_sha256")
    offline["npm_offline_build_receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="GOVERNED_BUILD_OR_RELEASE_LINEAGE_MISMATCH"):
        gate.review(handoff, execution, offline)


def test_duplicate_json_fields_and_symlink_paths_refused(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="DUPLICATE_JSON_FIELD"):
        gate.load_json(path)
    path.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="NONFINITE"):
        gate.load_json(path)
    path.write_text("{}", encoding="utf-8")
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(ValueError, match="INPUT_NOT_ABSOLUTE_REGULAR_FILE"):
        gate.load_json(alias)


def test_candidate_promotion_is_refused(tmp_path):
    handoff, execution, offline, _ = fixture(tmp_path)
    candidate = reviewed_candidate()
    candidate["review"]["installed"] = True
    with patch.object(gate, "reviewed_candidate", return_value=candidate):
        with pytest.raises(ValueError, match="UNREVIEWED_HANDOFF_OR_CANDIDATE"):
            gate.review(handoff, execution, offline)
