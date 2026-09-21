from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

import phios.apps.release_compatibility as compatibility_module
from phios.apps.intake import AppIntakeEvidence, AppIntakeProposal, AppIntakeResult
from phios.apps.manifest import AppManifest
from phios.apps.release_compatibility import (
    ActiveReleaseBaseline,
    GitHubBuildMarkerProvider,
    ReleaseChangeEvidenceService,
    SourceMarker,
)
from phios.apps.release_discovery import (
    ReleaseCandidateIntake,
    ReleaseCandidateSelection,
)


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.request_count = 0
        self.urls: list[str] = []

    def get_json(self, url: str) -> Any:
        self.request_count += 1
        self.urls.append(url)
        try:
            return self.responses[url]
        except KeyError as exc:
            raise AssertionError(f"unexpected URL: {url}") from exc


class FakeMarkerProvider:
    def __init__(
        self,
        *,
        active: tuple[SourceMarker, ...],
        candidate: tuple[SourceMarker, ...],
    ) -> None:
        self.active = active
        self.candidate = candidate
        self.request_count = 0
        self.calls: list[tuple[str, str]] = []

    def observe(
        self,
        repository_url: str,
        commit_sha: str,
    ) -> tuple[SourceMarker, ...]:
        self.calls.append((repository_url, commit_sha))
        self.request_count += 1
        if commit_sha == "a" * 40:
            return self.active
        if commit_sha == "b" * 40:
            return self.candidate
        raise AssertionError(f"unexpected commit: {commit_sha}")


def _manifest(
    *,
    version: str,
    runtime: str = "node",
    target: str = "package.json",
    permissions: tuple[str, ...] = ("network.local",),
    license_expression: str = "MIT",
    redistribution: str = "permitted",
) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "github.michaelwave369.browsallax",
            "name": "Browsallax",
            "version": version,
            "description": "Local-first browser",
            "source": {
                "repository_url": "https://github.com/MichaelWave369/Browsallax",
                "license_expression": license_expression,
                "redistribution": redistribution,
            },
            "entrypoint": {"runtime": runtime, "target": target},
            "permissions": list(permissions),
        }
    )


def _baseline() -> ActiveReleaseBaseline:
    manifest = _manifest(version="1.0.0")
    return ActiveReleaseBaseline(
        app_id=manifest.app_id,
        version=manifest.version,
        repository_url=manifest.source.repository_url,
        commit_sha="a" * 40,
        manifest=manifest,
        manifest_sha256=manifest.sha256(),
        active_bundle_path="/tmp/phios/desktop/browsallax/active",
        active_grant_sha256="1" * 64,
    )


def _candidate_envelope(
    manifest: AppManifest | None = None,
    *,
    app_id: str = "github.michaelwave369.browsallax",
    repository_url: str = "https://github.com/MichaelWave369/Browsallax",
    commit_sha: str = "b" * 40,
) -> ReleaseCandidateIntake:
    candidate = manifest or _manifest(
        version="2.0.0",
        runtime="static_web",
        target="index.html",
        permissions=("network.local", "workspace.read"),
        license_expression="Apache-2.0",
        redistribution="unknown",
    )
    selection = ReleaseCandidateSelection(
        release_discovery_sha256="2" * 64,
        app_id=app_id,
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
                "sha256": hashlib.sha256(b"<html></html>").hexdigest(),
                "byte_count": 13,
            },
        ),
        provider_request_count=4,
    )
    proposal = AppIntakeProposal(
        repository_url=repository_url,
        status="declared_manifest",
        app_id=candidate.app_id,
        runtime=candidate.entrypoint.runtime,
        target=candidate.entrypoint.target,
        name=candidate.name,
        version=candidate.version,
        description=candidate.description,
        license_expression=candidate.source.license_expression,
        redistribution=candidate.source.redistribution,
        permissions=candidate.permissions,
        permissions_source="phios-app.json",
        basis=("exact commit candidate",),
    )
    return ReleaseCandidateIntake(
        selection=selection,
        intake=AppIntakeResult(
            evidence=evidence,
            proposal=proposal,
            manifest_candidate=candidate,
        ),
    )


def _marker(
    path: str,
    blob: str,
    *,
    size: int = 100,
    object_type: str = "file",
) -> SourceMarker:
    return SourceMarker(
        path=path,
        provider_object_type=object_type,
        byte_count=size,
        provider_blob_id=blob,
    )


def test_github_marker_provider_reads_only_exact_root_listing() -> None:
    commit = "a" * 40
    base = "https://api.github.com/repos/MichaelWave369/Browsallax"
    url = base + f"/contents?ref={commit}"
    client = FakeClient(
        {
            url: [
                {
                    "path": "README.md",
                    "type": "file",
                    "size": 999,
                    "sha": "1" * 40,
                },
                {
                    "path": "package.json",
                    "type": "file",
                    "size": 100,
                    "sha": "2" * 40,
                },
                {
                    "path": "package-lock.json",
                    "type": "file",
                    "size": 200,
                    "sha": "3" * 40,
                },
            ]
        }
    )

    observed = GitHubBuildMarkerProvider(client).observe(
        "https://github.com/MichaelWave369/Browsallax",
        commit,
    )

    assert [item.path for item in observed] == [
        "package-lock.json",
        "package.json",
    ]
    assert observed[0].provider_blob_id == "3" * 40
    assert client.urls == [url]


