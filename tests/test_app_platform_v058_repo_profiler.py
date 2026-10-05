from __future__ import annotations

import json

import pytest

from phios.apps.intake import (
    AppIntakeAnalyzer,
    IntakeFile,
    RepositorySnapshot,
)
from phios.apps.repo_profile import (
    RepoCompatibilityAssessment,
    RepoProfile,
    profile_intake_result,
)


def _file(path: str, content: bytes) -> IntakeFile:
    import hashlib

    return IntakeFile(
        path=path,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        content=content,
    )


def _snapshot(
    *,
    files: tuple[IntakeFile, ...],
    root_paths: tuple[str, ...] | None = None,
    license_spdx: str | None = "MIT",
    archived: bool = False,
    disabled: bool = False,
) -> RepositorySnapshot:
    roots = root_paths or tuple(item.path for item in files)
    return RepositorySnapshot(
        repository_url="https://github.com/example/app",
        owner="example",
        name="app",
        description="fixture",
        default_branch="main",
        head_sha="a" * 40,
        archived=archived,
        disabled=disabled,
        license_spdx=license_spdx,
        root_paths=tuple(sorted(roots)),
        files=files,
        provider_request_count=3,
    )


def _analyze(snapshot: RepositorySnapshot):
    return AppIntakeAnalyzer().analyze(snapshot)


def test_mit_node_npm_repo_is_supported_after_operator_approval() -> None:
    package = _file(
        "package.json",
        json.dumps(
            {
                "name": "fixture",
                "version": "1.0.0",
                "scripts": {"build": "vite build"},
            }
        ).encode("utf-8"),
    )
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(package,),
                root_paths=("package.json", "package-lock.json"),
            )
        )
    )

    assert result.profile.license_state == "mit_confirmed"
    assert result.profile.build_family == "node_npm"
    assert result.compatibility.status == "SUPPORTED_AFTER_OPERATOR_APPROVAL"
    assert result.compatibility.blocking_reasons == ()
    assert result.compatibility.next_gate == "v0.27_source_acquisition_review"
    assert result.compatibility.advisory_only is True
    assert result.compatibility.acquisition_authority is False


def test_non_mit_repo_requires_license_review() -> None:
    package = _file(
        "package.json",
        b'{"name":"fixture","version":"1.0.0"}',
    )
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(package,),
                root_paths=("package.json", "package-lock.json"),
                license_spdx="GPL-3.0-only",
            )
        )
    )

    assert result.compatibility.status == "LICENSE_REVIEW_REQUIRED"
    assert "mit_only" in result.compatibility.blocking_reasons[0]


def test_submodule_marker_blocks_current_acquisition_path() -> None:
    package = _file("package.json", b'{"name":"fixture"}')
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(package,),
                root_paths=("package.json", "package-lock.json", ".gitmodules"),
            )
        )
    )

    assert result.profile.submodule_marker_observed is True
    assert result.compatibility.status == "SUBMODULE_REQUIRED"
    assert result.compatibility.next_gate == "submodule_acquisition_adapter"


def test_git_attributes_marker_requires_lfs_review() -> None:
    package = _file("package.json", b'{"name":"fixture"}')
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(package,),
                root_paths=("package.json", "package-lock.json", ".gitattributes"),
            )
        )
    )

    assert result.profile.gitattributes_marker_observed is True
    assert result.compatibility.status == "LFS_REVIEW_REQUIRED"


@pytest.mark.parametrize(
    ("lockfile", "family"),
    [
        ("pnpm-lock.yaml", "node_pnpm"),
        ("yarn.lock", "node_yarn"),
        ("bun.lockb", "node_bun"),
    ],
)
def test_unsupported_node_package_managers_report_missing_toolchain(
    lockfile: str,
    family: str,
) -> None:
    package = _file("package.json", b'{"name":"fixture"}')
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(package,),
                root_paths=("package.json", lockfile),
            )
        )
    )

    assert result.profile.build_family == family
    assert result.compatibility.status == "MISSING_TOOLCHAIN"


