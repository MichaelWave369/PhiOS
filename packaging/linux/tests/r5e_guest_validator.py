"""Fail closed on R5E's installed-QEMU serial observations; not a signature verifier."""
import re

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_BOOT = re.compile(r"[0-9a-f]{32}\Z")
_REQUIRED = {
    "schema", "scope", "source_commit", "phase", "boot_id", "uid",
    "desktop_registration_executed_in_guest",
    "desktop_update_and_rollback_executed_in_guest", "active_version",
    "fixture_app_process_healthy", "data_sha256", "update_receipt_sha256",
    "rollback_receipt_sha256", "real_app_install_service_executed",
    "publisher_identity_verified", "production_install_authority",
    "physical_hardware_qualified", "production_release_authorized",
}


def validate_r5e_guest(value, *, source, phase, boot_id, previous):
    """Validate exact source, observed boot identity, continuity, and held authority."""
    if not isinstance(value, dict) or set(value) != _REQUIRED:
        raise ValueError("R5E guest receipt fields invalid")
    if not isinstance(source, str) or not _SHA.fullmatch(source):
        raise ValueError("R5E host source identity invalid")
    if phase not in (1, 2, 3) or type(value["phase"]) is not int:
        raise ValueError("R5E phase invalid")
    if (value["schema"] != "phios.r5e_installed_desktop_observation.v0.1"
            or value["scope"] != "disposable_installed_qemu_guest_test_only"
            or value["source_commit"] != source or value["phase"] != phase
            or value["boot_id"] != boot_id or not _BOOT.fullmatch(str(boot_id))
            or type(value["uid"]) is not int or value["uid"] != 1000
            or value["active_version"] != "1.0.0"):
        raise ValueError("R5E guest identity mismatch")
    if (value["desktop_registration_executed_in_guest"] is not True
            or value["desktop_update_and_rollback_executed_in_guest"] is not True
            or value["fixture_app_process_healthy"] is not True
            or any(value[key] is not False for key in (
                "real_app_install_service_executed", "publisher_identity_verified",
                "production_install_authority", "physical_hardware_qualified",
                "production_release_authorized"))):
        raise ValueError("R5E guest claimed authority or lacked desktop lifecycle")
    if not isinstance(value["data_sha256"], str) or not _DIGEST.fullmatch(value["data_sha256"]):
        raise ValueError("R5E user data hash invalid")
    if phase == 1:
        if previous:
            raise ValueError("R5E first boot cannot carry earlier observations")
    else:
        if len(previous) != phase - 1 or previous[-1]["phase"] != phase - 1:
            raise ValueError("R5E prior boot evidence missing")
        if value["data_sha256"] != previous[0]["data_sha256"]:
            raise ValueError("R5E user data did not survive reboot/rollback")
        if value["boot_id"] in {item["boot_id"] for item in previous}:
            raise ValueError("R5E boot ID replay")
    for key in ("update_receipt_sha256", "rollback_receipt_sha256"):
        if not isinstance(value[key], str) or not _DIGEST.fullmatch(value[key]):
            raise ValueError("R5E transition receipt hash invalid")
        if phase > 1 and value[key] != previous[0][key]:
            raise ValueError("R5E transition receipt changed after reboot")
    return dict(value)
