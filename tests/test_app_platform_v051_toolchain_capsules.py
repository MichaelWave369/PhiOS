from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_plan import plan_build_from_payloads
from phios.apps.manifest import AppManifest
from phios.apps.toolchain_capsule import (
    ToolchainBinding,
    ToolchainCapsule,
    ToolchainRequirement,
    ToolchainTool,
    bind_toolchain_capsule,
    derive_toolchain_requirement,
)


def _manifest(runtime: str = "node", target: str = "package.json") -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.toolchain-example",
            "name": "Toolchain Example",
            "version": "1.0.0",
            "description": "Toolchain capsule contract test",
            "source": {
                "repository_url": "https://github.com/example/toolchain-example",
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
            "repository_url": manifest.source.repository_url,
            "head_sha": "a" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": manifest.source.repository_url,
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }


def _receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-10-04T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": manifest.source.repository_url,
        "commit_sha": "a" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "b" * 64,
        "tree_sha256": "c" * 64,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def _plan(tmp_path: Path, family: str):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if family == "node_npm":
        manifest = _manifest()
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "example", "scripts": {"build": "vite build"}})
        )
        (tmp_path / "package-lock.json").write_text("{}")
        (tmp_path / "vite.config.js").write_text("export default {}")
    elif family == "node_pnpm":
        manifest = _manifest()
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "example",
                    "packageManager": "pnpm@10.0.0",
                    "scripts": {"build": "vite build"},
                }
            )
        )
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
        (tmp_path / "vite.config.js").write_text("export default {}")
    elif family == "python_pep517":
        manifest = _manifest(runtime="python", target="pyproject.toml")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "example"\nversion = "1.0.0"\n'
        )
    elif family == "rust_cargo":
        manifest = _manifest(runtime="native", target="Cargo.toml")
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "example"\nversion = "0.1.0"\n'
        )
        (tmp_path / "Cargo.lock").write_text("# lock\n")
    elif family == "go_module":
        manifest = _manifest(runtime="native", target="go.mod")
        (tmp_path / "go.mod").write_text("module example\n")
        (tmp_path / "go.sum").write_text("example.invalid/mod v1.0.0 h1:abc\n")
    elif family == "static":
        manifest = _manifest(runtime="static_web", target="index.html")
        (tmp_path / "index.html").write_text("<html>phi</html>")
    else:
        raise AssertionError(family)
    return plan_build_from_payloads(_intake(manifest), _receipt(tmp_path, manifest))


@pytest.mark.parametrize(
    ("family", "expected", "tools"),
    [
        ("node_npm", "node_npm", ("node", "npm")),
        ("python_pep517", "python_pep517", ("python", "python-build")),
        ("rust_cargo", "rust_cargo", ("cargo", "rustc")),
        ("go_module", "go_module", ("go",)),
    ],
)
def test_supported_build_plans_derive_zero_authority_capsule_requirements(
    tmp_path: Path, family: str, expected: str, tools: tuple[str, ...]
) -> None:
    plan = _plan(tmp_path, family)
    requirement = derive_toolchain_requirement(plan)

    assert requirement.status == "capsule_required"
    assert requirement.family == expected
    assert requirement.required_tools == tools
    assert requirement.plan_sha256 == plan.sha256()
    assert requirement.execution_authority is False


def test_pnpm_is_explicitly_unsupported_in_v051(tmp_path: Path) -> None:
    requirement = derive_toolchain_requirement(_plan(tmp_path, "node_pnpm"))

    assert requirement.status == "unsupported_toolchain"
    assert requirement.family is None
    assert requirement.required_tools == ("node", "pnpm")


def test_static_source_requires_no_capsule(tmp_path: Path) -> None:
    requirement = derive_toolchain_requirement(_plan(tmp_path, "static"))

    assert requirement.status == "no_capsule_required"
    assert requirement.family is None
    assert requirement.required_tools == ()


