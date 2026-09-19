from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_plan import BuildPlan, plan_build_from_payloads, review_build_plan
from phios.apps.manifest import AppManifest


def _manifest(runtime: str = "node", target: str = "package.json") -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.example",
            "name": "Example",
            "version": "1.0.0",
            "description": "Example app",
            "source": {
                "repository_url": "https://github.com/example/example",
                "license_expression": "MIT",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": runtime, "target": target},
            "permissions": [],
        }
    )


def _intake(manifest: AppManifest) -> dict[str, Any]:
    return {
        "evidence": {
            "repository_url": "https://github.com/example/example",
            "head_sha": "a" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": "https://github.com/example/example",
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }


def _snapshot_stats(root: Path) -> tuple[int, int]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def _receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    file_count, total_bytes = _snapshot_stats(root)
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-09-19T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": "https://github.com/example/example",
        "commit_sha": "a" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "b" * 64,
        "tree_sha256": "c" * 64,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def test_locked_node_plan_is_declarative_and_deterministic(tmp_path: Path) -> None:
    manifest = _manifest()
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "example",
                "scripts": {"build": "vite build"},
                "devDependencies": {"vite": "^7.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "vite.config.js").write_text("export default {}", encoding="utf-8")

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.strategy == "node_package_manager"
    assert plan.package_manager == "npm"
    assert plan.status == "ready_for_review"
    assert [step.argv for step in plan.steps] == [
        ("npm", "ci"),
        ("npm", "run", "build"),
    ]
    assert plan.expected_outputs == ("dist/",)
    assert plan.requested_build_permissions == (
        "build.network.dependencies",
        "build.process.execute",
        "build.workspace.write",
    )
    assert plan.to_dict()["plan_sha256"] == plan.sha256()

    repeated = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))
    assert repeated.sha256() == plan.sha256()
    assert repeated.source_snapshot_sha256 == plan.source_snapshot_sha256


def test_unlocked_node_plan_requires_review(tmp_path: Path) -> None:
    manifest = _manifest()
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "example", "scripts": {"build": "custom-build"}}),
        encoding="utf-8",
    )

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.status == "review_required"
    assert plan.steps[0].argv == ("npm", "install")
    assert plan.steps[1].argv == ("npm", "run", "build")
    assert plan.expected_outputs == ()


def test_static_web_source_requires_no_execution(tmp_path: Path) -> None:
    manifest = _manifest(runtime="static_web", target="index.html")
    (tmp_path / "index.html").write_text("<html>phi</html>", encoding="utf-8")

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.status == "no_build_required"
    assert plan.strategy == "static_web_source"
    assert plan.steps == ()
    assert plan.requested_build_permissions == ()
    assert plan.expected_outputs == ("index.html",)


def test_python_plan_proposes_pep517_wheel_without_execution(tmp_path: Path) -> None:
    manifest = _manifest(runtime="python", target="pyproject.toml")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.strategy == "python_pep517_wheel"
    assert plan.steps[0].argv == (
        "python",
        "-m",
        "build",
        "--wheel",
        "--outdir",
        ".phios-build/out",
        ".",
    )
    assert plan.expected_outputs == (".phios-build/out/*.whl",)


def test_native_cargo_plan_uses_locked_release_build(tmp_path: Path) -> None:
    manifest = _manifest(runtime="native", target="Cargo.toml")
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "Cargo.lock").write_text("# lock", encoding="utf-8")

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.strategy == "rust_cargo_release"
    assert plan.status == "ready_for_review"
    assert plan.steps[0].argv == ("cargo", "build", "--release", "--locked")


def test_ambiguous_native_families_fail_to_review_only(tmp_path: Path) -> None:
    manifest = _manifest(runtime="native", target="Cargo.toml")
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
    (tmp_path / "go.mod").write_text("module example\n")

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.status == "review_required"
    assert plan.strategy == "native_ambiguous_build_family"
    assert plan.steps == ()


def test_receipt_binding_mismatch_is_blocked(tmp_path: Path) -> None:
    manifest = _manifest(runtime="static_web", target="index.html")
    (tmp_path / "index.html").write_text("x")
    receipt = _receipt(tmp_path, manifest)
    receipt["commit_sha"] = "d" * 40

    with pytest.raises(ValueError, match="commit does not match"):
        plan_build_from_payloads(_intake(manifest), receipt)


def test_source_count_mutation_after_receipt_is_blocked(tmp_path: Path) -> None:
    manifest = _manifest(runtime="static_web", target="index.html")
    (tmp_path / "index.html").write_text("x")
    receipt = _receipt(tmp_path, manifest)
    (tmp_path / "later.txt").write_text("mutation")

    with pytest.raises(ValueError, match="file count"):
        plan_build_from_payloads(_intake(manifest), receipt)


def test_source_snapshot_changes_when_same_size_bytes_change(tmp_path: Path) -> None:
    manifest = _manifest(runtime="static_web", target="index.html")
    target = tmp_path / "index.html"
    target.write_text("AAAA")
    receipt = _receipt(tmp_path, manifest)

    first = plan_build_from_payloads(_intake(manifest), receipt)
    target.write_text("BBBB")
    second = plan_build_from_payloads(_intake(manifest), receipt)

    assert first.source_file_count == second.source_file_count
    assert first.source_total_bytes == second.source_total_bytes
    assert first.source_snapshot_sha256 != second.source_snapshot_sha256
    assert first.sha256() != second.sha256()


def test_symlink_in_acquired_workspace_is_rejected(tmp_path: Path) -> None:
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlink API unavailable")
    manifest = _manifest(runtime="static_web", target="index.html")
    (tmp_path / "index.html").write_text("x")
    receipt = _receipt(tmp_path, manifest)
    external = tmp_path.parent / "external-build-plan-test.txt"
    external.write_text("outside")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")

    receipt["file_count"] = 2
    receipt["total_bytes"] = 8
    with pytest.raises(ValueError, match="symlink"):
        plan_build_from_payloads(_intake(manifest), receipt)


def test_build_plan_digest_detects_tampering(tmp_path: Path) -> None:
    manifest = _manifest(runtime="static_web", target="index.html")
    (tmp_path / "index.html").write_text("x")
    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))
    payload = plan.to_dict()

    reconstructed = BuildPlan.from_dict(payload)
    assert reconstructed == plan

    payload["strategy"] = "tampered"
    with pytest.raises(ValueError, match="digest"):
        BuildPlan.from_dict(payload)


def test_review_surface_exposes_plan_and_source_snapshot_digests(tmp_path: Path) -> None:
    manifest = _manifest(runtime="static_web", target="index.html")
    (tmp_path / "index.html").write_text("x")
    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    review = review_build_plan(plan.to_dict())

    assert review.plan_sha256 == plan.sha256()
    assert review.source_snapshot_sha256 == plan.source_snapshot_sha256
    assert review.steps == ()


def test_plan_does_not_execute_package_script(tmp_path: Path) -> None:
    manifest = _manifest()
    marker = tmp_path / "SHOULD_NOT_EXIST"
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "example",
                "scripts": {"build": f"touch {marker}"},
            }
        ),
        encoding="utf-8",
    )

    plan = plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))

    assert plan.steps[-1].argv == ("npm", "run", "build")
    assert not marker.exists()
    package_observation = next(item for item in plan.observed_files if item.path == "package.json")
    assert package_observation.sha256 == hashlib.sha256(
        (tmp_path / "package.json").read_bytes()
    ).hexdigest()
