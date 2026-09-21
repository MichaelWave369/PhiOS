from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from phios.apps.build_plan import plan_build_from_payloads
from phios.apps.intake import AppIntakeEvidence, AppIntakeProposal, AppIntakeResult
from phios.apps.manifest import AppManifest
from phios.apps.release_advancement import (
    ReleaseCandidateAdvancementRecord,
    advance_release_candidate,
    validate_release_candidate_advancement,
)
from phios.apps.release_compatibility import ReleaseChangeEvidence
from phios.apps.release_discovery import (
    ReleaseCandidateIntake,
    ReleaseCandidateSelection,
)
from phios.apps.release_review import accept_release_change_evidence


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "github.michaelwave369.browsallax",
            "name": "Browsallax",
            "version": "2.0.0",
            "description": "Local-first browser",
            "source": {
                "repository_url": "https://github.com/MichaelWave369/Browsallax",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {
                "runtime": "static_web",
                "target": "index.html",
            },
            "permissions": [],
        }
    )


def _candidate() -> ReleaseCandidateIntake:
    manifest = _manifest()
    commit_sha = "b" * 40
    repository_url = "https://github.com/MichaelWave369/Browsallax"
    selection = ReleaseCandidateSelection(
        release_discovery_sha256="1" * 64,
        app_id=manifest.app_id,
        installed_version="1.0.0",
        repository_url=repository_url,
        release_id=200,
        tag_name="v2.0.0",
        commit_sha=commit_sha,
        prerelease=False,
    )
    evidence = AppIntakeEvidence(
        repository_url=repository_url,
        owner="MichaelWave369",
        name="Browsallax",
        description="Local-first browser",
        default_branch="main",
        head_sha=commit_sha,
        archived=False,
        disabled=False,
        license_spdx="MIT",
        root_paths=("index.html",),
        inspected_files=(
            {
                "path": "index.html",
                "sha256": hashlib.sha256(b"<html>phi</html>").hexdigest(),
                "byte_count": len(b"<html>phi</html>"),
            },
        ),
        provider_request_count=4,
    )
    proposal = AppIntakeProposal(
        repository_url=repository_url,
        status="declared_manifest",
        app_id=manifest.app_id,
        runtime=manifest.entrypoint.runtime,
        target=manifest.entrypoint.target,
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        license_expression=manifest.source.license_expression,
        redistribution=manifest.source.redistribution,
        permissions=manifest.permissions,
        permissions_source="phios-app.json",
        basis=("exact commit candidate",),
    )
    return ReleaseCandidateIntake(
        selection=selection,
        intake=AppIntakeResult(
            evidence=evidence,
            proposal=proposal,
            manifest_candidate=manifest,
        ),
    )


def _change_evidence(candidate: ReleaseCandidateIntake) -> ReleaseChangeEvidence:
    manifest = _manifest()
    return ReleaseChangeEvidence(
        app_id=manifest.app_id,
        repository_url=manifest.source.repository_url,
        active_version="1.0.0",
        candidate_version=manifest.version,
        active_commit_sha="a" * 40,
        candidate_commit_sha="b" * 40,
        active_manifest_sha256="2" * 64,
        candidate_manifest_sha256=manifest.sha256(),
        release_candidate_intake_sha256=candidate.sha256(),
        active_bundle_path="/tmp/phios/desktop/browsallax/active",
        active_grant_sha256="3" * 64,
        manifest_changes=("version_changed",),
        permissions_added=(),
        permissions_removed=(),
        source_marker_changes=(),
        provider_request_count=2,
    )


def _acceptance(evidence: ReleaseChangeEvidence):
    return accept_release_change_evidence(
        evidence.to_dict(),
        approved_release_change_evidence_sha256=evidence.sha256(),
        acknowledged_manifest_changes=("version_changed",),
    )


def _chain():
    candidate = _candidate()
    evidence = _change_evidence(candidate)
    acceptance = _acceptance(evidence)
    advancement = advance_release_candidate(
        candidate.to_dict(),
        evidence.to_dict(),
        acceptance.to_dict(),
        approved_release_change_acceptance_sha256=acceptance.sha256(),
    )
    return candidate, evidence, acceptance, advancement


def _receipt(root: Path) -> dict[str, object]:
    manifest = _manifest()
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-09-21T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": manifest.source.repository_url,
        "commit_sha": "b" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "4" * 64,
        "tree_sha256": "5" * 64,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def test_exact_review_chain_creates_non_authoritative_advancement() -> None:
    candidate, evidence, acceptance, advancement = _chain()

    assert advancement.release_candidate_intake_sha256 == candidate.sha256()
    assert advancement.release_change_evidence_sha256 == evidence.sha256()
    assert advancement.release_change_acceptance_sha256 == acceptance.sha256()
    assert advancement.advancement_state == "human_review_prerequisite_satisfied"
    assert advancement.advancement_scope == "build_planning_only"
    assert advancement.compatibility_verdict == "not_assessed"
    assert advancement.acquisition_authority is False
    assert advancement.build_execution_authority is False
    assert advancement.install_authority is False
    assert advancement.update_authority is False


def test_advancement_requires_exact_operator_approved_acceptance() -> None:
    candidate = _candidate()
    evidence = _change_evidence(candidate)
    acceptance = _acceptance(evidence)

    with pytest.raises(ValueError, match="approved release change acceptance digest"):
        advance_release_candidate(
            candidate.to_dict(),
            evidence.to_dict(),
            acceptance.to_dict(),
            approved_release_change_acceptance_sha256="0" * 64,
        )


