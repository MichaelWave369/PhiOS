from __future__ import annotations

from pathlib import Path

import pytest

from phios.apps.build_execution import BuildExecutionRequest
from phios.apps.build_plan import BuildPlan
from phios.apps.release_advancement import ReleaseCandidateAdvancementRecord
from phios.apps.release_build_review import (
    ReleaseBuildReviewRecord,
    release_advancement_sha256_from_plan,
    review_release_build_plan,
)


def _advancement() -> ReleaseCandidateAdvancementRecord:
    return ReleaseCandidateAdvancementRecord(
        release_candidate_intake_sha256="1" * 64,
        release_change_evidence_sha256="2" * 64,
        release_change_acceptance_sha256="3" * 64,
        app_id="github.michaelwave369.browsallax",
        repository_url="https://github.com/MichaelWave369/Browsallax",
        active_version="1.0.0",
        candidate_version="2.0.0",
        active_commit_sha="a" * 40,
        candidate_commit_sha="b" * 40,
        candidate_manifest_sha256="4" * 64,
    )


def _plan(
    advancement: ReleaseCandidateAdvancementRecord | None,
    *,
    strategy: str = "static_web_source",
    legacy_note: bool = False,
) -> BuildPlan:
    notes = [
        (
            "source_snapshot_sha256 identifies current file paths and bytes at "
            "planning time"
        ),
        "build steps are declarative argv arrays; v0.28 executes no process",
    ]
    if advancement is not None:
        if legacy_note:
            notes[-1] = (
                "build steps are declarative argv arrays; v0.28 executes no process; "
                f"release_candidate_advancement_sha256={advancement.sha256()}"
            )
        else:
            notes.append(
                f"release_candidate_advancement_sha256={advancement.sha256()}"
            )
    return BuildPlan(
        app_id="github.michaelwave369.browsallax",
        repository_url="https://github.com/MichaelWave369/Browsallax",
        commit_sha="b" * 40,
        manifest_sha256="4" * 64,
        acquisition_tree_sha256="6" * 64,
        source_snapshot_sha256="5" * 64,
        source_file_count=1,
        source_total_bytes=16,
        runtime="static_web",
        strategy=strategy,
        package_manager=None,
        working_directory=".",
        required_tools=(),
        requested_build_permissions=(),
        steps=(),
        expected_outputs=("index.html",),
        observed_files=(),
        status="no_build_required",
        notes=tuple(notes),
    )


def _receipt(tmp_path: Path) -> dict[str, object]:
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-09-21T00:00:00+00:00",
        "app_id": "github.michaelwave369.browsallax",
        "repository_url": "https://github.com/MichaelWave369/Browsallax",
        "commit_sha": "b" * 40,
        "manifest_sha256": "4" * 64,
        "archive_sha256": "7" * 64,
        "tree_sha256": "6" * 64,
        "file_count": 1,
        "total_bytes": 16,
        "workspace_path": str(tmp_path.resolve()),
        "status": "acquired",
    }


def test_release_build_review_binds_exact_advancement_and_plan() -> None:
    advancement = _advancement()
    plan = _plan(advancement)

    review = review_release_build_plan(
        plan.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )

    assert review.release_candidate_advancement_sha256 == advancement.sha256()
    assert review.build_plan_sha256 == plan.sha256()
    assert review.source_snapshot_sha256 == plan.source_snapshot_sha256
    assert review.review_state == "reviewed_for_build_execution_consideration"
    assert review.review_scope == "exact_release_build_plan"
    assert review.compatibility_verdict == "not_assessed"
    assert review.permission_grant_authority is False
    assert review.build_execution_authority is False
    assert review.install_authority is False
    assert review.update_authority is False


def test_v047_legacy_embedded_advancement_note_remains_readable() -> None:
    advancement = _advancement()
    plan = _plan(advancement, legacy_note=True)

    assert release_advancement_sha256_from_plan(plan) == advancement.sha256()

    review = review_release_build_plan(
        plan.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )
    assert review.build_plan_sha256 == plan.sha256()


def test_duplicate_release_advancement_bindings_fail_closed() -> None:
    advancement = _advancement()
    plan = _plan(advancement)
    duplicate = BuildPlan(
        app_id=plan.app_id,
        repository_url=plan.repository_url,
        commit_sha=plan.commit_sha,
        manifest_sha256=plan.manifest_sha256,
        acquisition_tree_sha256=plan.acquisition_tree_sha256,
        source_snapshot_sha256=plan.source_snapshot_sha256,
        source_file_count=plan.source_file_count,
        source_total_bytes=plan.source_total_bytes,
        runtime=plan.runtime,
        strategy=plan.strategy,
        package_manager=plan.package_manager,
        working_directory=plan.working_directory,
        required_tools=plan.required_tools,
        requested_build_permissions=plan.requested_build_permissions,
        steps=plan.steps,
        expected_outputs=plan.expected_outputs,
        observed_files=plan.observed_files,
        status=plan.status,
        notes=plan.notes
        + (f"release_candidate_advancement_sha256={advancement.sha256()}",),
    )

    with pytest.raises(ValueError, match="multiple release advancement bindings"):
        release_advancement_sha256_from_plan(duplicate)


def test_release_build_review_requires_exact_advancement_approval() -> None:
    advancement = _advancement()
    plan = _plan(advancement)

    with pytest.raises(
        ValueError,
        match="approved release candidate advancement digest",
    ):
        review_release_build_plan(
            plan.to_dict(),
            advancement.to_dict(),
            approved_release_candidate_advancement_sha256="0" * 64,
        )


