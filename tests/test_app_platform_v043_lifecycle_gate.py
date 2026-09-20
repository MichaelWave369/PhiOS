from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import phios.apps.desktop_update as update_module
import phios.apps.retained_cleanup as cleanup_module
from phios.apps.cleanup_reconciliation import CleanupReconciliationReceipt
from phios.apps.lifecycle_gate import (
    assert_lifecycle_clear,
    observe_lifecycle_gate,
)
from phios.apps.retained_cleanup import (
    RetainedCleanupJournal,
    RetainedCleanupReceipt,
)


def _journal(tmp_path: Path, *, app_id: str = "phi.lifecycle-example") -> RetainedCleanupJournal:
    return RetainedCleanupJournal(
        journal_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-20T23:40:00+00:00",
        retained_cleanup_plan_sha256="a" * 64,
        app_id=app_id,
        retained_version="1.0.0",
        active_version="2.0.0",
        scope="desktop_bundle_only",
        retained_bundle_path=str((tmp_path / app_id / "bundle-v1").resolve()),
        retained_install_path=str((tmp_path / app_id / "install-v1").resolve()),
        retention_marker_path=str((tmp_path / app_id / "retained.json").resolve()),
        retained_grant_sha256="b" * 64,
        active_grant_sha256="c" * 64,
        retention_marker_sha256="d" * 64,
        approved_cleanup_permissions=("desktop.cleanup.retained",),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_journal(root: Path, journal: RetainedCleanupJournal) -> Path:
    path = root / f"retained-cleanup-journal-{journal.journal_id}.json"
    _write_json(path, journal.to_dict())
    return path


def _cleanup_receipt(tmp_path: Path, journal: RetainedCleanupJournal) -> RetainedCleanupReceipt:
    return RetainedCleanupReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-20T23:41:00+00:00",
        retained_cleanup_plan_sha256=journal.retained_cleanup_plan_sha256,
        retained_cleanup_journal_sha256=journal.sha256(),
        app_id=journal.app_id,
        retained_version=journal.retained_version,
        active_version=journal.active_version,
        scope=journal.scope,
        removed_bundle_path=journal.retained_bundle_path,
        removed_install_path=None,
        removed_install_receipt_sha256=None,
        removed_installed_tree_sha256=None,
        retired_marker_path=journal.retention_marker_path,
        retired_marker_sha256=journal.retention_marker_sha256,
        active_bundle_path=str((tmp_path / journal.app_id / "bundle-v2").resolve()),
        active_grant_sha256=journal.active_grant_sha256,
        cleanup_authority=True,
        rollback_authority=False,
    )


def _cancel_receipt(journal: RetainedCleanupJournal) -> CleanupReconciliationReceipt:
    return CleanupReconciliationReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-20T23:42:00+00:00",
        cleanup_reconciliation_plan_sha256="e" * 64,
        cleanup_reconciliation_observation_sha256="f" * 64,
        retained_cleanup_journal_sha256=journal.sha256(),
        retained_cleanup_plan_sha256=journal.retained_cleanup_plan_sha256,
        app_id=journal.app_id,
        action="cancel",
        classification_before="untouched",
        classification_after="untouched",
        cleanup_receipt_sha256=None,
        requested_reconciliation_permissions=("cleanup.reconcile.cancel",),
        reconciliation_authority=True,
        cleanup_authority=False,
        rollback_authority=False,
        status="cancelled",
    )