def test_node_without_lockfile_is_held() -> None:
    package = _file("package.json", b'{"name":"fixture"}')
    result = profile_intake_result(_analyze(_snapshot(files=(package,))))

    assert result.profile.build_family == "node_unlocked"
    assert result.compatibility.status == "LOCKFILE_REQUIRED"


def test_native_rust_repo_is_recognized_but_runtime_blocked() -> None:
    cargo = _file(
        "Cargo.toml",
        b'[package]\nname = "fixture"\nversion = "0.1.0"\n',
    )
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(cargo,),
                root_paths=("Cargo.toml", "Cargo.lock"),
            )
        )
    )

    assert result.profile.build_family == "rust_cargo"
    assert result.compatibility.status == "UNSUPPORTED_RUNTIME"


def test_inferred_python_project_requires_explicit_runtime_entrypoint() -> None:
    pyproject = _file(
        "pyproject.toml",
        b'[project]\nname = "fixture"\nversion = "1.0.0"\n',
    )
    result = profile_intake_result(_analyze(_snapshot(files=(pyproject,))))

    assert result.profile.build_family == "python_pep517"
    assert result.compatibility.status == "UNSUPPORTED_RUNTIME"
    assert "pyproject.toml" in result.compatibility.blocking_reasons[0]


def test_declared_python_file_entrypoint_can_reach_supported_class() -> None:
    declared = _file(
        "phios-app.json",
        json.dumps(
            {
                "schema_version": "phios.app_manifest.v0.1",
                "app_id": "fixture.python",
                "name": "Fixture Python",
                "version": "1.0.0",
                "description": "fixture",
                "source": {
                    "repository_url": "https://github.com/example/app",
                    "license_expression": "MIT",
                    "redistribution": "unknown",
                },
                "entrypoint": {"runtime": "python", "target": "app.py"},
                "permissions": [],
            }
        ).encode("utf-8"),
    )
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(declared,),
                root_paths=("phios-app.json", "app.py", "pyproject.toml"),
            )
        )
    )

    assert result.profile.manifest_source == "declared"
    assert result.compatibility.status == "SUPPORTED_AFTER_OPERATOR_APPROVAL"


def test_no_supported_root_marker_is_not_an_application() -> None:
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(),
                root_paths=("README.md", "LICENSE"),
            )
        )
    )

    assert result.compatibility.status == "NOT_AN_APPLICATION"


def test_disabled_repository_is_blocked_before_other_checks() -> None:
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(),
                root_paths=("README.md",),
                disabled=True,
            )
        )
    )

    assert result.compatibility.status == "REPOSITORY_DISABLED"


def test_archived_supported_repo_requires_review() -> None:
    index = _file("index.html", b"<html>fixture</html>")
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(index,),
                archived=True,
            )
        )
    )

    assert result.compatibility.status == "ARCHIVED_REPOSITORY_REVIEW"
    assert "archived=true" in result.compatibility.blocking_reasons[0]


def test_profile_and_assessment_detect_tamper_by_digest() -> None:
    package = _file("package.json", b'{"name":"fixture"}')
    result = profile_intake_result(
        _analyze(
            _snapshot(
                files=(package,),
                root_paths=("package.json", "package-lock.json"),
            )
        )
    )

    profile_data = result.profile.to_dict()
    assert profile_data["profile_sha256"] == result.profile.sha256()
    profile_data["runtime"] = "python"
    body = dict(profile_data)
    supplied = body.pop("profile_sha256")
    assert supplied != __import__("hashlib").sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    assessment_data = result.compatibility.to_dict()
    assert assessment_data["assessment_sha256"] == result.compatibility.sha256()
    assert RepoProfile.from_dict(result.profile.to_dict()) == result.profile
    assert (
        RepoCompatibilityAssessment.from_dict(result.compatibility.to_dict())
        == result.compatibility
    )

    tampered = result.compatibility.to_dict()
    tampered["next_gate"] = "tampered"
    with pytest.raises(ValueError, match="digest"):
        RepoCompatibilityAssessment.from_dict(tampered)