def test_release_build_review_rejects_cross_plan_advancement() -> None:
    advancement = _advancement()
    other = ReleaseCandidateAdvancementRecord(
        release_candidate_intake_sha256=advancement.release_candidate_intake_sha256,
        release_change_evidence_sha256=advancement.release_change_evidence_sha256,
        release_change_acceptance_sha256=advancement.release_change_acceptance_sha256,
        app_id=advancement.app_id,
        repository_url=advancement.repository_url,
        active_version=advancement.active_version,
        candidate_version=advancement.candidate_version,
        active_commit_sha=advancement.active_commit_sha,
        candidate_commit_sha="c" * 40,
        candidate_manifest_sha256=advancement.candidate_manifest_sha256,
    )
    plan = _plan(advancement)

    with pytest.raises(ValueError, match="release advancement binding"):
        review_release_build_plan(
            plan.to_dict(),
            other.to_dict(),
            approved_release_candidate_advancement_sha256=other.sha256(),
        )


def test_release_build_review_round_trip_and_tamper_detection() -> None:
    advancement = _advancement()
    plan = _plan(advancement)
    review = review_release_build_plan(
        plan.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )
    payload = review.to_dict()

    assert ReleaseBuildReviewRecord.from_dict(payload) == review

    payload["build_execution_authority"] = True
    with pytest.raises(ValueError):
        ReleaseBuildReviewRecord.from_dict(payload)


def test_release_lineage_plan_cannot_create_execution_request_without_v048_review(
    tmp_path: Path,
) -> None:
    advancement = _advancement()
    plan = _plan(advancement)

    with pytest.raises(ValueError, match="requires v0.48 review"):
        BuildExecutionRequest.from_payloads(
            plan.to_dict(),
            _receipt(tmp_path),
            approved_plan_sha256=plan.sha256(),
            approved_source_snapshot_sha256=plan.source_snapshot_sha256,
            approved_permissions=(),
        )


def test_exact_v048_review_allows_release_execution_request(
    tmp_path: Path,
) -> None:
    advancement = _advancement()
    plan = _plan(advancement)
    review = review_release_build_plan(
        plan.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )

    request = BuildExecutionRequest.from_payloads(
        plan.to_dict(),
        _receipt(tmp_path),
        approved_plan_sha256=plan.sha256(),
        approved_source_snapshot_sha256=plan.source_snapshot_sha256,
        approved_permissions=(),
        release_build_review_value=review.to_dict(),
        approved_release_build_review_sha256=review.sha256(),
    )

    assert request.plan == plan
    assert request.release_build_review_sha256 == review.sha256()


def test_stale_v048_review_approval_blocks_release_execution_request(
    tmp_path: Path,
) -> None:
    advancement = _advancement()
    plan = _plan(advancement)
    review = review_release_build_plan(
        plan.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )

    with pytest.raises(ValueError, match="approved release build review digest"):
        BuildExecutionRequest.from_payloads(
            plan.to_dict(),
            _receipt(tmp_path),
            approved_plan_sha256=plan.sha256(),
            approved_source_snapshot_sha256=plan.source_snapshot_sha256,
            approved_permissions=(),
            release_build_review_value=review.to_dict(),
            approved_release_build_review_sha256="0" * 64,
        )


def test_review_bound_to_other_plan_cannot_authorize_execution(
    tmp_path: Path,
) -> None:
    advancement = _advancement()
    original = _plan(advancement)
    review = review_release_build_plan(
        original.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )
    changed = _plan(advancement, strategy="static_web_changed_strategy")

    with pytest.raises(ValueError, match="does not bind canonical build plan"):
        BuildExecutionRequest.from_payloads(
            changed.to_dict(),
            _receipt(tmp_path),
            approved_plan_sha256=changed.sha256(),
            approved_source_snapshot_sha256=changed.source_snapshot_sha256,
            approved_permissions=(),
            release_build_review_value=review.to_dict(),
            approved_release_build_review_sha256=review.sha256(),
        )


def test_ordinary_build_execution_request_remains_unchanged(tmp_path: Path) -> None:
    plan = _plan(None)

    request = BuildExecutionRequest.from_payloads(
        plan.to_dict(),
        _receipt(tmp_path),
        approved_plan_sha256=plan.sha256(),
        approved_source_snapshot_sha256=plan.source_snapshot_sha256,
        approved_permissions=(),
    )

    assert request.release_build_review_sha256 is None


def test_ordinary_build_rejects_irrelevant_release_review_inputs(
    tmp_path: Path,
) -> None:
    advancement = _advancement()
    release_plan = _plan(advancement)
    review = review_release_build_plan(
        release_plan.to_dict(),
        advancement.to_dict(),
        approved_release_candidate_advancement_sha256=advancement.sha256(),
    )
    ordinary_plan = _plan(None)

    with pytest.raises(
        ValueError,
        match="valid only for a release-lineage build plan",
    ):
        BuildExecutionRequest.from_payloads(
            ordinary_plan.to_dict(),
            _receipt(tmp_path),
            approved_plan_sha256=ordinary_plan.sha256(),
            approved_source_snapshot_sha256=ordinary_plan.source_snapshot_sha256,
            approved_permissions=(),
            release_build_review_value=review.to_dict(),
            approved_release_build_review_sha256=review.sha256(),
        )