def test_release_change_evidence_is_descriptive_not_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _baseline()
    envelope = _candidate_envelope()
    provider = FakeMarkerProvider(
        active=(
            _marker("package.json", "3" * 40),
            _marker("package-lock.json", "4" * 40, size=200),
            _marker("vite.config.js", "5" * 40, size=50),
        ),
        candidate=(
            _marker("package.json", "6" * 40, size=120),
            _marker("package-lock.json", "4" * 40, size=200),
            _marker("index.html", "7" * 40, size=80),
        ),
    )
    monkeypatch.setattr(
        compatibility_module,
        "_active_baseline",
        lambda *args, **kwargs: baseline,
    )

    evidence = ReleaseChangeEvidenceService(provider=provider).compare(
        Path("/tmp/ignored"),
        envelope.to_dict(),
        approved_release_candidate_intake_sha256=envelope.sha256(),
        install_root=Path("/tmp/installed"),
        desktop_root=Path("/tmp/desktop"),
        applications_root=Path("/tmp/applications"),
    )

    assert evidence.compatibility_verdict == "not_assessed"
    assert evidence.build_authority is False
    assert evidence.install_authority is False
    assert evidence.update_authority is False
    assert evidence.manifest_changes == (
        "version_changed",
        "runtime_changed",
        "entrypoint_target_changed",
        "license_expression_changed",
        "redistribution_changed",
        "permissions_changed",
    )
    assert evidence.permissions_added == ("workspace.read",)
    assert evidence.permissions_removed == ()
    marker_changes = {item.path: item.change for item in evidence.source_marker_changes}
    assert marker_changes == {
        "index.html": "added",
        "package-lock.json": "unchanged",
        "package.json": "changed",
        "vite.config.js": "removed",
    }
    assert provider.calls == [
        (baseline.repository_url, "a" * 40),
        (baseline.repository_url, "b" * 40),
    ]


def test_permission_removal_is_reported_without_interpreting_safety(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _baseline()
    candidate = _manifest(version="2.0.0", permissions=())
    envelope = _candidate_envelope(candidate)
    provider = FakeMarkerProvider(active=(), candidate=())
    monkeypatch.setattr(
        compatibility_module,
        "_active_baseline",
        lambda *args, **kwargs: baseline,
    )

    evidence = ReleaseChangeEvidenceService(provider=provider).compare(
        Path("/tmp/ignored"),
        envelope.to_dict(),
        approved_release_candidate_intake_sha256=envelope.sha256(),
        install_root=Path("/tmp/installed"),
        desktop_root=Path("/tmp/desktop"),
        applications_root=Path("/tmp/applications"),
    )

    assert evidence.permissions_added == ()
    assert evidence.permissions_removed == ("network.local",)
    assert "permissions_changed" in evidence.manifest_changes
    assert evidence.compatibility_verdict == "not_assessed"


def test_candidate_intake_requires_exact_operator_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _candidate_envelope()
    provider = FakeMarkerProvider(active=(), candidate=())
    monkeypatch.setattr(
        compatibility_module,
        "_active_baseline",
        lambda *args, **kwargs: _baseline(),
    )

    with pytest.raises(ValueError, match="approved release candidate intake digest"):
        ReleaseChangeEvidenceService(provider=provider).compare(
            Path("/tmp/ignored"),
            envelope.to_dict(),
            approved_release_candidate_intake_sha256="0" * 64,
            install_root=Path("/tmp/installed"),
            desktop_root=Path("/tmp/desktop"),
            applications_root=Path("/tmp/applications"),
        )

    assert provider.calls == []


def test_tampered_candidate_intake_fails_before_marker_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _candidate_envelope()
    payload = envelope.to_dict()
    payload["intake"]["evidence"]["head_sha"] = "c" * 40
    provider = FakeMarkerProvider(active=(), candidate=())
    monkeypatch.setattr(
        compatibility_module,
        "_active_baseline",
        lambda *args, **kwargs: _baseline(),
    )

    with pytest.raises(ValueError, match="digest does not match"):
        ReleaseChangeEvidenceService(provider=provider).compare(
            Path("/tmp/ignored"),
            payload,
            approved_release_candidate_intake_sha256=envelope.sha256(),
            install_root=Path("/tmp/installed"),
            desktop_root=Path("/tmp/desktop"),
            applications_root=Path("/tmp/applications"),
        )

    assert provider.calls == []


def test_candidate_repository_must_match_active_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _baseline()
    envelope = _candidate_envelope(
        repository_url="https://github.com/example/other",
    )
    provider = FakeMarkerProvider(active=(), candidate=())
    monkeypatch.setattr(
        compatibility_module,
        "_active_baseline",
        lambda *args, **kwargs: baseline,
    )

    with pytest.raises(ValueError, match="repository does not match active"):
        ReleaseChangeEvidenceService(provider=provider).compare(
            Path("/tmp/ignored"),
            envelope.to_dict(),
            approved_release_candidate_intake_sha256=envelope.sha256(),
            install_root=Path("/tmp/installed"),
            desktop_root=Path("/tmp/desktop"),
            applications_root=Path("/tmp/applications"),
        )

    assert provider.calls == []


def test_marker_type_change_is_observed_not_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _candidate_envelope(
        _manifest(version="2.0.0"),
    )
    provider = FakeMarkerProvider(
        active=(_marker("index.html", "8" * 40, object_type="file"),),
        candidate=(_marker("index.html", "9" * 40, object_type="dir", size=0),),
    )
    monkeypatch.setattr(
        compatibility_module,
        "_active_baseline",
        lambda *args, **kwargs: _baseline(),
    )

    evidence = ReleaseChangeEvidenceService(provider=provider).compare(
        Path("/tmp/ignored"),
        envelope.to_dict(),
        approved_release_candidate_intake_sha256=envelope.sha256(),
        install_root=Path("/tmp/installed"),
        desktop_root=Path("/tmp/desktop"),
        applications_root=Path("/tmp/applications"),
    )

    assert evidence.source_marker_changes[0].change == "type_changed"
