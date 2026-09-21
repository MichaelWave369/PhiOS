from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import pytest

from phios.apps.intake import (
    AppIntakeAnalyzer,
    GitHubPublicRepoProvider,
    GitHubRepositoryRef,
    RepositorySnapshot,
    IntakeFile,
)


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.request_count = 0

    def get_json(self, url: str) -> Any:
        self.request_count += 1
        try:
            return self.responses[url]
        except KeyError as exc:
            raise AssertionError(f"unexpected URL: {url}") from exc


def _contents(content: bytes) -> dict[str, object]:
    return {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(content).decode("ascii"),
    }


def _snapshot(files: dict[str, bytes], **overrides: object) -> RepositorySnapshot:
    data: dict[str, object] = {
        "repository_url": "https://github.com/MichaelWave369/Browsallax",
        "owner": "MichaelWave369",
        "name": "Browsallax",
        "description": "Local-first browser.",
        "default_branch": "main",
        "head_sha": "a" * 40,
        "archived": False,
        "disabled": False,
        "license_spdx": "MIT",
        "root_paths": tuple(sorted(files)),
        "files": tuple(
            IntakeFile(
                path=path,
                sha256=hashlib.sha256(content).hexdigest(),
                byte_count=len(content),
                content=content,
            )
            for path, content in files.items()
        ),
        "provider_request_count": 4,
    }
    data.update(overrides)
    return RepositorySnapshot(**data)  # type: ignore[arg-type]


def test_repository_ref_accepts_only_canonical_public_github_shape() -> None:
    ref = GitHubRepositoryRef.parse("https://github.com/MichaelWave369/Browsallax.git")
    assert ref.repository_url == "https://github.com/MichaelWave369/Browsallax"

    with pytest.raises(ValueError):
        GitHubRepositoryRef.parse("https://example.com/owner/repo")

    with pytest.raises(ValueError):
        GitHubRepositoryRef.parse("https://github.com/owner/repo/issues")


def test_provider_reads_only_bounded_root_markers() -> None:
    repository = "https://api.github.com/repos/MichaelWave369/Browsallax"
    package = json.dumps(
        {"name": "browsallax", "version": "1.2.3", "description": "Browser"}
    ).encode()
    client = FakeClient(
        {
            repository: {
                "private": False,
                "default_branch": "main",
                "description": "Browser",
                "archived": False,
                "disabled": False,
                "license": {"spdx_id": "MIT"},
            },
            repository + "/branches/main": {"commit": {"sha": "b" * 40}},
            repository + "/contents?ref=main": [
                {"path": "README.md", "type": "file"},
                {"path": "package.json", "type": "file"},
                {"path": "src", "type": "dir"},
            ],
            repository + "/contents/package.json?ref=main": _contents(package),
        }
    )

    snapshot = GitHubPublicRepoProvider(client).inspect(
        "https://github.com/MichaelWave369/Browsallax"
    )

    assert snapshot.head_sha == "b" * 40
    assert snapshot.license_spdx == "MIT"
    assert [item.path for item in snapshot.files] == ["package.json"]
    assert client.request_count == 4


def test_node_intake_produces_candidate_without_inferred_permissions() -> None:
    package = json.dumps(
        {"name": "browsallax", "version": "1.2.3", "description": "Browser"}
    ).encode()
    result = AppIntakeAnalyzer().analyze(_snapshot({"package.json": package}))

    assert result.proposal.status == "inferred_candidate"
    assert result.proposal.runtime == "node"
    assert result.proposal.target == "package.json"
    assert result.proposal.permissions == ()
    assert result.proposal.permissions_source == "not_declared"
    assert result.proposal.redistribution == "unknown"
    assert result.manifest_candidate is not None
    assert result.manifest_candidate.permissions == ()


def test_python_intake_uses_project_metadata() -> None:
    pyproject = (
        b'[project]\nname = "phi-tool"\nversion = "0.4.0"\n'
        b'description = "Useful thing"\n'
    )
    result = AppIntakeAnalyzer().analyze(_snapshot({"pyproject.toml": pyproject}))

    assert result.proposal.runtime == "python"
    assert result.proposal.name == "phi-tool"
    assert result.proposal.version == "0.4.0"


def test_static_web_candidate_is_detected_from_index() -> None:
    result = AppIntakeAnalyzer().analyze(_snapshot({"index.html": b"<html></html>"}))

    assert result.proposal.runtime == "static_web"
    assert result.proposal.target == "index.html"


