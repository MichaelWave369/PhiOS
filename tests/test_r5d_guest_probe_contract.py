"""Guard the R5D injected-guest probe and the QEMU evidence parser contract."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "packaging/linux/tests/living_app_guest.py"
VM = ROOT / "packaging/linux/tests/qemu_install.py"


def test_both_guest_scripts_compile_and_no_prod_claims():
    guest = GUEST.read_text(encoding="utf-8")
    ast.parse(guest, filename=str(GUEST))
    spec = importlib.util.spec_from_file_location("r5d_guest_fixture_only", GUEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ast.parse(module.R5D_GUEST_APP, filename="installed-vm-test-only-app")
    assert "ThreadingHTTPServer" in module.R5D_GUEST_APP
    assert '"127.0.0.1"' in module.R5D_GUEST_APP
    assert "source_commit" in module.R5D_GUEST_APP
    assert "if phase == 1:" in guest
    assert "phase - 1" in guest
    assert '"test_app_process_http_healthy": True' in guest
    assert '"signed_app_artifact_installed": False' in guest
    assert '"app_platform_update_and_rollback_executed_inside_guest": False' in guest
    assert '"user_data_general_rollback_verified": False' in guest
    assert '"production_install_authority": False' in guest


def test_installed_vm_requires_real_guest_health_marker_per_boot():
    code = VM.read_text(encoding="utf-8")
    assert "living_app_guest.py" in code
    assert "r5d_guest_live_check({source!r}, {phase})" in code
    assert 'wait_for(r"PHIOS_R5D_GUEST_APP_OK:' in code
    assert 'receipt.setdefault("r5d_guest_app_boots", []).append(guest)' in code
    assert "disposable_installed_qemu_guest_test_only" in code
    assert "guest.get(\"source_commit\") != source" in code
    assert 'guest.get("test_app_process_http_healthy") is not True' in code
    assert 'guest.get("signed_app_artifact_installed") is not False' in code
    assert 'guest.get("production_install_authority") is not False' in code
