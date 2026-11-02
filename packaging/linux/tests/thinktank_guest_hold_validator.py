"""Fail-closed host-side verification of real installed guest HOLD observations.

The guest emitted receipt alone is not independent cryptographic attestation.
The QEMU harness binds it to its authenticated serial transcript, exact source,
distinct boot identities and no attached VM network interface.
"""
from __future__ import annotations

import re
from typing import Any

SCHEMA = "phios.thinktank_guest_hold_boot.v0.1"
FIELDS = {
    "schema", "source_commit", "boot_id", "phase", "uid",
    "guest_interface_names", "guest_login_observed", "app_platform_cli_observed",
    "no_thinktank_install_or_desktop_grant_observed", "status",
    "app_installed", "app_launch_verified", "app_rollback_verified",
    "guest_network_policy_attested", "redistribution_approved",
    "production_qualified", "external_done",
}
FALSE = (
    "app_installed", "app_launch_verified", "app_rollback_verified",
    "guest_network_policy_attested", "redistribution_approved",
    "production_qualified", "external_done",
)

def verify_hold_observation(value: Any, *, source: str, phase: int,
                            observed_boot_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("THINKTANK_GUEST_HOLD_UNEXPECTED_RECEIPT_FIELDS")
    if (not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{40}", source) is None
            or value["source_commit"] != source
            or type(value["phase"]) is not int or value["phase"] != phase
            or value["boot_id"] != observed_boot_id
            or re.fullmatch(r"[0-9a-f]{32}", observed_boot_id) is None
            or type(value["uid"]) is not int or value["uid"] != 1000
            or value["schema"] != SCHEMA
            or value["status"] != "HOLD_FOR_OPERATOR_REVIEW"
            or value["guest_interface_names"] != ["lo"]
            or value["guest_login_observed"] is not True
            or value["app_platform_cli_observed"] is not True
            or value["no_thinktank_install_or_desktop_grant_observed"] is not True
            or any(value[name] is not False for name in FALSE)):
        raise ValueError("THINKTANK_GUEST_HOLD_IDENTITY_OR_AUTHORITY_DRIFT")
    return value


def verify_boot_series(values: Any, *, source: str,
                       observed_boot_ids: list[str], phases: int) -> None:
    if (not isinstance(values, list) or len(values) != phases
            or len(observed_boot_ids) != phases
            or len(set(observed_boot_ids)) != phases):
        raise ValueError("THINKTANK_GUEST_HOLD_BOOT_COVERAGE_INCOMPLETE")
    for index, value in enumerate(values, start=1):
        verify_hold_observation(value, source=source, phase=index,
                                observed_boot_id=observed_boot_ids[index - 1])
