from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import phios.apps.release_discovery as release_module
from phios.apps.acquisition import review_intake_for_acquisition
from phios.apps.intake import (
    AppIntakeAnalyzer,
    GitHubPublicRepoProvider,
    IntakeFile,
    RepositorySnapshot,
)
from phios.apps.release_discovery import (
    GitHubReleaseProvider,
    ReleaseCandidateSelection,
    ReleaseDiscovery,
    ReleaseDiscoveryService,
    ReleaseEvidence,
    inspect_selected_release,
    select_release_candidate,
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


class FakeReleaseProvider:
    def __init__(self, releases: tuple[ReleaseEvidence, ...]) -> None:
        self.releases = releases
        self.request_count = 3
        self.calls: list[str] = []

    def discover(self, repository_url: str) -> tuple[bool, tuple[ReleaseEvidence, ...]]:
        self.calls.append(repository_url)
        return False, self.releases


class FakeExactCommitProvider:
    def __init__(self, snapshot: RepositorySnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[str, str]] = []

    def inspect_at_commit(
        self,
        repository_url: str,
        commit_sha: str,
    ) -> RepositorySnapshot:
        self.calls.append((repository_url, commit_sha))
        return self.snapshot


def _release(
    position: int,
    *,
    tag: str,
    commit: str,
    release_id: int | None = None,
    prerelease: bool = False,
    draft: bool = False,
) -> ReleaseEvidence:
    return ReleaseEvidence(
        release_id=release_id or (100 + position),
        provider_position=position,
        tag_name=tag,
        name=f"Release {tag}",
        published_at="2026-09-20T20:00:00Z",
        prerelease=prerelease,
        draft=draft,
        commit_sha=commit,
    )


def _discovery(*releases: ReleaseEvidence) -> ReleaseDiscovery:
    return ReleaseDiscovery(
        app_id="github.michaelwave369.browsallax",
        installed_version="1.0.0",
        repository_url="https://github.com/MichaelWave369/Browsallax",
        active_bundle_path="/tmp/desktop/github.michaelwave369.browsallax/active",
        active_grant_sha256="a" * 64,
        repository_archived=False,
        releases=tuple(releases),
        provider_request_count=5,
    )


def _snapshot(*, commit_sha: str, version: str = "2.0.0") -> RepositorySnapshot:
    package = json.dumps(
        {
            "name": "browsallax",
            "version": version,
            "description": "Browser",
        }
    ).encode()
    return RepositorySnapshot(
        repository_url="https://github.com/MichaelWave369/Browsallax",
        owner="MichaelWave369",
        name="Browsallax",
        description="Browser",
        default_branch="main",
        head_sha=commit_sha,
        archived=False,
        disabled=False,
        license_spdx="MIT",
        root_paths=("package.json",),
        files=(
            IntakeFile(
                path="package.json",
                sha256=hashlib.sha256(package).hexdigest(),
                byte_count=len(package),
                content=package,
            ),
        ),
        provider_request_count=4,
    )


def test_provider_preserves_github_order_and_resolves_annotated_tag() -> None:
    base = "https://api.github.com/repos/MichaelWave369/Browsallax"
    commit_a = "a" * 40
    tag_object = "b" * 40
    commit_b = "c" * 40
    client = FakeClient(
        {
            base: {
                "private": False,
                "disabled": False,
                "archived": False,
            },
            base + "/releases?per_page=8": [
                {
                    "id": 10,
                    "tag_name": "v2.0.0",
                    "name": "Two",
                    "published_at": "2026-09-20T20:00:00Z",
                    "draft": False,
                    "prerelease": False,
                },
                {
                    "id": 9,
                    "tag_name": "v1.5.0",
                    "name": "One Five",
                    "published_at": "2026-09-19T20:00:00Z",
                    "draft": False,
                    "prerelease": False,
                },
            ],
            base + "/git/ref/tags/v2.0.0": {
                "object": {"type": "commit", "sha": commit_a}
            },
            base + "/git/ref/tags/v1.5.0": {
                "object": {"type": "tag", "sha": tag_object}
            },
            base + f"/git/tags/{tag_object}": {
                "object": {"type": "commit", "sha": commit_b}
            },
        }
    )

    archived, releases = GitHubReleaseProvider(client).discover(
        "https://github.com/MichaelWave369/Browsallax"
    )

    assert archived is False
    assert [item.tag_name for item in releases] == ["v2.0.0", "v1.5.0"]
    assert [item.provider_position for item in releases] == [0, 1]
    assert [item.commit_sha for item in releases] == [commit_a, commit_b]


def test_selection_requires_exact_discovery_digest_and_explicit_tag() -> None:
    discovery = _discovery(
        _release(0, tag="v2.0.0", commit="b" * 40),
        _release(1, tag="v1.5.0", commit="c" * 40),
    )

    with pytest.raises(ValueError, match="approved release discovery digest"):
        select_release_candidate(
            discovery.to_dict(),
            tag_name="v1.5.0",
            approved_release_discovery_sha256="0" * 64,
        )

    selection = select_release_candidate(
        discovery.to_dict(),
        tag_name="v1.5.0",
        approved_release_discovery_sha256=discovery.sha256(),
    )

    assert selection.tag_name == "v1.5.0"
    assert selection.commit_sha == "c" * 40
    assert selection.update_authority is False
    assert selection.acquisition_authority is False


def test_provider_order_is_not_candidate_ranking() -> None:
    discovery = _discovery(
        _release(0, tag="v9.0.0", commit="d" * 40),
        _release(1, tag="v1.0.1", commit="e" * 40),
    )

    selection = select_release_candidate(
        discovery.to_dict(),
        tag_name="v1.0.1",
        approved_release_discovery_sha256=discovery.sha256(),
    )

    assert discovery.ordering_semantics == "provider_order_only"
    assert selection.tag_name == "v1.0.1"


def test_prerelease_requires_explicit_opt_in() -> None:
    discovery = _discovery(
        _release(
            0,
            tag="v2.0.0-rc1",
            commit="f" * 40,
            prerelease=True,
        )
    )

    with pytest.raises(ValueError, match="explicit allow_prerelease"):
        select_release_candidate(
            discovery.to_dict(),
            tag_name="v2.0.0-rc1",
            approved_release_discovery_sha256=discovery.sha256(),
        )

    selected = select_release_candidate(
        discovery.to_dict(),
        tag_name="v2.0.0-rc1",
        approved_release_discovery_sha256=discovery.sha256(),
        allow_prerelease=True,
    )
    assert selected.prerelease is True


def test_draft_and_duplicate_tags_fail_closed() -> None:
    draft = _discovery(
        _release(0, tag="v2.0.0", commit="1" * 40, draft=True)
    )
    with pytest.raises(ValueError, match="draft"):
        select_release_candidate(
            draft.to_dict(),
            tag_name="v2.0.0",
            approved_release_discovery_sha256=draft.sha256(),
        )

    duplicate = _discovery(
        _release(0, tag="v2.0.0", commit="2" * 40, release_id=101),
        _release(1, tag="v2.0.0", commit="3" * 40, release_id=102),
    )
    with pytest.raises(ValueError, match="exactly one"):
        select_release_candidate(
            duplicate.to_dict(),
            tag_name="v2.0.0",
            approved_release_discovery_sha256=duplicate.sha256(),
        )


def test_discovery_service_uses_active_app_source_without_selecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeReleaseProvider(
        (_release(0, tag="v2.0.0", commit="4" * 40),)
    )
    monkeypatch.setattr(
        release_module,
        "_active_app_source",
        lambda *args, **kwargs: release_module._ActiveAppSource(
            app_id="github.michaelwave369.browsallax",
            version="1.0.0",
            repository_url="https://github.com/MichaelWave369/Browsallax",
            bundle_path="/tmp/active",
            grant_sha256="5" * 64,
        ),
    )

    discovery = ReleaseDiscoveryService(provider=provider).discover(
        Path("/tmp/ignored"),
        install_root=Path("/tmp/installed"),
        desktop_root=Path("/tmp/desktop"),
        applications_root=Path("/tmp/applications"),
    )

    assert discovery.releases[0].tag_name == "v2.0.0"
    assert discovery.selection_authority is False
    assert discovery.update_authority is False
    assert provider.calls == ["https://github.com/MichaelWave369/Browsallax"]


def test_selected_release_is_inspected_at_exact_commit_and_bridges_to_v027() -> None:
    commit = "6" * 40
    discovery = _discovery(_release(0, tag="v2.0.0", commit=commit))
    selection = select_release_candidate(
        discovery.to_dict(),
        tag_name="v2.0.0",
        approved_release_discovery_sha256=discovery.sha256(),
    )
    provider = FakeExactCommitProvider(_snapshot(commit_sha=commit))

    envelope = inspect_selected_release(
        selection.to_dict(),
        approved_release_candidate_selection_sha256=selection.sha256(),
        provider=provider,  # type: ignore[arg-type]
        analyzer=AppIntakeAnalyzer(),
    )

    assert provider.calls == [
        ("https://github.com/MichaelWave369/Browsallax", commit)
    ]
    payload = envelope.to_dict()
    assert payload["selection"]["commit_sha"] == commit
    assert payload["intake"]["evidence"]["head_sha"] == commit

    review = review_intake_for_acquisition(payload)
    assert review.commit_sha == commit
    assert review.manifest.app_id == selection.app_id
    assert review.manifest.version == "2.0.0"


def test_selected_release_requires_exact_selection_digest() -> None:
    commit = "7" * 40
    discovery = _discovery(_release(0, tag="v2.0.0", commit=commit))
    selection = select_release_candidate(
        discovery.to_dict(),
        tag_name="v2.0.0",
        approved_release_discovery_sha256=discovery.sha256(),
    )
    provider = FakeExactCommitProvider(_snapshot(commit_sha=commit))

    with pytest.raises(ValueError, match="approved release selection digest"):
        inspect_selected_release(
            selection.to_dict(),
            approved_release_candidate_selection_sha256="0" * 64,
            provider=provider,  # type: ignore[arg-type]
        )


def test_release_candidate_envelope_rejects_app_identity_change() -> None:
    commit = "8" * 40
    discovery = _discovery(_release(0, tag="v2.0.0", commit=commit))
    selection = select_release_candidate(
        discovery.to_dict(),
        tag_name="v2.0.0",
        approved_release_discovery_sha256=discovery.sha256(),
    )
    package = json.dumps(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.changed-identity",
            "name": "Changed",
            "version": "2.0.0",
            "description": "Changed",
            "source": {
                "repository_url": "https://github.com/MichaelWave369/Browsallax",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    ).encode()
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/MichaelWave369/Browsallax",
        owner="MichaelWave369",
        name="Browsallax",
        description="Browser",
        default_branch="main",
        head_sha=commit,
        archived=False,
        disabled=False,
        license_spdx="MIT",
        root_paths=("phios-app.json",),
        files=(
            IntakeFile(
                path="phios-app.json",
                sha256=hashlib.sha256(package).hexdigest(),
                byte_count=len(package),
                content=package,
            ),
        ),
        provider_request_count=4,
    )

    with pytest.raises(ValueError, match="app_id changed"):
        inspect_selected_release(
            selection.to_dict(),
            approved_release_candidate_selection_sha256=selection.sha256(),
            provider=FakeExactCommitProvider(snapshot),  # type: ignore[arg-type]
        )
