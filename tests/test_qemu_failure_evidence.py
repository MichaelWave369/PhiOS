"""Offline, fail-closed VM qualification diagnostics regression tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "packaging" / "linux" / "tests"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from qemu_failure_evidence import snapshot  # noqa: E402


def test_snapshot_has_exit_code_and_hashes_but_no_raw_guest_text(tmp_path, monkeypatch):
    serial = tmp_path / "serial.log"
    stderr = tmp_path / "qemu.log"
    serial.write_bytes(
        b"password=do-not-persist-this\nBdsDxe: starting Boot0002\n"
        b"PHIOS_BOOT_FAILED\n"
    )
    stderr.write_text("qemu abruptly exited\n", encoding="utf-8")
    monkeypatch.setattr("qemu_failure_evidence._memory_events", lambda: {
        "oom": 3, "oom_kill": 1,
    })
    monkeypatch.setattr("qemu_failure_evidence._host_memory", lambda: {
        "MemAvailable_kib": 1234,
    })
    info = snapshot(
        stage="qa-live-media-recovery",
        process=Mock(poll=lambda: -9),
        serial_log=serial,
        qemu_log=stderr,
        failure=RuntimeError("recovery qualification failed"),
        memory_events_before={"oom": 2, "oom_kill": 0},
    )
    assert info["qemu_exit_code_before_cleanup"] == -9
    assert info["qemu_termination_signal_if_negative"] == 9
    assert info["cgroup_memory_events_delta_during_stage"] == {
        "oom": 1, "oom_kill": 1,
    }
    assert info["recent_serial_markers"]["uefi_boot_dispatch_seen"]
    assert info["recent_serial_markers"]["guest_failed_marker_seen"]
    assert info["serial_log"]["bytes"] == serial.stat().st_size
    assert info["serial_log"]["sha256"]
    assert info["action_authority"] is False
    assert "password" not in json.dumps(info)
    assert "do-not-persist-this" not in json.dumps(info)


def test_missing_serial_and_running_process_are_descriptive_not_success(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("qemu_failure_evidence._memory_events", lambda: {})
    data = snapshot(
        stage="normal-restore-live",
        process=Mock(poll=lambda: None),
        serial_log=tmp_path / "missing-serial.log",
        qemu_log=tmp_path / "missing-qemu.log",
        failure=RuntimeError("channel closed"),
    )
    assert data["qemu_exit_code_before_cleanup"] is None
    assert data["serial_log"]["present"] is False
    assert data["recent_serial_markers"]["phios_recovery_marker_seen"] is False
    assert data["action_authority"] is False


def test_recovery_quit_before_boot_preserves_pre_cleanup_diagnostics(tmp_path, monkeypatch):
    import qemu_install  # type: ignore[import-not-found]

    fake_iso = tmp_path / "fake.iso"
    fake_iso.write_bytes(b"fixture-only")
    receipt = {"commands": [], "recovery_checkpoint_generation": "a" * 32}
    stopped = []
    process = Mock()
    process.poll.return_value = -9
    monkeypatch.setattr(qemu_install.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(qemu_install, "stop", lambda proc: stopped.append(proc))
    with pytest.raises(RuntimeError, match="recovery fixture failed"):
        qemu_install.recover_live(
            ["qemu-system-x86_64"], fake_iso, tmp_path, receipt
        )
    assert stopped == [process]
    details = receipt["recovery_vm_failure"]
    assert details["qemu_exit_code_before_cleanup"] == -9
    assert details["stage"] == "qa-live-media-recovery"
    assert details["action_authority"] is False
    assert receipt.get("matched_root_efi_restored") is not True


def test_normal_live_quit_before_transport_is_not_promoted(tmp_path, monkeypatch):
    import qemu_normal_live  # type: ignore[import-not-found]

    fake_iso = tmp_path / "fake.iso"
    fake_iso.write_bytes(b"fixture-only")
    receipt = {"commands": []}
    process = Mock()
    process.poll.return_value = -9
    monkeypatch.setattr(qemu_normal_live.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(RuntimeError, match="exited before transport"):
        qemu_normal_live.drive_live(
            ["qemu-system-x86_64"], fake_iso, "a" * 40,
            tmp_path, receipt, stage="restore", generation="b" * 32,
        )
    detail = receipt["normal_live_vm_failures"][0]
    assert detail["qemu_exit_code_before_cleanup"] == -9
    assert detail["stage"] == "normal-restore-live"
    assert detail["action_authority"] is False
