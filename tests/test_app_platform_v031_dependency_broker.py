from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_plan import plan_build_from_payloads
from phios.apps.dependency_broker import (
    DependencyPlan,
    DependencyReceipt,
    DependencyStageRequest,
    DependencyStagingService,
    review_dependency_plan,
    plan_npm_dependencies,
)
from phios.apps.manifest import AppManifest


def _manifest() -> AppManifest:
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
            "entrypoint": {"runtime": "node", "target": "package.json"},
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


def _receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
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
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def _sri(content: bytes, algorithm: str = "sha512") -> str:
    digest = hashlib.new(algorithm, content).digest()
    return f"{algorithm}-{base64.b64encode(digest).decode('ascii')}"


def _write_project(
    root: Path,
    *,
    artifact_bytes: bytes = b"package-one",
    second_bytes: bytes | None = None,
    lockfile_version: int = 3,
    resolved_url: str = "https://registry.npmjs.org/dep-one/-/dep-one-1.0.0.tgz",
    integrity: str | None = None,
    padding: int = 0,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    package = {
        "name": "example",
        "scripts": {"build": "vite build"},
        "devDependencies": {"vite": "^7.0.0"},
    }
    (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
    (root / "vite.config.js").write_text("export default {}", encoding="utf-8")

    first_integrity = integrity or _sri(artifact_bytes)
    packages: dict[str, Any] = {
        "": {"name": "example", "version": "1.0.0"},
        "node_modules/dep-one": {
            "version": "1.0.0",
            "resolved": resolved_url,
            "integrity": first_integrity,
        },
    }
    downloads = {resolved_url: artifact_bytes}
    if second_bytes is not None:
        second_url = "https://registry.npmjs.org/dep-two/-/dep-two-2.0.0.tgz"
        packages["node_modules/dep-two"] = {
            "version": "2.0.0",
            "resolved": second_url,
            "integrity": _sri(second_bytes),
        }
        downloads[second_url] = second_bytes

    lock: dict[str, Any] = {
        "name": "example",
        "version": "1.0.0",
        "lockfileVersion": lockfile_version,
        "requires": True,
        "packages": packages,
    }
    if padding:
        lock["phios_test_padding"] = "x" * padding

    (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return lock, downloads


def _plan(root: Path, **kwargs: Any) -> tuple[dict[str, Any], Any, dict[str, bytes]]:
    manifest = _manifest()
    _, downloads = _write_project(root, **kwargs)
    receipt = _receipt(root, manifest)
    build_plan = plan_build_from_payloads(_intake(manifest), receipt)
    assert build_plan.status == "ready_for_review"
    dependency_plan = plan_npm_dependencies(build_plan.to_dict(), receipt)
    return receipt, dependency_plan, downloads


class FakeDownloader:
    def __init__(self, mapping: dict[str, bytes]) -> None:
        self.mapping = mapping
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def download(self, artifact: Any, *, approved_hosts: tuple[str, ...]) -> bytes:
        self.calls.append((artifact.resolved_url, approved_hosts))
        return self.mapping[artifact.resolved_url]


def _request(plan: Any) -> DependencyStageRequest:
    return DependencyStageRequest.from_payload(
        plan.to_dict(),
        approved_dependency_plan_sha256=plan.sha256(),
        approved_hosts=plan.allowed_hosts,
    )


def test_dependency_plan_binds_build_source_lockfile_and_hosts(tmp_path: Path) -> None:
    _, plan, _ = _plan(tmp_path)

    assert plan.package_manager == "npm"
    assert plan.lockfile_path == "package-lock.json"
    assert plan.lockfile_version == 3
    assert plan.allowed_hosts == ("registry.npmjs.org",)
    assert len(plan.artifacts) == 1
    assert plan.artifacts[0].host == "registry.npmjs.org"
    assert plan.artifacts[0].lock_keys == ("node_modules/dep-one",)
    assert plan.to_dict()["dependency_plan_sha256"] == plan.sha256()


def test_review_surface_exposes_exact_stage_approval_values(tmp_path: Path) -> None:
    _, plan, _ = _plan(tmp_path)
    review = review_dependency_plan(plan.to_dict())

    assert review.dependency_plan_sha256 == plan.sha256()
    assert review.build_plan_sha256 == plan.build_plan_sha256
    assert review.source_snapshot_sha256 == plan.source_snapshot_sha256
    assert review.lockfile_sha256 == plan.lockfile_sha256
    assert review.artifact_count == 1
    assert review.allowed_hosts == ("registry.npmjs.org",)


def test_dependency_plan_tampering_is_rejected(tmp_path: Path) -> None:
    _, plan, _ = _plan(tmp_path)
    payload = plan.to_dict()
    payload["allowed_hosts"] = ["evil.example"]

    with pytest.raises(ValueError):
        DependencyPlan.from_dict(payload)


def test_stage_requires_exact_plan_digest_and_exact_host_set(tmp_path: Path) -> None:
    _, plan, _ = _plan(tmp_path)

    with pytest.raises(ValueError, match="Approved dependency plan"):
        DependencyStageRequest.from_payload(
            plan.to_dict(),
            approved_dependency_plan_sha256="0" * 64,
            approved_hosts=plan.allowed_hosts,
        )

    with pytest.raises(ValueError, match="exactly match"):
        DependencyStageRequest.from_payload(
            plan.to_dict(),
            approved_dependency_plan_sha256=plan.sha256(),
            approved_hosts=("registry.npmjs.org", "extra.example"),
        )


def test_staging_verifies_sri_and_writes_cas_and_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan, downloads = _plan(source)
    downloader = FakeDownloader(downloads)

    receipt = DependencyStagingService(downloader=downloader).stage(
        _request(plan),
        store_root=tmp_path / "store",
    )

    assert receipt.dependency_plan_sha256 == plan.sha256()
    assert receipt.build_plan_sha256 == plan.build_plan_sha256
    assert receipt.source_snapshot_sha256 == plan.source_snapshot_sha256
    assert receipt.approved_hosts == plan.allowed_hosts
    assert len(receipt.artifacts) == 1
    artifact = receipt.artifacts[0]
    assert artifact.byte_count == len(b"package-one")
    assert artifact.sha256 == hashlib.sha256(b"package-one").hexdigest()
    assert Path(artifact.cas_path).read_bytes() == b"package-one"

    receipts = list((tmp_path / "store" / ".phios-receipts").glob("dependency-*.json"))
    assert len(receipts) == 1
    persisted = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert persisted["dependency_receipt_sha256"] == receipt.sha256()
    parsed = DependencyReceipt.from_dict(persisted)
    assert parsed == receipt
    assert parsed.repository_url == "https://github.com/example/example"
    assert parsed.package_manager == "npm"
    assert parsed.lockfile_version == 3
    assert downloader.calls == [
        (
            "https://registry.npmjs.org/dep-one/-/dep-one-1.0.0.tgz",
            ("registry.npmjs.org",),
        )
    ]


def test_bad_download_bytes_fail_integrity_before_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan, downloads = _plan(source)
    wrong = {url: b"tampered" for url in downloads}

    with pytest.raises(ValueError, match="SRI integrity"):
        DependencyStagingService(downloader=FakeDownloader(wrong)).stage(
            _request(plan),
            store_root=tmp_path / "store",
        )

    assert not (tmp_path / "store" / ".phios-receipts").exists()


def test_source_drift_blocks_dependency_planning(tmp_path: Path) -> None:
    manifest = _manifest()
    _write_project(tmp_path)
    receipt = _receipt(tmp_path, manifest)
    build_plan = plan_build_from_payloads(_intake(manifest), receipt)
    (tmp_path / "package.json").write_text('{"name":"changed"}', encoding="utf-8")

    with pytest.raises(ValueError, match="Source snapshot changed"):
        plan_npm_dependencies(build_plan.to_dict(), receipt)


def test_lockfile_digest_drift_is_detected_even_when_build_plan_payload_is_valid(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    lock, _ = _write_project(tmp_path)
    receipt = _receipt(tmp_path, manifest)
    build_plan = plan_build_from_payloads(_intake(manifest), receipt)
    lock["phios_mutation"] = True
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")

    with pytest.raises(ValueError):
        plan_npm_dependencies(build_plan.to_dict(), receipt)


def test_http_credentials_query_and_fragment_are_rejected(tmp_path: Path) -> None:
    bad_urls = (
        "http://registry.npmjs.org/a/-/a.tgz",
        "https://user:pass@registry.npmjs.org/a/-/a.tgz",
        "https://registry.npmjs.org/a/-/a.tgz?token=secret",
        "https://registry.npmjs.org/a/-/a.tgz#fragment",
    )
    for index, url in enumerate(bad_urls):
        root = tmp_path / str(index)
        root.mkdir()
        manifest = _manifest()
        _write_project(root, resolved_url=url)
        receipt = _receipt(root, manifest)
        build_plan = plan_build_from_payloads(_intake(manifest), receipt)
        with pytest.raises(ValueError):
            plan_npm_dependencies(build_plan.to_dict(), receipt)


def test_lockfile_requires_exact_resolved_and_integrity_evidence(tmp_path: Path) -> None:
    manifest = _manifest()
    lock, _ = _write_project(tmp_path)
    del lock["packages"]["node_modules/dep-one"]["integrity"]
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    receipt = _receipt(tmp_path, manifest)
    build_plan = plan_build_from_payloads(_intake(manifest), receipt)

    with pytest.raises(ValueError, match="incomplete resolved/integrity"):
        plan_npm_dependencies(build_plan.to_dict(), receipt)


def test_lockfile_version_one_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    _write_project(tmp_path, lockfile_version=1)
    receipt = _receipt(tmp_path, manifest)
    build_plan = plan_build_from_payloads(_intake(manifest), receipt)

    with pytest.raises(ValueError, match="lockfileVersion 2 or 3"):
        plan_npm_dependencies(build_plan.to_dict(), receipt)


def test_strongest_supported_sri_digest_is_selected(tmp_path: Path) -> None:
    content = b"strongest"
    integrity = f"{_sri(content, 'sha256')} {_sri(content, 'sha512')}"
    _, plan, _ = _plan(tmp_path, artifact_bytes=content, integrity=integrity)

    assert plan.artifacts[0].integrity_algorithm == "sha512"


def test_two_artifacts_with_same_bytes_share_content_address(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    same = b"same-package-bytes"
    _, plan, downloads = _plan(source, artifact_bytes=same, second_bytes=same)
    receipt = DependencyStagingService(downloader=FakeDownloader(downloads)).stage(
        _request(plan),
        store_root=tmp_path / "store",
    )

    assert len(receipt.artifacts) == 2
    assert receipt.artifacts[0].sha256 == receipt.artifacts[1].sha256
    assert receipt.artifacts[0].cas_path == receipt.artifacts[1].cas_path
    assert len(list((tmp_path / "store" / "cas" / "sha256").rglob("*.blob"))) == 1


def test_build_planning_accepts_lockfile_larger_than_old_256k_limit(tmp_path: Path) -> None:
    manifest = _manifest()
    _write_project(tmp_path, padding=300_000)
    receipt = _receipt(tmp_path, manifest)

    build_plan = plan_build_from_payloads(_intake(manifest), receipt)

    observed = {item.path: item.byte_count for item in build_plan.observed_files}
    assert observed["package-lock.json"] > 262_144
    dependency_plan = plan_npm_dependencies(build_plan.to_dict(), receipt)
    assert dependency_plan.lockfile_sha256 == hashlib.sha256(
        (tmp_path / "package-lock.json").read_bytes()
    ).hexdigest()


def test_dependency_receipt_tampering_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan, downloads = _plan(source)
    receipt = DependencyStagingService(downloader=FakeDownloader(downloads)).stage(
        _request(plan),
        store_root=tmp_path / "store",
    )
    payload = receipt.to_dict()
    payload["total_bytes"] += 1

    with pytest.raises(ValueError):
        DependencyReceipt.from_dict(payload)


def test_dependency_receipt_rejects_cas_path_escape(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan, downloads = _plan(source)
    receipt = DependencyStagingService(downloader=FakeDownloader(downloads)).stage(
        _request(plan),
        store_root=tmp_path / "store",
    )
    payload = receipt.to_dict()
    payload["artifacts"][0]["cas_path"] = str(
        (tmp_path / "outside" / f"{payload['artifacts'][0]['sha256']}.blob").resolve()
    )
    # Recompute the outer digest so path validation, not only digest validation, is exercised.
    payload_without_digest = dict(payload)
    payload_without_digest.pop("dependency_receipt_sha256")
    payload["dependency_receipt_sha256"] = hashlib.sha256(
        json.dumps(
            payload_without_digest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="escaped store root"):
        DependencyReceipt.from_dict(payload)