def test_absent_receipt_root_is_clear_and_observation_is_read_only(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    observation = observe_lifecycle_gate(root, app_id="phi.lifecycle-example")
    assert observation.clear is True
    assert observation.unresolved == ()
    assert observation.mutation_authority is False
    assert observation.reconciliation_authority is False
    assert not root.exists()


def test_prepared_journal_blocks_same_app_mutation(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    journal = _journal(tmp_path)
    _write_journal(root, journal)

    observation = observe_lifecycle_gate(root, app_id=journal.app_id)
    assert observation.clear is False
    assert [item.journal_sha256 for item in observation.unresolved] == [journal.sha256()]

    with pytest.raises(ValueError, match="unresolved lifecycle transition blocks desktop update"):
        assert_lifecycle_clear(
            root,
            app_id=journal.app_id,
            operation="desktop update",
        )


def test_cleanup_receipt_resolves_prepared_journal(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    journal = _journal(tmp_path)
    _write_journal(root, journal)
    receipt = _cleanup_receipt(tmp_path, journal)
    _write_json(root / f"retained-cleanup-{receipt.receipt_id}.json", receipt.to_dict())

    observation = observe_lifecycle_gate(root, app_id=journal.app_id)
    assert observation.clear is True
    assert observation.cleanup_receipts_seen == 1


def test_cancel_reconciliation_receipt_resolves_prepared_journal(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    journal = _journal(tmp_path)
    _write_journal(root, journal)
    receipt = _cancel_receipt(journal)
    _write_json(
        root / f"retained-cleanup-reconciliation-{receipt.receipt_id}.json",
        receipt.to_dict(),
    )

    observation = observe_lifecycle_gate(root, app_id=journal.app_id)
    assert observation.clear is True
    assert observation.reconciliation_receipts_seen == 1



def test_completed_reconciliation_without_cleanup_receipt_does_not_resolve(
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"
    journal = _journal(tmp_path)
    _write_journal(root, journal)
    receipt = CleanupReconciliationReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-20T23:43:00+00:00",
        cleanup_reconciliation_plan_sha256="4" * 64,
        cleanup_reconciliation_observation_sha256="5" * 64,
        retained_cleanup_journal_sha256=journal.sha256(),
        retained_cleanup_plan_sha256=journal.retained_cleanup_plan_sha256,
        app_id=journal.app_id,
        action="complete",
        classification_before="untouched",
        classification_after="effectively_complete",
        cleanup_receipt_sha256="6" * 64,
        requested_reconciliation_permissions=(
            "cleanup.reconcile.complete",
            "desktop.cleanup.retained",
        ),
        reconciliation_authority=True,
        cleanup_authority=True,
        rollback_authority=False,
        status="completed",
    )
    _write_json(
        root / f"retained-cleanup-reconciliation-{receipt.receipt_id}.json",
        receipt.to_dict(),
    )

    observation = observe_lifecycle_gate(root, app_id=journal.app_id)
    assert observation.clear is False
    assert len(observation.unresolved) == 1


def test_unresolved_journal_for_another_app_does_not_block_target(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    other = _journal(tmp_path, app_id="phi.other-app")
    _write_journal(root, other)

    observation = observe_lifecycle_gate(root, app_id="phi.lifecycle-example")
    assert observation.clear is True
    assert observation.unresolved == ()


def test_invalid_journal_evidence_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    root.mkdir()
    _write_json(
        root / "retained-cleanup-journal-broken.json",
        {"schema_version": "phios.retained_cleanup_journal.v0.1"},
    )
    with pytest.raises(ValueError, match="invalid retained cleanup journal evidence"):
        observe_lifecycle_gate(root, app_id="phi.lifecycle-example")


@pytest.mark.parametrize(
    ("module", "service_name", "operation"),
    [
        (update_module, "DesktopUpdateService", "desktop update"),
        (update_module, "DesktopRollbackService", "desktop rollback"),
        (cleanup_module, "RetainedCleanupService", "retained cleanup"),
    ],
)
def test_destructive_services_check_gate_before_other_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    service_name: str,
    operation: str,
) -> None:
    calls: list[tuple[str, str]] = []

    def blocked(
        receipt_root: Path,
        *,
        app_id: str,
        operation: str,
    ) -> None:
        del receipt_root
        calls.append((app_id, operation))
        raise ValueError("blocked by lifecycle gate")

    monkeypatch.setattr(module, "assert_lifecycle_clear", blocked)
    service = getattr(module, service_name)()
    request = SimpleNamespace(plan=SimpleNamespace(app_id="phi.lifecycle-example"))

    with pytest.raises(ValueError, match="blocked by lifecycle gate"):
        service.execute(
            request,
            install_root=tmp_path / "installed",
            desktop_root=tmp_path / "desktop",
            applications_root=tmp_path / "applications",
            receipt_root=tmp_path / "receipts",
        )
    assert calls == [("phi.lifecycle-example", operation)]
