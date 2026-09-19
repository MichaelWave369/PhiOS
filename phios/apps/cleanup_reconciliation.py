from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .desktop_update import _load_bundle, _root, _verify_current_bundle
from .package_install import snapshot_installed_tree
from .retained_cleanup import (
    RetainedCleanupJournal,
    RetainedCleanupPlan,
    RetainedCleanupReceipt,
    _read_json,
    _write_json_atomic,
)

CLEANUP_RECONCILIATION_OBSERVATION_SCHEMA_VERSION = (
    "phios.cleanup_reconciliation_observation.v0.1"
)
CLEANUP_RECONCILIATION_PLAN_SCHEMA_VERSION = "phios.cleanup_reconciliation_plan.v0.1"
CLEANUP_RECONCILIATION_REVIEW_SCHEMA_VERSION = (
    "phios.cleanup_reconciliation_review.v0.1"
)
CLEANUP_RECONCILIATION_RECEIPT_SCHEMA_VERSION = (
    "phios.cleanup_reconciliation_receipt.v0.1"
)

ReconciliationClassification = Literal[
    "untouched",
    "partial",
    "effectively_complete",
    "invalid",
]
ReconciliationAction = Literal["cancel", "complete", "finalize"]
ObservedTargetState = Literal["present_verified", "absent", "present_invalid"]
ObservedActiveState = Literal["verified", "invalid"]
ReconciliationStatus = Literal["cancelled", "completed", "finalized"]

_CANCEL_PERMISSION = ("cleanup.reconcile.cancel",)
_FINALIZE_PERMISSION = ("cleanup.reconcile.finalize",)
_MAX_RECEIPT_ENTRIES = 4096


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _string(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _contained_expected(root: Path, path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=False)
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"{label} escaped configured root")

    current = root
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escaped configured root") from exc
    for part in relative.parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"{label} traverses a symlinked parent")
    return resolved


def _complete_permissions(plan: RetainedCleanupPlan) -> tuple[str, ...]:
    return ("cleanup.reconcile.complete", *plan.requested_cleanup_permissions)


def _action_permissions(
    action: ReconciliationAction,
    cleanup_plan: RetainedCleanupPlan,
) -> tuple[str, ...]:
    if action == "cancel":
        return _CANCEL_PERMISSION
    if action == "finalize":
        return _FINALIZE_PERMISSION
    if action == "complete":
        return _complete_permissions(cleanup_plan)
    raise ValueError("unsupported cleanup reconciliation action")


def _allowed_actions(
    classification: ReconciliationClassification,
) -> tuple[ReconciliationAction, ...]:
    if classification == "untouched":
        return ("cancel", "complete")
    if classification == "partial":
        return ("complete",)
    if classification == "effectively_complete":
        return ("finalize",)
    return ()


def _load_inputs(
    journal_value: Any,
    cleanup_plan_value: Any,
) -> tuple[RetainedCleanupJournal, RetainedCleanupPlan]:
    journal = RetainedCleanupJournal.from_dict(journal_value)
    plan = RetainedCleanupPlan.from_dict(cleanup_plan_value)
    if journal.retained_cleanup_plan_sha256 != plan.sha256():
        raise ValueError("cleanup journal does not bind supplied cleanup plan")
    if journal.app_id != plan.app_id:
        raise ValueError("cleanup journal app_id does not match cleanup plan")
    if journal.retained_version != plan.retained_version:
        raise ValueError("cleanup journal retained version does not match cleanup plan")
    if journal.active_version != plan.active_version:
        raise ValueError("cleanup journal active version does not match cleanup plan")
    if journal.scope != plan.scope:
        raise ValueError("cleanup journal scope does not match cleanup plan")
    if journal.retained_bundle_path != plan.retained_bundle_path:
        raise ValueError("cleanup journal retained bundle path mismatch")
    if journal.retained_install_path != plan.retained_install_path:
        raise ValueError("cleanup journal retained install path mismatch")
    if journal.retention_marker_path != plan.retention_marker_path:
        raise ValueError("cleanup journal retention marker path mismatch")
    if journal.retained_grant_sha256 != plan.retained_grant_sha256:
        raise ValueError("cleanup journal retained grant mismatch")
    if journal.active_grant_sha256 != plan.active_grant_sha256:
        raise ValueError("cleanup journal active grant mismatch")
    if journal.retention_marker_sha256 != plan.retention_marker_sha256:
        raise ValueError("cleanup journal retention marker mismatch")
    if journal.approved_cleanup_permissions != plan.requested_cleanup_permissions:
        raise ValueError("cleanup journal permissions do not match cleanup plan")
    return journal, plan


def _bound_valid_receipt_count(
    receipt_root: Path,
    *,
    journal_sha256: str,
) -> int:
    if not receipt_root.exists():
        return 0
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ValueError("cleanup receipt root is unavailable or unsafe")
    count = 0
    entries = sorted(receipt_root.iterdir(), key=lambda path: path.name)
    if len(entries) > _MAX_RECEIPT_ENTRIES:
        raise ValueError("cleanup receipt root exceeds bounded entry count")
    for entry in entries:
        if (
            entry.is_symlink()
            or not entry.is_file()
            or not entry.name.startswith("retained-cleanup-")
            or entry.name.startswith("retained-cleanup-journal-")
            or entry.name.startswith("retained-cleanup-reconciliation-")
        ):
            continue
        try:
            receipt = RetainedCleanupReceipt.from_dict(
                _read_json(entry, "retained cleanup receipt")
            )
        except ValueError:
            continue
        if receipt.retained_cleanup_journal_sha256 == journal_sha256:
            count += 1
    return count


