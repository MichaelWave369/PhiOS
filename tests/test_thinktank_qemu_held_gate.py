"""Synthetic host-side gate tests; they do not boot QEMU or install ThinkTank."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1] / "packaging" / "linux" / "tests"
sys.path.insert(0, str(TESTS))
from thinktank_guest_hold_validator import verify_boot_series, verify_hold_observation  # noqa: E402

SOURCE = "a" * 40
BOOTS = ["1" * 32, "2" * 32, "3" * 32]


def receipt(phase: int = 1, boot_id: str = BOOTS[0]) -> dict:
    return {
        "schema": "phios.thinktank_guest_hold_boot.v0.1",
        "source_commit": SOURCE,
        "boot_id": boot_id,
        "phase": phase,
        "uid": 1000,
        "guest_interface_names": ["lo"],
        "guest_login_observed": True,
        "app_platform_cli_observed": True,
        "no_thinktank_install_or_desktop_grant_observed": True,
        "status": "HOLD_FOR_OPERATOR_REVIEW",
        "app_installed": False,
        "app_launch_verified": False,
        "app_rollback_verified": False,
        "guest_network_policy_attested": False,
        "redistribution_approved": False,
        "production_qualified": False,
        "external_done": False,
    }


class ThinkTankQemuHeldGateTests(unittest.TestCase):
    def test_clean_guest_hold_observation(self):
        row = receipt()
        self.assertIs(verify_hold_observation(row, source=SOURCE, phase=1,
                                              observed_boot_id=BOOTS[0]), row)

    def test_three_distinct_installed_guest_boots(self):
        verify_boot_series([receipt(i, BOOTS[i - 1]) for i in (1, 2, 3)],
                           source=SOURCE, observed_boot_ids=BOOTS, phases=3)

    def test_missing_second_boot_refused(self):
        with self.assertRaisesRegex(ValueError, "COVERAGE_INCOMPLETE"):
            verify_boot_series([receipt()], source=SOURCE, observed_boot_ids=BOOTS,
                               phases=3)

    def test_replayed_boot_id_refused(self):
        with self.assertRaisesRegex(ValueError, "COVERAGE_INCOMPLETE"):
            verify_boot_series([receipt(1), receipt(2), receipt(3)],
                               source=SOURCE, observed_boot_ids=[BOOTS[0]] * 3, phases=3)

    def test_mismatched_source_refused(self):
        row = receipt()
        row["source_commit"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "IDENTITY_OR_AUTHORITY"):
            verify_hold_observation(row, source=SOURCE, phase=1,
                                    observed_boot_id=BOOTS[0])

    def test_false_promotion_refused(self):
        for key in ("app_installed", "app_launch_verified", "app_rollback_verified",
                    "guest_network_policy_attested", "redistribution_approved",
                    "production_qualified", "external_done"):
            with self.subTest(key=key):
                row = receipt()
                row[key] = True
                with self.assertRaisesRegex(ValueError, "IDENTITY_OR_AUTHORITY"):
                    verify_hold_observation(row, source=SOURCE, phase=1,
                                            observed_boot_id=BOOTS[0])

    def test_wrong_status_refused(self):
        row = receipt()
        row["status"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "IDENTITY_OR_AUTHORITY"):
            verify_hold_observation(row, source=SOURCE, phase=1,
                                    observed_boot_id=BOOTS[0])

    def test_guest_nic_refused(self):
        row = receipt()
        row["guest_interface_names"] = ["eth0", "lo"]
        with self.assertRaisesRegex(ValueError, "IDENTITY_OR_AUTHORITY"):
            verify_hold_observation(row, source=SOURCE, phase=1,
                                    observed_boot_id=BOOTS[0])

    def test_spoofed_phase_and_uid_refused(self):
        for key, val in (("phase", True), ("phase", 2), ("uid", True),
                         ("uid", 0)):
            with self.subTest(key=key, val=val):
                row = receipt()
                row[key] = val
                with self.assertRaisesRegex(ValueError, "IDENTITY_OR_AUTHORITY"):
                    verify_hold_observation(row, source=SOURCE, phase=1,
                                            observed_boot_id=BOOTS[0])

    def test_unexpected_or_missing_fields_refused(self):
        row = receipt()
        row["allow_install"] = True
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_RECEIPT_FIELDS"):
            verify_hold_observation(row, source=SOURCE, phase=1,
                                    observed_boot_id=BOOTS[0])
        row = receipt()
        row.pop("external_done")
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_RECEIPT_FIELDS"):
            verify_hold_observation(row, source=SOURCE, phase=1,
                                    observed_boot_id=BOOTS[0])

    def test_guest_probe_has_valid_syntax_and_no_install_calls(self):
        path = TESTS / "thinktank_guest_hold_probe.py"
        code = path.read_text(encoding="utf-8")
        ast.parse(code)
        self.assertNotIn("subprocess", code)
        self.assertNotIn("phi-app install", code)
        self.assertIn("snapshot_desktop_catalog", code)
        self.assertIn("HOLD_FOR_OPERATOR_REVIEW", code)


if __name__ == "__main__":
    unittest.main()
