from __future__ import annotations

import copy

import pytest

from phios.apps.release_compatibility import (
    ReleaseChangeEvidence,
    SourceMarker,
    SourceMarkerChange,
)
from phios.apps.release_review import (
    MarkerChangeAcknowledgement,
    ReleaseChangeAcceptanceRecord,
    accept_release_change_evidence,
)


def _marker(path: str, blob: str, *, size: int = 100) -> SourceMarker:
    return SourceMarker(
        path=path,
        provider_object_type="file",
        byte_count=size,
        provider_blob_id=blob,
    )


def _evidence() -> ReleaseChangeEvidence:
    return ReleaseChangeEvidence(
        app_id="github.michaelwave369.browsallax",
        repository_url="https://github.com/MichaelWave369/Browsallax",
        active_version="1.0.0",
        candidate_version="2.0.0",
        active_commit_sha="a" * 40,
        candidate_commit_sha="b" * 40,
        active_manifest_sha256="1" * 64,
        candidate_manifest_sha256="2" * 64,
        release_candidate_intake_sha256="3" * 64,
        active_bundle_path="/tmp/phios/desktop/browsallax/active",
        active_grant_sha256="4" * 64,
        manifest_changes=(
            "version_changed",
            "runtime_changed",
            "permissions_changed",
        ),
        permissions_added=("workspace.read",),
        permissions_removed=("network.local",),
        source_marker_changes=(
            SourceMarkerChange(
                path="index.html",
                change="added",
                active=None,
                candidate=_marker("index.html", "5" * 40),
            ),
            SourceMarkerChange(
                path="package-lock.json",
                change="unchanged",
                active=_marker("package-lock.json", "6" * 40, size=200),
                candidate=_marker("package-lock.json", "6" * 40, size=200),
            ),
            SourceMarkerChange(
                path="package.json",
                change="changed",
                active=_marker("package.json", "7" * 40),
                candidate=_marker("package.json", "8" * 40, size=120),
            ),
        ),
        provider_request_count=2,
    )


def _accept(evidence: ReleaseChangeEvidence) -> ReleaseChangeAcceptanceRecord:
    return accept_release_change_evidence(
        evidence.to_dict(),
        approved_release_change_evidence_sha256=evidence.sha256(),
        acknowledged_manifest_changes=(
            "permissions_changed",
            "runtime_changed",
            "version_changed",
        ),
        acknowledged_permissions_added=("workspace.read",),
        acknowledged_permissions_removed=("network.local",),
        acknowledged_source_marker_changes=(
            MarkerChangeAcknowledgement(path="index.html", change="added"),
            MarkerChangeAcknowledgement(path="package.json", change="changed"),
        ),
        review_note="Reviewed the exact observed changes.",
    )


def test_exact_acknowledgement_creates_non_authoritative_acceptance() -> None:
    evidence = _evidence()
    record = _accept(evidence)

    assert record.release_change_evidence_sha256 == evidence.sha256()
    assert record.review_scope == "observed_changes_only"
    assert record.review_state == "accepted_for_further_review"
    assert record.compatibility_verdict == "not_assessed"
    assert record.permission_grant_authority is False
    assert record.build_authority is False
    assert record.install_authority is False
    assert record.update_authority is False
    assert record.acknowledged_source_marker_changes == (
        MarkerChangeAcknowledgement(path="index.html", change="added"),
        MarkerChangeAcknowledgement(path="package.json", change="changed"),
    )


def test_unchanged_marker_requires_no_acknowledgement() -> None:
    evidence = _evidence()
    record = _accept(evidence)

    assert all(
        item.path != "package-lock.json"
        for item in record.acknowledged_source_marker_changes
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "manifest",
            ("runtime_changed", "version_changed"),
            "manifest change acknowledgements",
        ),
        (
            "added",
            (),
            "added-permission acknowledgements",
        ),
        (
            "removed",
            (),
            "removed-permission acknowledgements",
        ),
        (
            "markers",
            (MarkerChangeAcknowledgement(path="package.json", change="changed"),),
            "source-marker acknowledgements",
        ),
    ],
)
def test_missing_acknowledgement_fails_closed(
    field: str,
    value: object,
    message: str,
) -> None:
    evidence = _evidence()
    kwargs = {
        "acknowledged_manifest_changes": (
            "permissions_changed",
            "runtime_changed",
            "version_changed",
        ),
        "acknowledged_permissions_added": ("workspace.read",),
        "acknowledged_permissions_removed": ("network.local",),
        "acknowledged_source_marker_changes": (
            MarkerChangeAcknowledgement(path="index.html", change="added"),
            MarkerChangeAcknowledgement(path="package.json", change="changed"),
        ),
    }
    if field == "manifest":
        kwargs["acknowledged_manifest_changes"] = value
    elif field == "added":
        kwargs["acknowledged_permissions_added"] = value
    elif field == "removed":
        kwargs["acknowledged_permissions_removed"] = value
    else:
        kwargs["acknowledged_source_marker_changes"] = value

    with pytest.raises(ValueError, match=message):
        accept_release_change_evidence(
            evidence.to_dict(),
            approved_release_change_evidence_sha256=evidence.sha256(),
            **kwargs,  # type: ignore[arg-type]
        )


