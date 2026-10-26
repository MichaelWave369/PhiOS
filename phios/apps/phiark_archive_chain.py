"""PhiARK R1.1: offline byte-level source archive and installed receipt cross-check.

No download, installation, launch, network call or authority grant. Provided ZIP bytes
are not independently authenticated as GitHub's exact commit; the output records
a local-consistency proof and deliberately preserves that distinction.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .acquisition import (
    SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION,
    SourceTreeEntry,
    _normalized_mode,
    _safe_relative_member,
    _tree_digest,
)
from .build_plan import AcquisitionBinding, SourceSnapshotEntry
from .package_install import AppInstallReceipt, SuccessfulBuildBinding
from .phiark_source_lineage import review_phiark_source_lineage
from .phiark_service_plan import APP_ID, SOURCE

_MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 8192
_MAX_FILES = 4096
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 128 * 1024 * 1024


def verify_archive_bytes(archive: bytes) -> dict[str, Any]:
    """Inspect an in-memory GitHub-style ZIP using PhiOS acquisition path rules."""
    if not isinstance(archive, bytes) or not 0 < len(archive) <= _MAX_ARCHIVE_BYTES:
        raise ValueError("PhiARK source archive must be bounded ZIP bytes")
    entries: list[SourceTreeEntry] = []
    seen: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            members = zf.infolist()
            if not members or len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ValueError("PhiARK archive has an invalid member count")
            root = PurePosixPath(members[0].filename)
            if not root.parts:
                raise ValueError("PhiARK archive has no top-level directory")
            prefix = root.parts[0]
            for member in members:
                relative = _safe_relative_member(member, prefix)
                mode = _normalized_mode(member)
                if relative is None:
                    continue
                path = relative.as_posix()
                if path in seen:
                    raise ValueError("PhiARK archive contains duplicate paths")
                seen.add(path)
                if member.is_dir():
                    continue
                if member.file_size > _MAX_FILE_BYTES or len(entries) >= _MAX_FILES:
                    raise ValueError("PhiARK archive file count or size exceeds limit")
                total += member.file_size
                if total > _MAX_TOTAL_BYTES:
                    raise ValueError("PhiARK archive uncompressed byte limit exceeded")
                data = zf.read(member)
                if len(data) != member.file_size:
                    raise ValueError("PhiARK archive member size changed during reading")
                entries.append(
                    SourceTreeEntry(
                        path=path,
                        mode=mode,
                        byte_count=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                )
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("PhiARK source archive contains invalid or unsupported ZIP data") from exc
    if not entries:
        raise ValueError("PhiARK archive contains no regular files")
    content_digest = hashlib.sha256()
    for item in sorted(entries, key=lambda x: x.path):
        content_digest.update(
            SourceSnapshotEntry(
                path=item.path, byte_count=item.byte_count, sha256=item.sha256
            ).canonical_line()
        )
    return {
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "acquisition_tree_sha256": _tree_digest(entries),
        "source_snapshot_sha256": content_digest.hexdigest(),
        "file_count": len(entries),
        "total_bytes": total,
    }


def review_phiark_archive_chain(
    install_receipt_value: dict[str, Any],
    acquisition_receipt_value: dict[str, Any],
    build_execution_receipt_value: dict[str, Any],
    offline_build_receipt_value: dict[str, Any],
    archive: bytes,
    *, install_root: Path, data_directory: Path, expected_commit: str,
) -> dict[str, Any]:
    """Compare actual ZIP bytes through native PhiOS acquisition/build/install hashes.

    Even complete agreement here is not an independent GitHub provenance claim.
    """
    installed = review_phiark_source_lineage(
        install_receipt_value,
        install_root=install_root, data_directory=data_directory,
        expected_commit=expected_commit,
    )
    acquisition = AcquisitionBinding.from_dict(acquisition_receipt_value)
    if acquisition_receipt_value.get("schema_version") != SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION:
        raise ValueError("PhiARK acquisition has an unsupported receipt schema")
    receipt = AppInstallReceipt.from_dict(install_receipt_value)
    build = SuccessfulBuildBinding.from_payloads(
        build_execution_receipt_value,
        offline_build_receipt_value,
    )
    inspection = verify_archive_bytes(archive)
    required = {
        "acquisition identity": acquisition.app_id == APP_ID
                                and acquisition.repository_url == SOURCE
                                and acquisition.commit_sha == expected_commit,
        "acquisition manifest": acquisition.manifest_sha256 == receipt.manifest_sha256,
        "acquired ZIP hash": inspection["archive_sha256"] == acquisition.archive_sha256,
        "acquisition tree digest": inspection["acquisition_tree_sha256"] == acquisition.acquisition_tree_sha256,
        "acquisition counts": inspection["file_count"] == acquisition.file_count
                              and inspection["total_bytes"] == acquisition.total_bytes,
        "build identity": build.app_id == APP_ID and build.repository_url == SOURCE
                          and build.commit_sha == expected_commit,
        "build acquired tree": build_execution_receipt_value["acquisition_tree_sha256"]
                               == acquisition.acquisition_tree_sha256,
        "build source snapshot": build.source_snapshot_sha256 == inspection["source_snapshot_sha256"],
        "build acquisition workspace": Path(
            build_execution_receipt_value["source_workspace_path"]
        ) == acquisition.workspace_path,
        "build receipt": build.execution_receipt_sha256 == receipt.execution_receipt_sha256,
        "offline receipt": build.offline_build_receipt_sha256 == receipt.offline_build_receipt_sha256,
        "package artifacts": build.artifact_set_sha256 == receipt.artifact_set_sha256,
        "package build plan": build.build_plan_sha256 == receipt.build_plan_sha256,
    }
    problems = sorted(label for label, passed in required.items() if not passed)
    if problems:
        raise ValueError("PhiARK source/archive/install evidence mismatch: " + ", ".join(problems))
    report: dict[str, Any] = {
        "schema": "phios.phiark_archive_chain.v0.1",
        "status": "ARCHIVE_BYTES_MATCHED_LOCAL_RECEIPTS",
        "app_id": APP_ID,
        "repository_url": SOURCE,
        "source_commit_claim": expected_commit,
        "archive_sha256": inspection["archive_sha256"],
        "acquisition_tree_sha256": inspection["acquisition_tree_sha256"],
        "source_snapshot_sha256": inspection["source_snapshot_sha256"],
        "installed_tree_sha256": receipt.installed_tree_sha256,
        "installed_lineage_review_sha256": installed["review_sha256"],
        "source_archive_bytes_matched_local_receipt": True,
        "acquisition_build_install_crosschecked": True,
        "source_authenticated_against_github": False,
        "build_toolchain_attested": False,
        "physical_network_isolation_qualified": False,
        "service_supervised": False,
        "offline_cold_start_verified": False,
        "install_authority": False,
        "launch_authority": False,
        "gateway_authority": False,
    }
    report["review_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report