def _bound_reconciliation_receipt_count(
    receipt_root: Path,
    *,
    journal_sha256: str,
) -> int:
    if not receipt_root.exists():
        return 0
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ValueError("cleanup receipt root is unavailable or unsafe")
    count = 0
    entries = sorted(receipt_root.iterdir(), key=lambda path: path.name)
    if len(entries) > _MAX_RECEIPT_ENTRIES:
        raise ValueError("cleanup receipt root exceeds bounded entry count")
    for entry in entries:
        if (
            entry.is_symlink()
            or not entry.is_file()
            or not entry.name.startswith("retained-cleanup-reconciliation-")
        ):
            continue
        try:
            receipt = CleanupReconciliationReceipt.from_dict(
                _read_json(entry, "cleanup reconciliation receipt")
            )
        except ValueError:
            continue
        if receipt.retained_cleanup_journal_sha256 == journal_sha256:
            count += 1
    return count


def _observe_active(
    plan: RetainedCleanupPlan,
    *,
    desktop_root: Path,
    install_root: Path,
    applications_root: Path,
) -> tuple[ObservedActiveState, tuple[str, ...]]:
    issues: list[str] = []
    try:
        active = _load_bundle(Path(plan.active_bundle_path), desktop_root=desktop_root)
        _verify_current_bundle(
            active,
            install_root=install_root,
            applications_root=applications_root,
            require_active_entry=True,
        )
        if active.plan.sha256() != plan.active_desktop_plan_sha256:
            issues.append("active_plan_mismatch")
        if active.grant.sha256() != plan.active_grant_sha256:
            issues.append("active_grant_mismatch")
        entry_path = Path(plan.desktop_entry_path)
        if (
            entry_path.is_symlink()
            or not entry_path.is_file()
            or hashlib.sha256(entry_path.read_bytes()).hexdigest()
            != plan.active_entry_sha256
        ):
            issues.append("active_entry_mismatch")
    except (OSError, ValueError):
        issues.append("active_state_invalid")
    return ("verified", ()) if not issues else ("invalid", tuple(sorted(set(issues))))


def _observe_marker(
    plan: RetainedCleanupPlan,
    *,
    desktop_root: Path,
) -> tuple[ObservedTargetState, tuple[str, ...]]:
    marker_path = _contained_expected(
        desktop_root,
        Path(plan.retention_marker_path),
        "retention marker path",
    )
    if not marker_path.exists():
        return "absent", ()
    if marker_path.is_symlink() or not marker_path.is_file():
        return "present_invalid", ("retention_marker_unsafe",)
    try:
        from .desktop_update import DesktopRetentionMarker

        marker = DesktopRetentionMarker.from_dict(
            _read_json(marker_path, "desktop retention marker")
        )
    except (OSError, ValueError):
        return "present_invalid", ("retention_marker_invalid",)
    if marker.sha256() != plan.retention_marker_sha256:
        return "present_invalid", ("retention_marker_mismatch",)
    if (
        Path(marker.retained_bundle_path) != Path(plan.retained_bundle_path)
        or marker.retained_grant_sha256 != plan.retained_grant_sha256
        or Path(marker.active_bundle_path) != Path(plan.active_bundle_path)
        or marker.active_grant_sha256 != plan.active_grant_sha256
    ):
        return "present_invalid", ("retention_marker_binding_mismatch",)
    return "present_verified", ()


def _observe_retained_bundle(
    plan: RetainedCleanupPlan,
    *,
    desktop_root: Path,
    install_root: Path,
    applications_root: Path,
) -> tuple[ObservedTargetState, tuple[str, ...]]:
    path = _contained_expected(
        desktop_root,
        Path(plan.retained_bundle_path),
        "retained desktop bundle",
    )
    if not path.exists():
        return "absent", ()
    if path.is_symlink() or not path.is_dir():
        return "present_invalid", ("retained_bundle_unsafe",)
    try:
        retained = _load_bundle(path, desktop_root=desktop_root)
        _verify_current_bundle(
            retained,
            install_root=install_root,
            applications_root=applications_root,
            require_active_entry=False,
        )
    except (OSError, ValueError):
        return "present_invalid", ("retained_bundle_invalid",)
    issues: list[str] = []
    if retained.plan.sha256() != plan.retained_desktop_plan_sha256:
        issues.append("retained_plan_mismatch")
    if retained.grant.sha256() != plan.retained_grant_sha256:
        issues.append("retained_grant_mismatch")
    if retained.install_receipt.sha256() != plan.retained_install_receipt_sha256:
        issues.append("retained_install_receipt_mismatch")
    return (
        ("present_verified", ())
        if not issues
        else ("present_invalid", tuple(sorted(set(issues))))
    )