def test_advancement_rejects_cross_candidate_evidence() -> None:
    candidate = _candidate()
    evidence = _change_evidence(candidate)
    mismatched = ReleaseChangeEvidence(
        app_id=evidence.app_id,
        repository_url=evidence.repository_url,
        active_version=evidence.active_version,
        candidate_version=evidence.candidate_version,
        active_commit_sha=evidence.active_commit_sha,
        candidate_commit_sha="c" * 40,
        active_manifest_sha256=evidence.active_manifest_sha256,
        candidate_manifest_sha256=evidence.candidate_manifest_sha256,
        release_candidate_intake_sha256=evidence.release_candidate_intake_sha256,
        active_bundle_path=evidence.active_bundle_path,
        active_grant_sha256=evidence.active_grant_sha256,
        manifest_changes=evidence.manifest_changes,
        permissions_added=evidence.permissions_added,
        permissions_removed=evidence.permissions_removed,
        source_marker_changes=evidence.source_marker_changes,
        provider_request_count=evidence.provider_request_count,
    )
    acceptance = _acceptance(mismatched)

    with pytest.raises(ValueError, match="candidate commit"):
        advance_release_candidate(
            candidate.to_dict(),
            mismatched.to_dict(),
            acceptance.to_dict(),
            approved_release_change_acceptance_sha256=acceptance.sha256(),
        )


def test_advancement_record_round_trip_and_tamper_detection() -> None:
    _candidate_value, _evidence_value, _acceptance_value, advancement = _chain()
    payload = advancement.to_dict()

    assert ReleaseCandidateAdvancementRecord.from_dict(payload) == advancement

    payload["advancement_scope"] = "install_now"
    with pytest.raises(ValueError):
        ReleaseCandidateAdvancementRecord.from_dict(payload)


def test_validate_advancement_rechecks_full_review_chain() -> None:
    candidate, evidence, acceptance, advancement = _chain()

    validated = validate_release_candidate_advancement(
        candidate.to_dict(),
        evidence.to_dict(),
        acceptance.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )
    assert validated == advancement

    with pytest.raises(ValueError, match="approved release candidate advancement digest"):
        validate_release_candidate_advancement(
            candidate.to_dict(),
            evidence.to_dict(),
            acceptance.to_dict(),
            advancement.to_dict(),
            approved_release_candidate_advancement_sha256="0" * 64,
        )


def test_release_candidate_cannot_plan_build_without_v047_gate(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    (tmp_path / "index.html").write_text("<html>phi</html>", encoding="utf-8")

    with pytest.raises(ValueError, match="release candidate build planning requires"):
        plan_build_from_payloads(
            candidate.to_dict(),
            _receipt(tmp_path),
        )


def test_release_candidate_build_plan_requires_exact_v047_chain(
    tmp_path: Path,
) -> None:
    candidate, evidence, acceptance, advancement = _chain()
    (tmp_path / "index.html").write_text("<html>phi</html>", encoding="utf-8")

    plan = plan_build_from_payloads(
        candidate.to_dict(),
        _receipt(tmp_path),
        release_change_evidence_value=evidence.to_dict(),
        release_change_acceptance_value=acceptance.to_dict(),
        release_candidate_advancement_value=advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )

    assert plan.status == "no_build_required"
    assert plan.commit_sha == "b" * 40
    assert plan.manifest_sha256 == _manifest().sha256()
    assert any(
        f"release_candidate_advancement_sha256={advancement.sha256()}" in note
        for note in plan.notes
    )


def test_release_candidate_build_plan_rejects_wrong_advancement_approval(
    tmp_path: Path,
) -> None:
    candidate, evidence, acceptance, advancement = _chain()
    (tmp_path / "index.html").write_text("<html>phi</html>", encoding="utf-8")

    with pytest.raises(ValueError, match="approved release candidate advancement digest"):
        plan_build_from_payloads(
            candidate.to_dict(),
            _receipt(tmp_path),
            release_change_evidence_value=evidence.to_dict(),
            release_change_acceptance_value=acceptance.to_dict(),
            release_candidate_advancement_value=advancement.to_dict(),
            approved_release_candidate_advancement_sha256="0" * 64,
        )


def test_non_release_build_rejects_release_gate_inputs(tmp_path: Path) -> None:
    manifest = AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.example",
            "name": "Example",
            "version": "1.0.0",
            "description": "Example",
            "source": {
                "repository_url": "https://github.com/example/example",
                "license_expression": "MIT",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": "static_web", "target": "index.html"},
            "permissions": [],
        }
    )
    intake = {
        "evidence": {
            "repository_url": manifest.source.repository_url,
            "head_sha": "d" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": manifest.source.repository_url,
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    receipt = {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "22222222-2222-2222-2222-222222222222",
        "timestamp_utc": "2026-09-21T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": manifest.source.repository_url,
        "commit_sha": "d" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "6" * 64,
        "tree_sha256": "7" * 64,
        "file_count": 1,
        "total_bytes": 1,
        "workspace_path": str(tmp_path.resolve()),
        "status": "acquired",
    }

    with pytest.raises(ValueError, match="valid only for release-candidate intake"):
        plan_build_from_payloads(
            intake,
            receipt,
            release_change_evidence_value={"unexpected": True},
        )