def _capsule(family: str = "node_npm") -> ToolchainCapsule:
    tools = {
        "node_npm": (ToolchainTool("node", "22.0.0"), ToolchainTool("npm", "10.0.0")),
        "python_pep517": (
            ToolchainTool("python", "3.11.10"),
            ToolchainTool("python-build", "1.2.2"),
        ),
        "rust_cargo": (
            ToolchainTool("cargo", "1.89.0"),
            ToolchainTool("rustc", "1.89.0"),
        ),
        "go_module": (ToolchainTool("go", "1.25.1"),),
    }[family]
    return ToolchainCapsule(
        capsule_id=f"phios.{family}.example",
        family=family,  # type: ignore[arg-type]
        platform="linux_x86_64",
        artifact_kind="oci_image",
        artifact_ref=f"registry.example/phios/{family}@sha256:" + "d" * 64,
        artifact_sha256="d" * 64,
        tools=tools,
    )


def test_capsule_round_trip_is_strict_and_digest_bound() -> None:
    capsule = _capsule()
    payload = capsule.to_dict()

    assert ToolchainCapsule.from_dict(payload) == capsule
    assert payload["execution_authority"] is False
    assert payload["network_authority"] is False
    assert payload["install_authority"] is False
    assert payload["host_write_authority"] is False

    payload["artifact_ref"] = "registry.example/tampered"
    with pytest.raises(ValueError, match="digest"):
        ToolchainCapsule.from_dict(payload)


def test_capsule_rejects_missing_or_extra_family_tools() -> None:
    with pytest.raises(ValueError, match="must declare exactly"):
        ToolchainCapsule(
            capsule_id="phios.node.bad",
            family="node_npm",
            platform="linux_x86_64",
            artifact_kind="oci_image",
            artifact_ref="registry.example/node",
            artifact_sha256="d" * 64,
            tools=(ToolchainTool("node", "22.0.0"),),
        )


def test_capsule_rejects_authority_smuggling() -> None:
    with pytest.raises(ValueError, match="authority fields"):
        ToolchainCapsule(
            capsule_id="phios.node.bad-authority",
            family="node_npm",
            platform="linux_x86_64",
            artifact_kind="oci_image",
            artifact_ref="registry.example/node",
            artifact_sha256="d" * 64,
            tools=(ToolchainTool("node", "22.0.0"), ToolchainTool("npm", "10.0.0")),
            execution_authority=True,
        )


def test_matching_capsule_creates_review_only_binding(tmp_path: Path) -> None:
    requirement = derive_toolchain_requirement(_plan(tmp_path, "node_npm"))
    capsule = _capsule()

    binding = bind_toolchain_capsule(requirement, capsule)

    assert binding.status == "compatible_for_review"
    assert binding.requirement_sha256 == requirement.sha256()
    assert binding.capsule_sha256 == capsule.sha256()
    assert binding.execution_authority is False
    assert binding.network_authority is False
    assert binding.install_authority is False
    assert binding.host_write_authority is False
    assert ToolchainBinding.from_dict(binding.to_dict()) == binding


def test_cross_family_binding_is_rejected(tmp_path: Path) -> None:
    requirement = derive_toolchain_requirement(_plan(tmp_path, "python_pep517"))

    with pytest.raises(ValueError, match="family"):
        bind_toolchain_capsule(requirement, _capsule("node_npm"))


def test_no_build_and_unsupported_requirements_cannot_bind(tmp_path: Path) -> None:
    no_build = derive_toolchain_requirement(_plan(tmp_path / "static", "static"))
    unsupported = derive_toolchain_requirement(_plan(tmp_path / "pnpm", "node_pnpm"))

    with pytest.raises(ValueError, match="capsule_required"):
        bind_toolchain_capsule(no_build, _capsule())
    with pytest.raises(ValueError, match="capsule_required"):
        bind_toolchain_capsule(unsupported, _capsule())


def test_requirement_round_trip_rejects_unknown_fields(tmp_path: Path) -> None:
    requirement = derive_toolchain_requirement(_plan(tmp_path, "node_npm"))
    payload = requirement.to_dict()

    assert ToolchainRequirement.from_dict(payload) == requirement
    payload["surprise_authority"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        ToolchainRequirement.from_dict(payload)