def _observe_retained_install(
    plan: RetainedCleanupPlan,
    *,
    install_root: Path,
) -> tuple[ObservedTargetState, tuple[str, ...]]:
    path = _contained_expected(
        install_root,
        Path(plan.retained_install_path),
        "retained install path",
    )
    if not path.exists():
        return "absent", ()
    if path.is_symlink() or not path.is_dir():
        return "present_invalid", ("retained_install_unsafe",)
    try:
        tree_sha, _, _ = snapshot_installed_tree(path)
    except (OSError, ValueError):
        return "present_invalid", ("retained_install_invalid",)
    if tree_sha != plan.retained_installed_tree_sha256:
        return "present_invalid", ("retained_install_tree_mismatch",)
    return "present_verified", ()


def _classify(
    *,
    scope: str,
    marker_state: ObservedTargetState,
    bundle_state: ObservedTargetState,
    install_state: ObservedTargetState,
    active_state: ObservedActiveState,
    bound_cleanup_receipt_count: int,
    bound_reconciliation_receipt_count: int,
) -> ReconciliationClassification:
    if active_state != "verified":
        return "invalid"
    if bound_cleanup_receipt_count != 0 or bound_reconciliation_receipt_count != 0:
        return "invalid"
    if "present_invalid" in {marker_state, bundle_state, install_state}:
        return "invalid"

    if scope == "desktop_bundle_only":
        if (
            marker_state == "present_verified"
            and bundle_state == "present_verified"
            and install_state == "present_verified"
        ):
            return "untouched"
        if (
            marker_state == "absent"
            and bundle_state == "absent"
            and install_state == "present_verified"
        ):
            return "effectively_complete"
        return "partial"

    if scope == "desktop_bundle_and_install":
        if (
            marker_state == "present_verified"
            and bundle_state == "present_verified"
            and install_state == "present_verified"
        ):
            return "untouched"
        if (
            marker_state == "absent"
            and bundle_state == "absent"
            and install_state == "absent"
        ):
            return "effectively_complete"
        return "partial"
    return "invalid"


