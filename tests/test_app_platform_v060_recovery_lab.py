"""R5C: real filesystem transitions in a disposable Ubuntu runner.

The install/upgrade/rollback calls below are the existing governed PhiOS
DesktopAppInstaller, DesktopUpdateService and DesktopRollbackService. The
simulated "app broke" input is a synthetic health-probe failure; no real
application process, Linux ISO, production device, or user data is exercised.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import phios.apps.desktop_update as update_module
from phios.apps.desktop_catalog import snapshot_desktop_catalog
from phios.apps.desktop_update import (
    DesktopRollbackReceipt,
    DesktopRollbackService,
    DesktopUpdateReceipt,
    DesktopUpdateService,
    plan_desktop_rollback,
)
from phios.apps.recovery_lab import audit_disposable_recovery
from test_app_platform_v040_update_rollback import (
    _execute_update,
    _rollback_request,
    _setup,
    _update_plan,
    _update_request,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe_expected_health(index_html: Path, expected: str) -> bool:
    """Deliberately simple *file content* health probe, not an app runtime."""
    return expected.encode("utf-8") in index_html.read_bytes()


def test_actual_update_fault_detection_and_explicit_rollback(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    entry = Path(plan.desktop_entry_path)
    original_entry = entry.read_bytes()
    original_digest = digest(original_entry)
    assert original_digest == plan.active_entry_sha256

    _, updated = _execute_update(state)
    assert updated.receipt.status == "updated"
    assert entry.read_bytes() != original_entry
    assert digest(entry.read_bytes()) == plan.candidate_entry_sha256
    assert Path(updated.receipt.retention_marker_path).is_file()
    assert Path(updated.receipt_path).is_file()

    after_update_catalog = snapshot_desktop_catalog(
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        install_root=state["v1"]["install_root"],
    )
    after_status = {item.app_version:item.status for item in after_update_catalog.items}
    assert after_status == {"1.0.0":"blocked", "2.0.0":"ready"}

    # Synthetic failure: an external content policy expects version-one.
    # The v2 payload is unchanged, so actual trusted rollback can inspect it.
    candidate_html = state["v2"]["install_path"] / "payload" / "dist" / "index.html"
    assert probe_expected_health(candidate_html, "version-two")
    assert not probe_expected_health(candidate_html, "version-one")

    # The operator still must explicitly approve the exact rollback plan,
    # target grant, active grant, and minimal rollback permission set.
    rollback = plan_desktop_rollback(
        updated.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    assert rollback.rollback_authority is False
    restored = DesktopRollbackService().execute(
        _rollback_request(rollback, updated.receipt),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    assert entry.read_bytes() == original_entry
    assert Path(restored.receipt_path).is_file()
    assert DesktopUpdateReceipt.from_dict(updated.receipt.to_dict()) == updated.receipt
    assert DesktopRollbackReceipt.from_dict(restored.receipt.to_dict()) == restored.receipt

    report = audit_disposable_recovery(
        update_receipt_value=updated.receipt.to_dict(),
        rollback_receipt_value=restored.receipt.to_dict(),
        update_receipt_path=Path(updated.receipt_path),
        rollback_receipt_path=Path(restored.receipt_path),
        desktop_entry_path=entry,
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        install_root=state["v1"]["install_root"],
        receipt_root=state["receipt_root"],
        observed_failure_mode="simulated_post_update_health_probe_failure",
    )
    assert report["status"] == "DISPOSABLE_FILESYSTEM_RECOVERY_OBSERVED"
    assert report["observed_restored_entry_sha256"] == original_digest
    assert report["restored_version_is_ready_in_catalog"] is True
    assert report["candidate_is_blocked_in_catalog"] is True
    assert report["real_process_health_probed"] is False
    assert report["user_data_rollback_verified"] is False
    assert report["publisher_identity_verified"] is False
    assert report["signed_artifact_bound_to_this_rehearsal"] is False
    assert report["operations_performed_by_auditor"] == []

    # CI can publish *bounded structured observations*, not a forged
    # "production recovery verified" or publisher trust certificate.
    output_dir = os.environ.get("PHIOS_R5C_EVIDENCE_DIR")
    if output_dir:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination/"disposable-recovery-observation.json").write_text(
            json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8"
        )


def test_update_receipt_write_failure_aborts_without_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state=_setup(tmp_path)
    plan=_update_plan(state)
    request=_update_request(state,plan)
    entry=Path(plan.desktop_entry_path)
    original=entry.read_bytes()
    original_write=update_module._write_json_atomic

    def fail_update_receipt(path: Path, payload: dict[str, object]) -> None:
        if path.name.startswith("desktop-update-"):
            raise OSError("R5C simulated receipt-store outage")
        original_write(path,payload)

    monkeypatch.setattr(update_module,"_write_json_atomic",fail_update_receipt)
    with pytest.raises(OSError,match="R5C simulated receipt-store outage"):
        DesktopUpdateService().execute(
            request,
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
            receipt_root=state["receipt_root"],
        )
    assert entry.read_bytes()==original
    assert not Path(plan.candidate_bundle_path).exists()
    assert digest(entry.read_bytes())==plan.active_entry_sha256


def test_tampered_retention_marker_blocks_rollback_without_switch(tmp_path: Path) -> None:
    state=_setup(tmp_path)
    plan,updated=_execute_update(state)
    entry=Path(plan.desktop_entry_path)
    active_entry=entry.read_bytes()
    marker=Path(updated.receipt.retention_marker_path)
    forged=json.loads(marker.read_text(encoding="utf-8"))
    forged["retained_version"]="9.9.9"
    marker.write_text(json.dumps(forged),encoding="utf-8")
    with pytest.raises(ValueError,match="digest"):
        plan_desktop_rollback(
            updated.receipt.to_dict(),
            install_root=state["v1"]["install_root"],
            desktop_root=state["desktop_root"],
            applications_root=state["applications_root"],
        )
    assert entry.read_bytes()==active_entry
    assert digest(entry.read_bytes())==plan.candidate_entry_sha256


def test_auditor_refuses_forged_rollback_receipt_and_missing_evidence(tmp_path: Path) -> None:
    state=_setup(tmp_path)
    plan,updated=_execute_update(state)
    rollback=plan_desktop_rollback(
        updated.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    restored=DesktopRollbackService().execute(
        _rollback_request(rollback,updated.receipt),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    kwargs={
        "update_receipt_value":updated.receipt.to_dict(),
        "rollback_receipt_value":restored.receipt.to_dict(),
        "update_receipt_path":Path(updated.receipt_path),
        "rollback_receipt_path":Path(restored.receipt_path),
        "desktop_entry_path":Path(plan.desktop_entry_path),
        "desktop_root":state["desktop_root"],
        "applications_root":state["applications_root"],
        "install_root":state["v1"]["install_root"],
        "receipt_root":state["receipt_root"],
        "observed_failure_mode":"simulated_post_update_health_probe_failure",
    }
    bad=dict(kwargs)
    bad["rollback_receipt_value"]={**restored.receipt.to_dict(),"to_version":"9.9.9"}
    with pytest.raises(ValueError,match="digest"):
        audit_disposable_recovery(**bad)
    bad=dict(kwargs)
    bad["observed_failure_mode"]="real_process_crash_verified"
    with pytest.raises(ValueError,match="simulated"):
        audit_disposable_recovery(**bad)
    Path(restored.receipt_path).unlink()
    with pytest.raises(ValueError,match="receipt"):
        audit_disposable_recovery(**kwargs)
