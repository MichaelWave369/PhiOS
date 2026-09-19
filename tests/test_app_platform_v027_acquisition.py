from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from phios.apps.acquisition import (
    DownloadedArchive,
    SourceAcquisitionRequest,
    SourceAcquisitionService,
)
from phios.apps.manifest import AppManifest


class FakeArchiveProvider:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls: list[tuple[str, str]] = []

    def download(self, repository_url: str, commit_sha: str) -> DownloadedArchive:
        self.calls.append((repository_url, commit_sha))
        return DownloadedArchive(
            content=self.content,
            sha256=hashlib.sha256(self.content).hexdigest(),
            source_url="https://codeload.github.com/example/example/zip/commit",
        )


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


def _request() -> SourceAcquisitionRequest:
    manifest = _manifest()
    return SourceAcquisitionRequest(
        repository_url="https://github.com/example/example",
        commit_sha="a" * 40,
        manifest=manifest,
        approved_commit_sha="a" * 40,
        approved_manifest_sha256=manifest.sha256(),
    )


def _zip(files: dict[str, bytes], *, modes: dict[str, int] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("example-commit/", b"")
        for path, content in files.items():
            info = zipfile.ZipInfo(f"example-commit/{path}")
            info.create_system = 3
            mode = (modes or {}).get(path, 0o100644)
            info.external_attr = mode << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def _symlink_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("example-commit/", b"")
        info = zipfile.ZipInfo("example-commit/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"target")
    return buffer.getvalue()


def test_request_requires_explicit_manifest_digest_approval() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="does not match"):
        SourceAcquisitionRequest(
            repository_url="https://github.com/example/example",
            commit_sha="a" * 40,
            manifest=manifest,
            approved_commit_sha="a" * 40,
            approved_manifest_sha256="0" * 64,
        )


def test_request_requires_explicit_commit_approval() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="Approved commit SHA"):
        SourceAcquisitionRequest(
            repository_url="https://github.com/example/example",
            commit_sha="a" * 40,
            manifest=manifest,
            approved_commit_sha="b" * 40,
            approved_manifest_sha256=manifest.sha256(),
        )


def test_request_can_be_reconstructed_from_v026_intake_payload() -> None:
    manifest = _manifest()
    payload = {
        "evidence": {
            "repository_url": "https://github.com/example/example",
            "head_sha": "b" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": "https://github.com/example/example",
            "app_id": manifest.app_id,
        },
        "manifest_candidate": manifest.to_dict(),
    }
    request = SourceAcquisitionRequest.from_intake_payload(
        payload,
        approved_commit_sha="b" * 40,
        approved_manifest_sha256=manifest.sha256(),
    )

    assert request.commit_sha == "b" * 40
    assert request.manifest == manifest


def test_successful_acquisition_is_pinned_hashed_and_receipted(tmp_path: Path) -> None:
    content = _zip(
        {
            "package.json": b'{"name":"example"}',
            "src/index.js": b"console.log('phi')\n",
        }
    )
    provider = FakeArchiveProvider(content)
    service = SourceAcquisitionService(provider=provider)

    receipt = service.acquire(_request(), workspace_root=tmp_path)

    destination = tmp_path / "phi.example" / ("a" * 40)
    assert destination.is_dir()
    assert (destination / "package.json").read_bytes() == b'{"name":"example"}'
    assert receipt.status == "acquired"
    assert receipt.file_count == 2
    assert receipt.commit_sha == "a" * 40
    assert receipt.manifest_sha256 == _manifest().sha256()
    assert provider.calls == [("https://github.com/example/example", "a" * 40)]

    receipt_files = list((tmp_path / ".phios-receipts").glob("*.json"))
    assert len(receipt_files) == 1
    persisted = json.loads(receipt_files[0].read_text(encoding="utf-8"))
    assert persisted["tree_sha256"] == receipt.tree_sha256
    assert persisted["archive_sha256"] == hashlib.sha256(content).hexdigest()


def test_tree_hash_is_deterministic_across_zip_member_order(tmp_path: Path) -> None:
    first = _zip({"b.txt": b"B", "a.txt": b"A"})
    second = _zip({"a.txt": b"A", "b.txt": b"B"})

    one = SourceAcquisitionService(provider=FakeArchiveProvider(first)).acquire(
        _request(),
        workspace_root=tmp_path / "one",
    )
    two = SourceAcquisitionService(provider=FakeArchiveProvider(second)).acquire(
        _request(),
        workspace_root=tmp_path / "two",
    )

    assert one.tree_sha256 == two.tree_sha256


def test_archive_path_traversal_is_rejected(tmp_path: Path) -> None:
    malicious = _zip({"../escape.txt": b"nope"})
    service = SourceAcquisitionService(provider=FakeArchiveProvider(malicious))

    with pytest.raises(ValueError, match="unsafe"):
        service.acquire(_request(), workspace_root=tmp_path)

    assert not (tmp_path.parent / "escape.txt").exists()


def test_archive_symlink_is_rejected(tmp_path: Path) -> None:
    service = SourceAcquisitionService(provider=FakeArchiveProvider(_symlink_zip()))

    with pytest.raises(ValueError, match="symlink"):
        service.acquire(_request(), workspace_root=tmp_path)


def test_archive_file_count_limit_fails_closed(tmp_path: Path) -> None:
    content = _zip({"a": b"1", "b": b"2"})
    service = SourceAcquisitionService(provider=FakeArchiveProvider(content), max_files=1)

    with pytest.raises(ValueError, match="exceeds 1 files"):
        service.acquire(_request(), workspace_root=tmp_path)


def test_archive_total_byte_limit_fails_closed(tmp_path: Path) -> None:
    content = _zip({"a": b"123", "b": b"456"})
    service = SourceAcquisitionService(provider=FakeArchiveProvider(content), max_total_bytes=5)

    with pytest.raises(ValueError, match="uncompressed bytes"):
        service.acquire(_request(), workspace_root=tmp_path)


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    destination = tmp_path / "phi.example" / ("a" * 40)
    destination.mkdir(parents=True)
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    service = SourceAcquisitionService(provider=FakeArchiveProvider(_zip({"a": b"1"})))

    with pytest.raises(ValueError, match="already exists"):
        service.acquire(_request(), workspace_root=tmp_path)

    assert marker.read_text(encoding="utf-8") == "keep"
