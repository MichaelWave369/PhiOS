from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_LIFECYCLE_FILES = 4096
MAX_LIFECYCLE_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, kw_only=True)
class UnresolvedLifecycleJournal:
    app_id: str
    journal_id: str
    journal_sha256: str
    retained_cleanup_plan_sha256: str
    retained_version: str
    active_version: str
    scope: str
    journal_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "app_id": self.app_id,
            "journal_id": self.journal_id,
            "journal_sha256": self.journal_sha256,
            "retained_cleanup_plan_sha256": self.retained_cleanup_plan_sha256,
            "retained_version": self.retained_version,
            "active_version": self.active_version,
            "scope": self.scope,
            "journal_path": self.journal_path,
        }


@dataclass(frozen=True, kw_only=True)
class LifecycleGateObservation:
    app_id: str
    receipt_root: str
    unresolved: tuple[UnresolvedLifecycleJournal, ...]
    cleanup_receipts_seen: int
    reconciliation_receipts_seen: int
    mutation_authority: bool = False
    reconciliation_authority: bool = False

    @property
    def clear(self) -> bool:
        return not self.unresolved

    def to_dict(self) -> dict[str, object]:
        return {
            "app_id": self.app_id,
            "receipt_root": self.receipt_root,
            "clear": self.clear,
            "unresolved": [item.to_dict() for item in self.unresolved],
            "cleanup_receipts_seen": self.cleanup_receipts_seen,
            "reconciliation_receipts_seen": self.reconciliation_receipts_seen,
            "mutation_authority": self.mutation_authority,
            "reconciliation_authority": self.reconciliation_authority,
        }


def observe_lifecycle_gate(
    receipt_root: Path,
    *,
    app_id: str,
) -> LifecycleGateObservation:
    """Observe unresolved prepared cleanup journals for one app.

    This function is read-only. It derives gate state exclusively from existing
    v0.41/v0.42 evidence and never creates a lock or receipt.
    """

    normalized_app_id = app_id.strip()
    if not normalized_app_id:
        raise ValueError("lifecycle gate app_id must be non-empty")

    root = receipt_root.expanduser()
    if root.is_symlink():
        raise ValueError("lifecycle receipt root must not be a symlink")
    if not root.exists():
        return LifecycleGateObservation(
            app_id=normalized_app_id,
            receipt_root=str(root.resolve(strict=False)),
            unresolved=(),
            cleanup_receipts_seen=0,
            reconciliation_receipts_seen=0,
        )
    if not root.is_dir():
        raise ValueError("lifecycle receipt root must be a directory")
    root = root.resolve(strict=True)

    journal_paths = sorted(root.glob("retained-cleanup-journal-*.json"))
    cleanup_paths = sorted(
        path
        for path in root.glob("retained-cleanup-*.json")
        if not path.name.startswith("retained-cleanup-journal-")
        and not path.name.startswith("retained-cleanup-reconciliation-")
    )
    reconciliation_paths = sorted(
        root.glob("retained-cleanup-reconciliation-*.json")
    )
    if (
        len(journal_paths) + len(cleanup_paths) + len(reconciliation_paths)
        > MAX_LIFECYCLE_FILES
    ):
        raise ValueError("lifecycle receipt file count exceeds configured bound")

    # Lazy imports avoid a module cycle: retained_cleanup execution itself uses
    # this gate before it creates a new journal.
    from .cleanup_reconciliation import CleanupReconciliationReceipt
    from .retained_cleanup import RetainedCleanupJournal, RetainedCleanupReceipt

    cleanup_by_journal: set[str] = set()
    cleanup_seen = 0
    for path in cleanup_paths:
        payload = _read_json_object(path, "retained cleanup receipt")
        try:
            receipt = RetainedCleanupReceipt.from_dict(payload)
        except ValueError:
            # Invalid receipt evidence can never resolve a prepared journal.
            continue
        cleanup_seen += 1
        if receipt.app_id == normalized_app_id:
            cleanup_by_journal.add(receipt.retained_cleanup_journal_sha256)

    reconciliation_by_journal: set[str] = set()
    reconciliation_seen = 0
    for path in reconciliation_paths:
        payload = _read_json_object(path, "cleanup reconciliation receipt")
        try:
            receipt = CleanupReconciliationReceipt.from_dict(payload)
        except ValueError:
            # Invalid receipt evidence can never resolve a prepared journal.
            continue
        reconciliation_seen += 1
        if receipt.app_id == normalized_app_id:
            reconciliation_by_journal.add(receipt.retained_cleanup_journal_sha256)

    unresolved: list[UnresolvedLifecycleJournal] = []
    for path in journal_paths:
        payload = _read_json_object(path, "retained cleanup journal")
        try:
            journal = RetainedCleanupJournal.from_dict(payload)
        except ValueError as exc:
            raise ValueError(
                f"invalid retained cleanup journal evidence: {path.name}"
            ) from exc
        if journal.app_id != normalized_app_id:
            continue
        digest = journal.sha256()
        if digest in cleanup_by_journal or digest in reconciliation_by_journal:
            continue
        unresolved.append(
            UnresolvedLifecycleJournal(
                app_id=journal.app_id,
                journal_id=journal.journal_id,
                journal_sha256=digest,
                retained_cleanup_plan_sha256=journal.retained_cleanup_plan_sha256,
                retained_version=journal.retained_version,
                active_version=journal.active_version,
                scope=journal.scope,
                journal_path=str(path),
            )
        )

    return LifecycleGateObservation(
        app_id=normalized_app_id,
        receipt_root=str(root),
        unresolved=tuple(unresolved),
        cleanup_receipts_seen=cleanup_seen,
        reconciliation_receipts_seen=reconciliation_seen,
    )


def assert_lifecycle_clear(
    receipt_root: Path,
    *,
    app_id: str,
    operation: str,
) -> LifecycleGateObservation:
    observation = observe_lifecycle_gate(receipt_root, app_id=app_id)
    if observation.clear:
        return observation
    digests = ",".join(item.journal_sha256[:12] for item in observation.unresolved)
    raise ValueError(
        "unresolved lifecycle transition blocks "
        f"{operation} for {app_id}; reconcile prepared cleanup journal(s): {digests}"
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if metadata.st_size > MAX_LIFECYCLE_FILE_BYTES:
        raise ValueError(f"{label} exceeds configured size bound")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value
