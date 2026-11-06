"""R5E serial-marker refusal tests; synthetic receipts, no QEMU claim."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging/linux/tests"))
from r5e_guest_validator import validate_r5e_guest as check

SOURCE = "a" * 40


def receipt(phase, boot):
    return {
        "schema": "phios.r5e_installed_desktop_observation.v0.1",
        "scope": "disposable_installed_qemu_guest_test_only",
        "source_commit": SOURCE, "phase": phase, "boot_id": boot, "uid": 1000,
        "desktop_registration_executed_in_guest": True,
        "desktop_update_and_rollback_executed_in_guest": True,
        "active_version": "1.0.0", "fixture_app_process_healthy": True,
        "data_sha256": "c" * 64,
        "update_receipt_sha256": "d" * 64,
        "rollback_receipt_sha256": "e" * 64,
        "real_app_install_service_executed": False,
        "publisher_identity_verified": False,
        "production_install_authority": False,
        "physical_hardware_qualified": False,
        "production_release_authorized": False,
    }


def test_three_guest_reports_have_consistent_identity():
    a, b, c = receipt(1, "1"*32), receipt(2, "2"*32), receipt(3, "3"*32)
    assert check(a, source=SOURCE, phase=1, boot_id=a["boot_id"], previous=[]) == a
    assert check(b, source=SOURCE, phase=2, boot_id=b["boot_id"], previous=[a]) == b
    assert check(c, source=SOURCE, phase=3, boot_id=c["boot_id"], previous=[a,b]) == c


@pytest.mark.parametrize("key,value", [
    ("source_commit", "b"*40), ("uid", 0), ("uid", True),
    ("scope", "physical-device"), ("active_version", "2.0.0"),
    ("production_install_authority", True), ("publisher_identity_verified", True),
    ("real_app_install_service_executed", True), ("fixture_app_process_healthy", False),
    ("data_sha256", "bad"), ("phase", True),
    ("desktop_update_and_rollback_executed_in_guest", False),
])
def test_refuse_falsified_first_boot(key, value):
    a = receipt(1, "1"*32)
    a[key] = value
    with pytest.raises(ValueError):
        check(a, source=SOURCE, phase=1, boot_id="1"*32, previous=[])


@pytest.mark.parametrize("key,value", [
    ("update_receipt_sha256", "bad"), ("rollback_receipt_sha256", None),
    ("data_sha256", "f"*64), ("production_release_authorized", True),
    ("boot_id", "1"*32), ("desktop_registration_executed_in_guest", False),
])
def test_refuse_falsified_second_boot(key, value):
    a, b = receipt(1, "1"*32), receipt(2, "2"*32)
    b[key] = value
    with pytest.raises(ValueError):
        check(b, source=SOURCE, phase=2, boot_id=b["boot_id"], previous=[a])


def test_refuse_missing_previous_and_replayed_transition():
    a, b, c = receipt(1, "1"*32), receipt(2, "2"*32), receipt(3, "3"*32)
    with pytest.raises(ValueError):
        check(c, source=SOURCE, phase=3, boot_id=c["boot_id"], previous=[a])
    c["rollback_receipt_sha256"] = "f"*64
    with pytest.raises(ValueError):
        check(c, source=SOURCE, phase=3, boot_id=c["boot_id"], previous=[a,b])


def test_refuse_unrecognized_claim_fields():
    a = receipt(1, "1"*32)
    a["signed_release_authorized"] = True
    with pytest.raises(ValueError):
        check(a, source=SOURCE, phase=1, boot_id=a["boot_id"], previous=[])