def test_extra_invented_acknowledgement_fails_closed() -> None:
    evidence = _evidence()

    with pytest.raises(ValueError, match="manifest change acknowledgements"):
        accept_release_change_evidence(
            evidence.to_dict(),
            approved_release_change_evidence_sha256=evidence.sha256(),
            acknowledged_manifest_changes=(
                "permissions_changed",
                "runtime_changed",
                "version_changed",
                "name_changed",
            ),
            acknowledged_permissions_added=("workspace.read",),
            acknowledged_permissions_removed=("network.local",),
            acknowledged_source_marker_changes=(
                MarkerChangeAcknowledgement(path="index.html", change="added"),
                MarkerChangeAcknowledgement(path="package.json", change="changed"),
            ),
        )


def test_duplicate_acknowledgement_is_rejected() -> None:
    evidence = _evidence()

    with pytest.raises(ValueError, match="duplicate acknowledgements"):
        accept_release_change_evidence(
            evidence.to_dict(),
            approved_release_change_evidence_sha256=evidence.sha256(),
            acknowledged_manifest_changes=(
                "permissions_changed",
                "runtime_changed",
                "runtime_changed",
                "version_changed",
            ),
            acknowledged_permissions_added=("workspace.read",),
            acknowledged_permissions_removed=("network.local",),
            acknowledged_source_marker_changes=(
                MarkerChangeAcknowledgement(path="index.html", change="added"),
                MarkerChangeAcknowledgement(path="package.json", change="changed"),
            ),
        )


def test_stale_operator_digest_fails_before_acceptance() -> None:
    evidence = _evidence()

    with pytest.raises(ValueError, match="approved release change evidence digest"):
        accept_release_change_evidence(
            evidence.to_dict(),
            approved_release_change_evidence_sha256="0" * 64,
            acknowledged_manifest_changes=evidence.manifest_changes,
            acknowledged_permissions_added=evidence.permissions_added,
            acknowledged_permissions_removed=evidence.permissions_removed,
            acknowledged_source_marker_changes=(
                MarkerChangeAcknowledgement(path="index.html", change="added"),
                MarkerChangeAcknowledgement(path="package.json", change="changed"),
            ),
        )


def test_tampered_v045_evidence_is_rejected_even_if_old_digest_is_approved() -> None:
    evidence = _evidence()
    payload = copy.deepcopy(evidence.to_dict())
    payload["permissions_added"].append("camera.capture")

    with pytest.raises(ValueError, match="digest does not match"):
        accept_release_change_evidence(
            payload,
            approved_release_change_evidence_sha256=evidence.sha256(),
            acknowledged_manifest_changes=evidence.manifest_changes,
            acknowledged_permissions_added=(
                "camera.capture",
                "workspace.read",
            ),
            acknowledged_permissions_removed=evidence.permissions_removed,
            acknowledged_source_marker_changes=(
                MarkerChangeAcknowledgement(path="index.html", change="added"),
                MarkerChangeAcknowledgement(path="package.json", change="changed"),
            ),
        )


def test_acceptance_record_round_trip_and_tamper_detection() -> None:
    record = _accept(_evidence())
    payload = record.to_dict()

    assert ReleaseChangeAcceptanceRecord.from_dict(payload) == record

    payload["review_state"] = "install_now"
    with pytest.raises(ValueError):
        ReleaseChangeAcceptanceRecord.from_dict(payload)


def test_marker_acknowledgement_uses_explicit_path_equals_change_syntax() -> None:
    parsed = MarkerChangeAcknowledgement.from_text("package.json=changed")
    assert parsed == MarkerChangeAcknowledgement(
        path="package.json",
        change="changed",
    )

    with pytest.raises(ValueError, match="PATH=CHANGE"):
        MarkerChangeAcknowledgement.from_text("package.json")


def test_no_change_evidence_can_be_acknowledged_without_fake_changes() -> None:
    evidence = ReleaseChangeEvidence(
        app_id="github.michaelwave369.browsallax",
        repository_url="https://github.com/MichaelWave369/Browsallax",
        active_version="1.0.0",
        candidate_version="1.0.0",
        active_commit_sha="a" * 40,
        candidate_commit_sha="b" * 40,
        active_manifest_sha256="1" * 64,
        candidate_manifest_sha256="1" * 64,
        release_candidate_intake_sha256="3" * 64,
        active_bundle_path="/tmp/phios/desktop/browsallax/active",
        active_grant_sha256="4" * 64,
        manifest_changes=(),
        permissions_added=(),
        permissions_removed=(),
        source_marker_changes=(
            SourceMarkerChange(
                path="package.json",
                change="unchanged",
                active=_marker("package.json", "7" * 40),
                candidate=_marker("package.json", "7" * 40),
            ),
        ),
        provider_request_count=2,
    )

    record = accept_release_change_evidence(
        evidence.to_dict(),
        approved_release_change_evidence_sha256=evidence.sha256(),
    )

    assert record.acknowledged_manifest_changes == ()
    assert record.acknowledged_source_marker_changes == ()
    assert record.review_state == "accepted_for_further_review"