def test_declared_phios_manifest_is_preserved_as_declared_metadata() -> None:
    manifest = {
        "schema_version": "phios.app_manifest.v0.1",
        "app_id": "phi.browsallax",
        "name": "Browsallax",
        "version": "1.0.0",
        "description": "Browser",
        "source": {
            "repository_url": "https://github.com/MichaelWave369/Browsallax",
            "license_expression": "MIT",
            "redistribution": "permitted",
        },
        "entrypoint": {"runtime": "node", "target": "package.json"},
        "permissions": ["network.local"],
    }
    result = AppIntakeAnalyzer().analyze(
        _snapshot({"phios-app.json": json.dumps(manifest).encode()})
    )

    assert result.proposal.status == "declared_manifest"
    assert result.proposal.permissions == ("network.local",)
    assert result.proposal.permissions_source == "phios-app.json"
    assert result.manifest_candidate is not None


def test_invalid_declared_manifest_fails_closed_without_fallback() -> None:
    package = json.dumps({"name": "would-have-worked", "version": "1.0.0"}).encode()
    result = AppIntakeAnalyzer().analyze(
        _snapshot(
            {
                "phios-app.json": b'{"schema_version":"wrong"}',
                "package.json": package,
            }
        )
    )

    assert result.proposal.status == "invalid_declared_manifest"
    assert result.manifest_candidate is None


def test_declared_manifest_must_match_inspected_repository() -> None:
    manifest = {
        "schema_version": "phios.app_manifest.v0.1",
        "app_id": "phi.other",
        "name": "Other",
        "version": "1.0.0",
        "description": "",
        "source": {
            "repository_url": "https://github.com/SomeoneElse/Other",
            "license_expression": "MIT",
            "redistribution": "permitted",
        },
        "entrypoint": {"runtime": "node", "target": "package.json"},
        "permissions": [],
    }
    result = AppIntakeAnalyzer().analyze(
        _snapshot({"phios-app.json": json.dumps(manifest).encode()})
    )

    assert result.proposal.status == "declared_source_mismatch"
    assert result.manifest_candidate is None


def test_persisted_evidence_contains_digests_not_raw_file_content() -> None:
    secret_marker = "PLANTED_RAW_PACKAGE_VALUE_369"
    package = json.dumps(
        {"name": "browsallax", "version": "1.0.0", "extra": secret_marker}
    ).encode()
    result = AppIntakeAnalyzer().analyze(_snapshot({"package.json": package}))

    serialized = json.dumps(result.evidence.to_dict(), sort_keys=True)
    assert secret_marker not in serialized
    assert result.evidence.inspected_files[0]["sha256"] == hashlib.sha256(package).hexdigest()


def test_disabled_repository_does_not_produce_manifest_candidate() -> None:
    package = json.dumps({"name": "disabled", "version": "1.0.0"}).encode()
    result = AppIntakeAnalyzer().analyze(
        _snapshot({"package.json": package}, disabled=True)
    )

    assert result.proposal.status == "repository_disabled"
    assert result.manifest_candidate is None


def test_no_supported_marker_remains_insufficient_metadata() -> None:
    result = AppIntakeAnalyzer().analyze(_snapshot({}))

    assert result.proposal.status == "insufficient_metadata"
    assert result.manifest_candidate is None


def test_provider_can_inspect_exact_commit_without_default_branch_drift() -> None:
    repository = "https://api.github.com/repos/MichaelWave369/Browsallax"
    commit_sha = "c" * 40
    package = json.dumps(
        {"name": "browsallax", "version": "2.0.0", "description": "Release"}
    ).encode()
    client = FakeClient(
        {
            repository: {
                "private": False,
                "default_branch": "main",
                "description": "Browser",
                "archived": False,
                "disabled": False,
                "license": {"spdx_id": "MIT"},
            },
            repository + f"/commits/{commit_sha}": {"sha": commit_sha},
            repository + f"/contents?ref={commit_sha}": [
                {"path": "package.json", "type": "file"},
            ],
            repository + f"/contents/package.json?ref={commit_sha}": _contents(package),
        }
    )

    snapshot = GitHubPublicRepoProvider(client).inspect_at_commit(
        "https://github.com/MichaelWave369/Browsallax",
        commit_sha,
    )

    assert snapshot.head_sha == commit_sha
    assert [item.path for item in snapshot.files] == ["package.json"]
    assert client.request_count == 4
