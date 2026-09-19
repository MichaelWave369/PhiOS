from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from .intake import GitHubRepositoryRef
from .manifest import AppManifest

SOURCE_ACQUISITION_REQUEST_SCHEMA_VERSION = "phios.source_acquisition_request.v0.1"
SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION = "phios.source_acquisition_receipt.v0.1"

_MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
_MAX_FILES = 4096
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _require_string(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


@dataclass(frozen=True)
class SourceAcquisitionRequest:
    repository_url: str
    commit_sha: str
    manifest: AppManifest
    approved_commit_sha: str
    approved_manifest_sha256: str
    schema_version: str = SOURCE_ACQUISITION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_ACQUISITION_REQUEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported source acquisition request schema: {self.schema_version}")
        ref = GitHubRepositoryRef.parse(self.repository_url)
        manifest_ref = GitHubRepositoryRef.parse(self.manifest.source.repository_url)
        if ref.repository_url.lower() != manifest_ref.repository_url.lower():
            raise ValueError("Acquisition repository does not match manifest source repository")
        if not _SHA_RE.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a 40-64 character hexadecimal commit identifier")
        if not _SHA_RE.fullmatch(self.approved_commit_sha):
            raise ValueError(
                "approved_commit_sha must be a 40-64 character hexadecimal commit identifier"
            )
        if self.commit_sha.lower() != self.approved_commit_sha.lower():
            raise ValueError("Approved commit SHA does not match the intake evidence commit")
        if not _SHA256_RE.fullmatch(self.approved_manifest_sha256):
            raise ValueError("approved_manifest_sha256 must be a lowercase SHA-256 digest")
        actual = self.manifest.sha256()
        if actual != self.approved_manifest_sha256:
            raise ValueError("Approved manifest digest does not match the manifest candidate")

    @classmethod
    def from_intake_payload(
        cls,
        value: Any,
        *,
        approved_commit_sha: str,
        approved_manifest_sha256: str,
    ) -> SourceAcquisitionRequest:
        payload = _require_dict(value, "intake result")
        evidence = _require_dict(payload.get("evidence"), "intake result evidence")
        proposal = _require_dict(payload.get("proposal"), "intake result proposal")
        manifest_value = payload.get("manifest_candidate")
        if manifest_value is None:
            raise ValueError("Intake result does not contain a manifest candidate")

        status = proposal.get("status")
        if status not in {"declared_manifest", "inferred_candidate"}:
            raise ValueError(f"Intake proposal status is not acquirable: {status}")

        manifest = AppManifest.from_dict(manifest_value)
        repository_url = _require_string(
            evidence.get("repository_url"),
            "intake evidence repository_url",
        )
        commit_sha = _require_string(evidence.get("head_sha"), "intake evidence head_sha", maximum=64)

        proposal_url = _require_string(
            proposal.get("repository_url"),
            "intake proposal repository_url",
        )
        if GitHubRepositoryRef.parse(repository_url).repository_url.lower() != (
            GitHubRepositoryRef.parse(proposal_url).repository_url.lower()
        ):
            raise ValueError("Intake proposal repository does not match intake evidence repository")

        proposal_app_id = proposal.get("app_id")
        if proposal_app_id != manifest.app_id:
            raise ValueError("Intake proposal app_id does not match manifest candidate")

        return cls(
            repository_url=repository_url,
            commit_sha=commit_sha.lower(),
            manifest=manifest,
            approved_commit_sha=approved_commit_sha.lower(),
            approved_manifest_sha256=approved_manifest_sha256,
        )


@dataclass(frozen=True)
class DownloadedArchive:
    content: bytes
    sha256: str
    source_url: str


class SourceArchiveProvider(Protocol):
    def download(self, repository_url: str, commit_sha: str) -> DownloadedArchive: ...


class GitHubCommitArchiveProvider:
    """Download one exact GitHub commit ZIP from codeload.github.com."""

    def __init__(self, *, max_archive_bytes: int = _MAX_ARCHIVE_BYTES) -> None:
        self.max_archive_bytes = max_archive_bytes

    def download(self, repository_url: str, commit_sha: str) -> DownloadedArchive:
        ref = GitHubRepositoryRef.parse(repository_url)
        if not _SHA_RE.fullmatch(commit_sha):
            raise ValueError("commit_sha must be a 40-64 character hexadecimal commit identifier")

        owner = urllib.parse.quote(ref.owner, safe="")
        name = urllib.parse.quote(ref.name, safe="")
        sha = urllib.parse.quote(commit_sha.lower(), safe="")
        url = f"https://codeload.github.com/{owner}/{name}/zip/{sha}"

        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "PhiOS-Source-Acquisition/0.27"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                final_url = response.geturl()
                final = urlsplit(final_url)
                if final.scheme != "https" or final.hostname != "codeload.github.com":
                    raise ValueError("GitHub archive download redirected outside codeload.github.com")
                content = response.read(self.max_archive_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"GitHub archive download returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"GitHub archive download failed: {exc.reason}") from exc

        if len(content) > self.max_archive_bytes:
            raise ValueError("GitHub archive exceeds the bounded download size")
        return DownloadedArchive(
            content=content,
            sha256=hashlib.sha256(content).hexdigest(),
            source_url=url,
        )


@dataclass(frozen=True)
class SourceTreeEntry:
    path: str
    mode: int
    byte_count: int
    sha256: str

    def canonical_line(self) -> bytes:
        return (
            f"{self.path}\0{self.mode:o}\0{self.byte_count}\0{self.sha256}\n"
        ).encode("utf-8")


@dataclass(frozen=True)
class SourceAcquisitionReceipt:
    schema_version: str
    receipt_id: str
    timestamp_utc: str
    app_id: str
    repository_url: str
    commit_sha: str
    manifest_sha256: str
    archive_sha256: str
    tree_sha256: str
    file_count: int
    total_bytes: int
    workspace_path: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _zip_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _normalized_mode(info: zipfile.ZipInfo) -> int:
    raw = _zip_mode(info)
    kind = stat.S_IFMT(raw)
    if info.is_dir():
        if kind not in {0, stat.S_IFDIR}:
            raise ValueError(f"Archive directory has unsupported file type: {info.filename}")
        return 0o755
    if kind == stat.S_IFLNK:
        raise ValueError(f"Archive symlink is not allowed: {info.filename}")
    if kind not in {0, stat.S_IFREG}:
        raise ValueError(f"Archive special file is not allowed: {info.filename}")
    executable = bool(raw & 0o111)
    return 0o755 if executable else 0o644


def _safe_relative_member(info: zipfile.ZipInfo, root_prefix: str) -> PurePosixPath | None:
    name = info.filename
    if not name or "\\" in name or "\x00" in name:
        raise ValueError("Archive contains an invalid member path")

    path = PurePosixPath(name)
    if path.is_absolute():
        raise ValueError(f"Archive contains an absolute path: {name}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Archive contains an unsafe path: {name}")
    if not path.parts or path.parts[0] != root_prefix:
        raise ValueError("Archive contains multiple or unexpected top-level roots")
    if len(path.parts) == 1:
        return None
    relative = PurePosixPath(*path.parts[1:])
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"Archive contains an unsafe relative path: {name}")
    return relative


def _tree_digest(entries: list[SourceTreeEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item.path):
        digest.update(entry.canonical_line())
    return digest.hexdigest()


def _write_receipt(path: Path, receipt: SourceAcquisitionReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    try:
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class SourceAcquisitionService:
    """Acquire exact source bytes into a bounded workspace without building or executing them."""

    def __init__(
        self,
        *,
        provider: SourceArchiveProvider | None = None,
        max_files: int = _MAX_FILES,
        max_file_bytes: int = _MAX_FILE_BYTES,
        max_total_bytes: int = _MAX_TOTAL_UNCOMPRESSED_BYTES,
    ) -> None:
        self.provider = provider or GitHubCommitArchiveProvider()
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    def acquire(
        self,
        request: SourceAcquisitionRequest,
        *,
        workspace_root: Path,
        receipt_root: Path | None = None,
    ) -> SourceAcquisitionReceipt:
        root = workspace_root.expanduser().resolve()
        receipts = (receipt_root or (root / ".phios-receipts")).expanduser().resolve()

        app_root = (root / request.manifest.app_id).resolve()
        destination = (app_root / request.commit_sha).resolve()
        if root not in destination.parents:
            raise ValueError("Acquisition destination escaped the configured workspace root")
        if receipts == destination or destination in receipts.parents:
            raise ValueError("Receipt root must remain outside the acquired source tree")
        if destination.exists():
            raise ValueError("Acquisition destination already exists")

        archive = self.provider.download(request.repository_url, request.commit_sha)
        staging = (root / f".acquire-{request.manifest.app_id}-{uuid.uuid4().hex}").resolve()
        if root not in staging.parents:
            raise ValueError("Acquisition staging path escaped the configured workspace root")

        entries: list[SourceTreeEntry] = []
        total_bytes = 0
        try:
            staging.mkdir(parents=True, exist_ok=False)
            with zipfile.ZipFile(io.BytesIO(archive.content)) as source_zip:
                infos = source_zip.infolist()
                if not infos:
                    raise ValueError("Source archive is empty")
                first = PurePosixPath(infos[0].filename)
                if not first.parts:
                    raise ValueError("Source archive has no top-level root")
                root_prefix = first.parts[0]

                seen: set[str] = set()
                file_count = 0
                for info in infos:
                    relative = _safe_relative_member(info, root_prefix)
                    mode = _normalized_mode(info)
                    if relative is None:
                        continue

                    relative_text = relative.as_posix()
                    target = (staging / Path(*relative.parts)).resolve()
                    if staging != target and staging not in target.parents:
                        raise ValueError(f"Archive member escaped staging root: {info.filename}")

                    if relative_text in seen:
                        raise ValueError(f"Archive contains duplicate path: {relative_text}")
                    seen.add(relative_text)

                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue

                    file_count += 1
                    if file_count > self.max_files:
                        raise ValueError(f"Source archive exceeds {self.max_files} files")
                    if info.file_size > self.max_file_bytes:
                        raise ValueError(
                            f"Archive member exceeds {self.max_file_bytes} bytes: {relative_text}"
                        )
                    total_bytes += info.file_size
                    if total_bytes > self.max_total_bytes:
                        raise ValueError(
                            f"Source archive exceeds {self.max_total_bytes} uncompressed bytes"
                        )

                    target.parent.mkdir(parents=True, exist_ok=True)
                    payload = source_zip.read(info)
                    if len(payload) != info.file_size:
                        raise ValueError(f"Archive member size mismatch: {relative_text}")
                    target.write_bytes(payload)
                    try:
                        os.chmod(target, mode)
                    except OSError:
                        pass
                    entries.append(
                        SourceTreeEntry(
                            path=relative_text,
                            mode=mode,
                            byte_count=len(payload),
                            sha256=hashlib.sha256(payload).hexdigest(),
                        )
                    )

            if not entries:
                raise ValueError("Source archive contains no regular files")

            tree_sha256 = _tree_digest(entries)
            app_root.mkdir(parents=True, exist_ok=True)
            staging.replace(destination)

            receipt = SourceAcquisitionReceipt(
                schema_version=SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION,
                receipt_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(UTC).isoformat(),
                app_id=request.manifest.app_id,
                repository_url=request.repository_url,
                commit_sha=request.commit_sha,
                manifest_sha256=request.manifest.sha256(),
                archive_sha256=archive.sha256,
                tree_sha256=tree_sha256,
                file_count=len(entries),
                total_bytes=sum(item.byte_count for item in entries),
                workspace_path=str(destination),
                status="acquired",
            )
            receipt_path = receipts / f"{receipt.receipt_id}.json"
            try:
                _write_receipt(receipt_path, receipt)
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                raise
            return receipt
        except zipfile.BadZipFile as exc:
            raise ValueError("Downloaded source archive is not a valid ZIP file") from exc
        except (RuntimeError, NotImplementedError) as exc:
            raise ValueError("Downloaded source archive uses an unsupported ZIP feature") from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