@dataclass(frozen=True)
class CleanupReconciliationObservation:
    retained_cleanup_journal_sha256: str
    retained_cleanup_plan_sha256: str
    app_id: str
    retained_version: str
    active_version: str
    scope: str
    marker_state: ObservedTargetState
    retained_bundle_state: ObservedTargetState
    retained_install_state: ObservedTargetState
    active_state: ObservedActiveState
    bound_cleanup_receipt_count: int
    bound_reconciliation_receipt_count: int
    classification: ReconciliationClassification
    issues: tuple[str, ...]
    allowed_actions: tuple[ReconciliationAction, ...]
    reconciliation_authority: bool = False
    cleanup_authority: bool = False
    rollback_authority: bool = False
    schema_version: str = CLEANUP_RECONCILIATION_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CLEANUP_RECONCILIATION_OBSERVATION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported cleanup reconciliation observation schema: {self.schema_version}"
            )
        _sha256(
            self.retained_cleanup_journal_sha256,
            "retained_cleanup_journal_sha256",
        )
        _sha256(self.retained_cleanup_plan_sha256, "retained_cleanup_plan_sha256")
        if self.classification not in {
            "untouched",
            "partial",
            "effectively_complete",
            "invalid",
        }:
            raise ValueError("unsupported cleanup reconciliation classification")
        if tuple(sorted(set(self.issues))) != self.issues:
            raise ValueError("cleanup reconciliation issues must be sorted and unique")
        if self.allowed_actions != _allowed_actions(self.classification):
            raise ValueError("allowed reconciliation actions do not match classification")
        for value in (
            self.bound_cleanup_receipt_count,
            self.bound_reconciliation_receipt_count,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("cleanup reconciliation receipt counts are invalid")
        if any(
            not isinstance(value, bool)
            for value in (
                self.reconciliation_authority,
                self.cleanup_authority,
                self.rollback_authority,
            )
        ):
            raise ValueError("cleanup reconciliation authority fields must be boolean")
        if (
            self.reconciliation_authority
            or self.cleanup_authority
            or self.rollback_authority
        ):
            raise ValueError("cleanup reconciliation observation grants no authority")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["issues"] = list(self.issues)
        result["allowed_actions"] = list(self.allowed_actions)
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["cleanup_reconciliation_observation_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> CleanupReconciliationObservation:
        data = _mapping(value, "cleanup reconciliation observation")
        expected = {
            "schema_version",
            "retained_cleanup_journal_sha256",
            "retained_cleanup_plan_sha256",
            "app_id",
            "retained_version",
            "active_version",
            "scope",
            "marker_state",
            "retained_bundle_state",
            "retained_install_state",
            "active_state",
            "bound_cleanup_receipt_count",
            "bound_reconciliation_receipt_count",
            "classification",
            "issues",
            "allowed_actions",
            "reconciliation_authority",
            "cleanup_authority",
            "rollback_authority",
            "cleanup_reconciliation_observation_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "cleanup reconciliation observation contains missing or unknown fields"
            )
        issues = data["issues"]
        actions = data["allowed_actions"]
        if not isinstance(issues, list) or not isinstance(actions, list):
            raise ValueError("cleanup reconciliation arrays are invalid")
        observation = cls(
            schema_version=data["schema_version"],
            retained_cleanup_journal_sha256=_sha256(
                data["retained_cleanup_journal_sha256"],
                "retained_cleanup_journal_sha256",
            ),
            retained_cleanup_plan_sha256=_sha256(
                data["retained_cleanup_plan_sha256"],
                "retained_cleanup_plan_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            retained_version=_string(
                data["retained_version"],
                "retained_version",
                maximum=128,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            scope=_string(data["scope"], "scope", maximum=64),
            marker_state=data["marker_state"],
            retained_bundle_state=data["retained_bundle_state"],
            retained_install_state=data["retained_install_state"],
            active_state=data["active_state"],
            bound_cleanup_receipt_count=data["bound_cleanup_receipt_count"],
            bound_reconciliation_receipt_count=data[
                "bound_reconciliation_receipt_count"
            ],
            classification=data["classification"],
            issues=tuple(
                _string(item, "reconciliation issue", maximum=128) for item in issues
            ),
            allowed_actions=tuple(
                cast(
                    ReconciliationAction,
                    _string(item, "reconciliation action", maximum=32),
                )
                for item in actions
            ),
            reconciliation_authority=data["reconciliation_authority"],
            cleanup_authority=data["cleanup_authority"],
            rollback_authority=data["rollback_authority"],
        )
        if data["cleanup_reconciliation_observation_sha256"] != observation.sha256():
            raise ValueError(
                "cleanup reconciliation observation digest does not match canonical observation"
            )
        return observation


def observe_cleanup_reconciliation(
    journal_value: Any,
    cleanup_plan_value: Any,
    *,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
    receipt_root: Path,
) -> CleanupReconciliationObservation:
    journal, plan = _load_inputs(journal_value, cleanup_plan_value)
    desktop = _root(desktop_root, "desktop app bundle root")
    applications = _root(applications_root, "desktop applications root")
    installed = _root(install_root, "installed app root")
    receipts = _root(receipt_root, "cleanup receipt root", create=True)

    active_state, active_issues = _observe_active(
        plan,
        desktop_root=desktop,
        install_root=installed,
        applications_root=applications,
    )
    marker_state, marker_issues = _observe_marker(plan, desktop_root=desktop)
    bundle_state, bundle_issues = _observe_retained_bundle(
        plan,
        desktop_root=desktop,
        install_root=installed,
        applications_root=applications,
    )
    install_state, install_issues = _observe_retained_install(
        plan,
        install_root=installed,
    )
    cleanup_receipts = _bound_valid_receipt_count(
        receipts,
        journal_sha256=journal.sha256(),
    )
    reconciliation_receipts = _bound_reconciliation_receipt_count(
        receipts,
        journal_sha256=journal.sha256(),
    )

    issues = list(
        active_issues + marker_issues + bundle_issues + install_issues
    )
    if cleanup_receipts:
        issues.append("bound_cleanup_receipt_exists")
    if reconciliation_receipts:
        issues.append("bound_reconciliation_receipt_exists")
    classification = _classify(
        scope=plan.scope,
        marker_state=marker_state,
        bundle_state=bundle_state,
        install_state=install_state,
        active_state=active_state,
        bound_cleanup_receipt_count=cleanup_receipts,
        bound_reconciliation_receipt_count=reconciliation_receipts,
    )
    return CleanupReconciliationObservation(
        retained_cleanup_journal_sha256=journal.sha256(),
        retained_cleanup_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        retained_version=plan.retained_version,
        active_version=plan.active_version,
        scope=plan.scope,
        marker_state=marker_state,
        retained_bundle_state=bundle_state,
        retained_install_state=install_state,
        active_state=active_state,
        bound_cleanup_receipt_count=cleanup_receipts,
        bound_reconciliation_receipt_count=reconciliation_receipts,
        classification=classification,
        issues=tuple(sorted(set(issues))),
        allowed_actions=_allowed_actions(classification),
        reconciliation_authority=False,
        cleanup_authority=False,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class CleanupReconciliationPlan:
    action: ReconciliationAction
    classification: ReconciliationClassification
    cleanup_reconciliation_observation_sha256: str
    retained_cleanup_journal_sha256: str
    retained_cleanup_plan_sha256: str
    app_id: str
    retained_version: str
    active_version: str
    scope: str
    retained_bundle_path: str
    retained_install_path: str
    retention_marker_path: str
    active_bundle_path: str
    active_grant_sha256: str
    requested_reconciliation_permissions: tuple[str, ...]
    reconciliation_authority: bool = False
    cleanup_authority: bool = False
    rollback_authority: bool = False
    schema_version: str = CLEANUP_RECONCILIATION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CLEANUP_RECONCILIATION_PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported cleanup reconciliation plan schema: {self.schema_version}"
            )
        if self.action not in {"cancel", "complete", "finalize"}:
            raise ValueError("unsupported cleanup reconciliation action")
        if self.action not in _allowed_actions(self.classification):
            raise ValueError("reconciliation action is not allowed for classification")
        for value, label in (
            (
                self.cleanup_reconciliation_observation_sha256,
                "cleanup_reconciliation_observation_sha256",
            ),
            (self.retained_cleanup_journal_sha256, "retained_cleanup_journal_sha256"),
            (self.retained_cleanup_plan_sha256, "retained_cleanup_plan_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
        ):
            _sha256(value, label)
        for value, label in (
            (self.retained_bundle_path, "retained_bundle_path"),
            (self.retained_install_path, "retained_install_path"),
            (self.retention_marker_path, "retention_marker_path"),
            (self.active_bundle_path, "active_bundle_path"),
        ):
            if not Path(value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        if any(
            not isinstance(value, bool)
            for value in (
                self.reconciliation_authority,
                self.cleanup_authority,
                self.rollback_authority,
            )
        ):
            raise ValueError("cleanup reconciliation plan authority fields must be boolean")
        if (
            self.reconciliation_authority
            or self.cleanup_authority
            or self.rollback_authority
        ):
            raise ValueError("cleanup reconciliation plan grants no authority")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_reconciliation_permissions"] = list(
            self.requested_reconciliation_permissions
        )
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["cleanup_reconciliation_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> CleanupReconciliationPlan:
        data = _mapping(value, "cleanup reconciliation plan")
        expected = {
            "schema_version",
            "action",
            "classification",
            "cleanup_reconciliation_observation_sha256",
            "retained_cleanup_journal_sha256",
            "retained_cleanup_plan_sha256",
            "app_id",
            "retained_version",
            "active_version",
            "scope",
            "retained_bundle_path",
            "retained_install_path",
            "retention_marker_path",
            "active_bundle_path",
            "active_grant_sha256",
            "requested_reconciliation_permissions",
            "reconciliation_authority",
            "cleanup_authority",
            "rollback_authority",
            "cleanup_reconciliation_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("cleanup reconciliation plan contains missing or unknown fields")
        permissions = data["requested_reconciliation_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("requested_reconciliation_permissions must be an array")
        action = _string(data["action"], "reconciliation action", maximum=32)
        classification = _string(
            data["classification"],
            "reconciliation classification",
            maximum=64,
        )
        plan = cls(
            schema_version=data["schema_version"],
            action=cast(ReconciliationAction, action),
            classification=cast(ReconciliationClassification, classification),
            cleanup_reconciliation_observation_sha256=_sha256(
                data["cleanup_reconciliation_observation_sha256"],
                "cleanup_reconciliation_observation_sha256",
            ),
            retained_cleanup_journal_sha256=_sha256(
                data["retained_cleanup_journal_sha256"],
                "retained_cleanup_journal_sha256",
            ),
            retained_cleanup_plan_sha256=_sha256(
                data["retained_cleanup_plan_sha256"],
                "retained_cleanup_plan_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            retained_version=_string(
                data["retained_version"],
                "retained_version",
                maximum=128,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            scope=_string(data["scope"], "scope", maximum=64),
            retained_bundle_path=_string(
                data["retained_bundle_path"],
                "retained_bundle_path",
                maximum=4096,
            ),
            retained_install_path=_string(
                data["retained_install_path"],
                "retained_install_path",
                maximum=4096,
            ),
            retention_marker_path=_string(
                data["retention_marker_path"],
                "retention_marker_path",
                maximum=4096,
            ),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            requested_reconciliation_permissions=tuple(
                _string(item, "reconciliation permission", maximum=128)
                for item in permissions
            ),
            reconciliation_authority=data["reconciliation_authority"],
            cleanup_authority=data["cleanup_authority"],
            rollback_authority=data["rollback_authority"],
        )
        if data["cleanup_reconciliation_plan_sha256"] != plan.sha256():
            raise ValueError(
                "cleanup reconciliation plan digest does not match canonical plan"
            )
        return plan


def plan_cleanup_reconciliation(
    journal_value: Any,
    cleanup_plan_value: Any,
    *,
    action: ReconciliationAction,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
    receipt_root: Path,
) -> CleanupReconciliationPlan:
    journal, cleanup_plan = _load_inputs(journal_value, cleanup_plan_value)
    observation = observe_cleanup_reconciliation(
        journal.to_dict(),
        cleanup_plan.to_dict(),
        install_root=install_root,
        desktop_root=desktop_root,
        applications_root=applications_root,
        receipt_root=receipt_root,
    )
    if action not in observation.allowed_actions:
        raise ValueError(
            f"reconciliation action {action!r} is not allowed for "
            f"classification {observation.classification!r}"
        )
    return CleanupReconciliationPlan(
        action=action,
        classification=observation.classification,
        cleanup_reconciliation_observation_sha256=observation.sha256(),
        retained_cleanup_journal_sha256=journal.sha256(),
        retained_cleanup_plan_sha256=cleanup_plan.sha256(),
        app_id=cleanup_plan.app_id,
        retained_version=cleanup_plan.retained_version,
        active_version=cleanup_plan.active_version,
        scope=cleanup_plan.scope,
        retained_bundle_path=cleanup_plan.retained_bundle_path,
        retained_install_path=cleanup_plan.retained_install_path,
        retention_marker_path=cleanup_plan.retention_marker_path,
        active_bundle_path=cleanup_plan.active_bundle_path,
        active_grant_sha256=cleanup_plan.active_grant_sha256,
        requested_reconciliation_permissions=_action_permissions(
            action,
            cleanup_plan,
        ),
        reconciliation_authority=False,
        cleanup_authority=False,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class CleanupReconciliationReview:
    cleanup_reconciliation_plan_sha256: str
    action: ReconciliationAction
    classification: ReconciliationClassification
    cleanup_reconciliation_observation_sha256: str
    retained_cleanup_journal_sha256: str
    retained_cleanup_plan_sha256: str
    app_id: str
    retained_version: str
    active_version: str
    scope: str
    requested_reconciliation_permissions: tuple[str, ...]
    reconciliation_authority: bool
    cleanup_authority: bool
    rollback_authority: bool
    schema_version: str = CLEANUP_RECONCILIATION_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_reconciliation_permissions"] = list(
            self.requested_reconciliation_permissions
        )
        return result


def review_cleanup_reconciliation(value: Any) -> CleanupReconciliationReview:
    plan = CleanupReconciliationPlan.from_dict(value)
    return CleanupReconciliationReview(
        cleanup_reconciliation_plan_sha256=plan.sha256(),
        action=plan.action,
        classification=plan.classification,
        cleanup_reconciliation_observation_sha256=(
            plan.cleanup_reconciliation_observation_sha256
        ),
        retained_cleanup_journal_sha256=plan.retained_cleanup_journal_sha256,
        retained_cleanup_plan_sha256=plan.retained_cleanup_plan_sha256,
        app_id=plan.app_id,
        retained_version=plan.retained_version,
        active_version=plan.active_version,
        scope=plan.scope,
        requested_reconciliation_permissions=plan.requested_reconciliation_permissions,
        reconciliation_authority=False,
        cleanup_authority=False,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class CleanupReconciliationRequest:
    plan: CleanupReconciliationPlan
    journal: RetainedCleanupJournal
    cleanup_plan: RetainedCleanupPlan
    approved_reconciliation_plan_sha256: str
    approved_observation_sha256: str
    approved_journal_sha256: str
    approved_cleanup_plan_sha256: str
    approved_reconciliation_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_reconciliation_plan_sha256 != self.plan.sha256():
            raise ValueError(
                "Approved reconciliation plan SHA-256 does not match canonical plan"
            )
        if (
            self.approved_observation_sha256
            != self.plan.cleanup_reconciliation_observation_sha256
        ):
            raise ValueError("Approved observation SHA-256 does not match plan")
        if self.approved_journal_sha256 != self.journal.sha256():
            raise ValueError("Approved cleanup journal SHA-256 does not match journal")
        if self.approved_cleanup_plan_sha256 != self.cleanup_plan.sha256():
            raise ValueError("Approved cleanup plan SHA-256 does not match cleanup plan")
        if self.plan.retained_cleanup_journal_sha256 != self.journal.sha256():
            raise ValueError("reconciliation plan does not bind cleanup journal")
        if self.plan.retained_cleanup_plan_sha256 != self.cleanup_plan.sha256():
            raise ValueError("reconciliation plan does not bind cleanup plan")
        expected = _action_permissions(self.plan.action, self.cleanup_plan)
        if self.plan.requested_reconciliation_permissions != expected:
            raise ValueError("reconciliation plan permission set is invalid")
        if self.approved_reconciliation_permissions != expected:
            raise ValueError(
                "Approved reconciliation permissions must exactly match reviewed plan"
            )

    @classmethod
    def from_payloads(
        cls,
        reconciliation_plan_value: Any,
        journal_value: Any,
        cleanup_plan_value: Any,
        *,
        approved_reconciliation_plan_sha256: str,
        approved_observation_sha256: str,
        approved_journal_sha256: str,
        approved_cleanup_plan_sha256: str,
        approved_reconciliation_permissions: tuple[str, ...],
    ) -> CleanupReconciliationRequest:
        return cls(
            plan=CleanupReconciliationPlan.from_dict(reconciliation_plan_value),
            journal=RetainedCleanupJournal.from_dict(journal_value),
            cleanup_plan=RetainedCleanupPlan.from_dict(cleanup_plan_value),
            approved_reconciliation_plan_sha256=_sha256(
                approved_reconciliation_plan_sha256,
                "approved_reconciliation_plan_sha256",
            ),
            approved_observation_sha256=_sha256(
                approved_observation_sha256,
                "approved_observation_sha256",
            ),
            approved_journal_sha256=_sha256(
                approved_journal_sha256,
                "approved_journal_sha256",
            ),
            approved_cleanup_plan_sha256=_sha256(
                approved_cleanup_plan_sha256,
                "approved_cleanup_plan_sha256",
            ),
            approved_reconciliation_permissions=tuple(
                sorted(approved_reconciliation_permissions)
            ),
        )


def _build_cleanup_receipt(
    cleanup_plan: RetainedCleanupPlan,
    journal: RetainedCleanupJournal,
) -> RetainedCleanupReceipt:
    include_install = cleanup_plan.scope == "desktop_bundle_and_install"
    return RetainedCleanupReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(UTC).isoformat(),
        retained_cleanup_plan_sha256=cleanup_plan.sha256(),
        retained_cleanup_journal_sha256=journal.sha256(),
        app_id=cleanup_plan.app_id,
        retained_version=cleanup_plan.retained_version,
        active_version=cleanup_plan.active_version,
        scope=cleanup_plan.scope,
        removed_bundle_path=cleanup_plan.retained_bundle_path,
        removed_install_path=(
            cleanup_plan.retained_install_path if include_install else None
        ),
        removed_install_receipt_sha256=(
            cleanup_plan.retained_install_receipt_sha256 if include_install else None
        ),
        removed_installed_tree_sha256=(
            cleanup_plan.retained_installed_tree_sha256 if include_install else None
        ),
        retired_marker_path=cleanup_plan.retention_marker_path,
        retired_marker_sha256=cleanup_plan.retention_marker_sha256,
        active_bundle_path=cleanup_plan.active_bundle_path,
        active_grant_sha256=cleanup_plan.active_grant_sha256,
        cleanup_authority=True,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class CleanupReconciliationReceipt:
    receipt_id: str
    timestamp_utc: str
    cleanup_reconciliation_plan_sha256: str
    cleanup_reconciliation_observation_sha256: str
    retained_cleanup_journal_sha256: str
    retained_cleanup_plan_sha256: str
    app_id: str
    action: ReconciliationAction
    classification_before: ReconciliationClassification
    classification_after: ReconciliationClassification
    cleanup_receipt_sha256: str | None
    requested_reconciliation_permissions: tuple[str, ...]
    reconciliation_authority: bool
    cleanup_authority: bool
    rollback_authority: bool
    status: ReconciliationStatus
    schema_version: str = CLEANUP_RECONCILIATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CLEANUP_RECONCILIATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported cleanup reconciliation receipt schema: {self.schema_version}"
            )
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("reconciliation receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("reconciliation receipt timestamp must include timezone")
        for value, label in (
            (
                self.cleanup_reconciliation_plan_sha256,
                "cleanup_reconciliation_plan_sha256",
            ),
            (
                self.cleanup_reconciliation_observation_sha256,
                "cleanup_reconciliation_observation_sha256",
            ),
            (self.retained_cleanup_journal_sha256, "retained_cleanup_journal_sha256"),
            (self.retained_cleanup_plan_sha256, "retained_cleanup_plan_sha256"),
        ):
            _sha256(value, label)
        if self.cleanup_receipt_sha256 is not None:
            _sha256(self.cleanup_receipt_sha256, "cleanup_receipt_sha256")
        if self.status == "cancelled":
            if self.action != "cancel" or self.cleanup_receipt_sha256 is not None:
                raise ValueError("cancelled reconciliation receipt is inconsistent")
            if self.classification_after != "untouched":
                raise ValueError("cancel leaves cleanup classification untouched")
        elif self.status in {"completed", "finalized"}:
            if self.cleanup_receipt_sha256 is None:
                raise ValueError("completed reconciliation must bind cleanup receipt")
            if self.classification_after != "effectively_complete":
                raise ValueError(
                    "completed reconciliation must end effectively_complete"
                )
        else:
            raise ValueError("unsupported cleanup reconciliation status")
        if not isinstance(self.reconciliation_authority, bool) or not isinstance(
            self.cleanup_authority, bool
        ) or not isinstance(self.rollback_authority, bool):
            raise ValueError("reconciliation receipt authority fields must be boolean")
        if not self.reconciliation_authority or self.rollback_authority:
            raise ValueError("reconciliation receipt authority state is invalid")
        if self.cleanup_authority != (self.action in {"complete", "finalize"}):
            raise ValueError("reconciliation cleanup authority does not match action")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_reconciliation_permissions"] = list(
            self.requested_reconciliation_permissions
        )
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["cleanup_reconciliation_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> CleanupReconciliationReceipt:
        data = _mapping(value, "cleanup reconciliation receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "cleanup_reconciliation_plan_sha256",
            "cleanup_reconciliation_observation_sha256",
            "retained_cleanup_journal_sha256",
            "retained_cleanup_plan_sha256",
            "app_id",
            "action",
            "classification_before",
            "classification_after",
            "cleanup_receipt_sha256",
            "requested_reconciliation_permissions",
            "reconciliation_authority",
            "cleanup_authority",
            "rollback_authority",
            "status",
            "cleanup_reconciliation_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "cleanup reconciliation receipt contains missing or unknown fields"
            )
        permissions = data["requested_reconciliation_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("reconciliation receipt permissions must be an array")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            cleanup_reconciliation_plan_sha256=_sha256(
                data["cleanup_reconciliation_plan_sha256"],
                "cleanup_reconciliation_plan_sha256",
            ),
            cleanup_reconciliation_observation_sha256=_sha256(
                data["cleanup_reconciliation_observation_sha256"],
                "cleanup_reconciliation_observation_sha256",
            ),
            retained_cleanup_journal_sha256=_sha256(
                data["retained_cleanup_journal_sha256"],
                "retained_cleanup_journal_sha256",
            ),
            retained_cleanup_plan_sha256=_sha256(
                data["retained_cleanup_plan_sha256"],
                "retained_cleanup_plan_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            action=cast(
                ReconciliationAction,
                _string(data["action"], "reconciliation action", maximum=32),
            ),
            classification_before=cast(
                ReconciliationClassification,
                _string(
                    data["classification_before"],
                    "classification_before",
                    maximum=64,
                ),
            ),
            classification_after=cast(
                ReconciliationClassification,
                _string(
                    data["classification_after"],
                    "classification_after",
                    maximum=64,
                ),
            ),
            cleanup_receipt_sha256=(
                None
                if data["cleanup_receipt_sha256"] is None
                else _sha256(
                    data["cleanup_receipt_sha256"],
                    "cleanup_receipt_sha256",
                )
            ),
            requested_reconciliation_permissions=tuple(
                _string(item, "reconciliation permission", maximum=128)
                for item in permissions
            ),
            reconciliation_authority=data["reconciliation_authority"],
            cleanup_authority=data["cleanup_authority"],
            rollback_authority=data["rollback_authority"],
            status=data["status"],
        )
        if data["cleanup_reconciliation_receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "cleanup reconciliation receipt digest does not match canonical receipt"
            )
        return receipt


@dataclass(frozen=True)
class CleanupReconciliationResult:
    receipt: CleanupReconciliationReceipt
    receipt_path: str
    cleanup_receipt: RetainedCleanupReceipt | None
    cleanup_receipt_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
            "cleanup_receipt": (
                None if self.cleanup_receipt is None else self.cleanup_receipt.to_dict()
            ),
            "cleanup_receipt_path": self.cleanup_receipt_path,
        }


class CleanupReconciliationService:
    def execute(
        self,
        request: CleanupReconciliationRequest,
        *,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
        receipt_root: Path,
    ) -> CleanupReconciliationResult:
        desktop = _root(desktop_root, "desktop app bundle root")
        installed = _root(install_root, "installed app root")
        receipts = _root(receipt_root, "cleanup receipt root", create=True)

        current_observation = observe_cleanup_reconciliation(
            request.journal.to_dict(),
            request.cleanup_plan.to_dict(),
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
            receipt_root=receipts,
        )
        if (
            current_observation.sha256()
            != request.plan.cleanup_reconciliation_observation_sha256
        ):
            raise ValueError("cleanup reconciliation state changed after review")
        if request.plan.action not in current_observation.allowed_actions:
            raise ValueError("cleanup reconciliation action is no longer allowed")

        cleanup_receipt: RetainedCleanupReceipt | None = None
        cleanup_receipt_path: Path | None = None

        if request.plan.action == "cancel":
            classification_after: ReconciliationClassification = "untouched"
            status: ReconciliationStatus = "cancelled"
        else:
            marker_path = _contained_expected(
                desktop,
                Path(request.cleanup_plan.retention_marker_path),
                "retention marker path",
            )
            retained_bundle = _contained_expected(
                desktop,
                Path(request.cleanup_plan.retained_bundle_path),
                "retained desktop bundle",
            )
            retained_install = _contained_expected(
                installed,
                Path(request.cleanup_plan.retained_install_path),
                "retained install path",
            )

            if request.plan.action == "complete":
                if marker_path.exists():
                    marker_path.unlink()
                if retained_bundle.exists():
                    shutil.rmtree(retained_bundle)
                if (
                    request.cleanup_plan.scope == "desktop_bundle_and_install"
                    and retained_install.exists()
                ):
                    shutil.rmtree(retained_install)

            post_observation = observe_cleanup_reconciliation(
                request.journal.to_dict(),
                request.cleanup_plan.to_dict(),
                install_root=install_root,
                desktop_root=desktop_root,
                applications_root=applications_root,
                receipt_root=receipts,
            )
            if post_observation.classification != "effectively_complete":
                raise ValueError(
                    "cleanup reconciliation did not reach effectively_complete state"
                )
            cleanup_receipt = _build_cleanup_receipt(
                request.cleanup_plan,
                request.journal,
            )
            cleanup_receipt_path = (
                receipts / f"retained-cleanup-{cleanup_receipt.receipt_id}.json"
            )
            _write_json_atomic(cleanup_receipt_path, cleanup_receipt.to_dict())
            classification_after = "effectively_complete"
            status = (
                "completed" if request.plan.action == "complete" else "finalized"
            )

        receipt = CleanupReconciliationReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            cleanup_reconciliation_plan_sha256=request.plan.sha256(),
            cleanup_reconciliation_observation_sha256=(
                request.plan.cleanup_reconciliation_observation_sha256
            ),
            retained_cleanup_journal_sha256=request.journal.sha256(),
            retained_cleanup_plan_sha256=request.cleanup_plan.sha256(),
            app_id=request.cleanup_plan.app_id,
            action=request.plan.action,
            classification_before=request.plan.classification,
            classification_after=classification_after,
            cleanup_receipt_sha256=(
                None if cleanup_receipt is None else cleanup_receipt.sha256()
            ),
            requested_reconciliation_permissions=(
                request.approved_reconciliation_permissions
            ),
            reconciliation_authority=True,
            cleanup_authority=request.plan.action in {"complete", "finalize"},
            rollback_authority=False,
            status=status,
        )
        receipt_path = (
            receipts / f"retained-cleanup-reconciliation-{receipt.receipt_id}.json"
        )
        _write_json_atomic(receipt_path, receipt.to_dict())
        return CleanupReconciliationResult(
            receipt=receipt,
            receipt_path=str(receipt_path),
            cleanup_receipt=cleanup_receipt,
            cleanup_receipt_path=(
                None if cleanup_receipt_path is None else str(cleanup_receipt_path)
            ),
        )
