"""Read-only ThinkTank guest evidence tests. No apps or permissions are created."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import thinktank_guest_acceptance as gate


class ThinkTankGuestAssessorTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.desktop = self.root / "desktop"
        self.apps = self.root / "applications"
        self.install = self.root / "installed"
        for path in (self.desktop, self.apps, self.install):
            path.mkdir()
        self.candidate = {
            "source_sha": "a" * 40,
            "review": {"state": "HELD_FOR_OPERATOR_REVIEW", "installed": False,
                       "execution_authorized": False, "desktop_launch_grant_verified": False,
                       "external_done": False},
            "manifest": {"app_id": gate.APP_ID,
                         "source": {"repository_url": gate.SOURCE_REPO,
                                    "redistribution": "unknown"}, "permissions": []},
        }
        self.args = dict(desktop_root=self.desktop, applications_root=self.apps,
                         install_root=self.install)

    def _run(self, items=(), **extra):
        with patch.object(gate, "reviewed_candidate", return_value=self.candidate), patch.object(
            gate, "snapshot_desktop_catalog", return_value=SimpleNamespace(
                root_issues=(), items=tuple(items))
        ):
            return gate.assess(**self.args, **extra)

    def _ready(self):
        bundle = self.desktop / gate.APP_ID / "1234567890abcdef"
        bundle.mkdir(parents=True)
        install_path = self.install / gate.APP_ID / "0.1.0"
        meta = install_path / ".phios"
        meta.mkdir(parents=True)
        (bundle / "install-receipt.json").write_text("{}")
        (meta / "package-plan.json").write_text("{}")
        item = SimpleNamespace(app_id=gate.APP_ID, app_version="0.1.0",
                               bundle_path=str(bundle), status="ready",
                               desktop_app_plan_sha256="1" * 64,
                               desktop_launch_grant_sha256="2" * 64)
        install = SimpleNamespace(app_id=gate.APP_ID, app_version="0.1.0",
                                  install_path=str(install_path), package_plan_sha256="4" * 64,
                                  manifest_sha256="5" * 64, artifact_set_sha256="6" * 64,
                                  installed_payload_sha256="7" * 64, sha256=lambda: "3" * 64)
        package = SimpleNamespace(app_id=gate.APP_ID, app_version="0.1.0",
                                  repository_url=gate.SOURCE_REPO,
                                  commit_sha=self.candidate["source_sha"],
                                  manifest_sha256="5" * 64, artifact_set_sha256="6" * 64,
                                  launch_authority=False, sha256=lambda: "4" * 64)
        return item, install, package

    def test_current_reviewed_candidate_is_still_held(self):
        candidate = gate.reviewed_candidate()
        self.assertEqual(candidate["manifest"]["app_id"], gate.APP_ID)
        self.assertEqual(candidate["review"]["state"], "HELD_FOR_OPERATOR_REVIEW")
        self.assertFalse(candidate["review"]["execution_authorized"])

    def test_empty_catalog_remains_held(self):
        report = self._run()
        self.assertEqual(report["status"], "HOLD_FOR_OPERATOR_REVIEW")
        self.assertFalse(report["guest_local_installed_tree_observed"])
        self.assertFalse(report["production_qualified"])

    def test_no_receipts_without_ready_install(self):
        receipt = self.root / "receipt.json"
        receipt.write_text("{}")
        with self.assertRaisesRegex(ValueError, "RECEIPTS_WITHOUT_ACTIVE_INSTALL"):
            self._run(launch_receipt=receipt)

    def test_update_and_rollback_receipts_are_a_pair(self):
        with self.assertRaisesRegex(ValueError, "UPDATE_ROLLBACK_PAIR_REQUIRED"):
            self._run(update_receipt=self.root / "one.json")

    def test_duplicate_active_bundles_blocked(self):
        item = SimpleNamespace(app_id=gate.APP_ID, status="ready")
        with self.assertRaisesRegex(ValueError, "MULTIPLE_ACTIVE"):
            self._run(items=(item, item))

    def test_catalog_root_issues_blocked(self):
        with patch.object(gate, "reviewed_candidate", return_value=self.candidate), patch.object(
            gate, "snapshot_desktop_catalog", return_value=SimpleNamespace(
                root_issues=("unsafe",), items=()
            )
        ):
            with self.assertRaisesRegex(ValueError, "CATALOG_ROOT_ISSUES"):
                gate.assess(**self.args)

    def test_invalid_candidate_promotion_denied(self):
        candidate = json.loads(json.dumps(self.candidate))
        candidate["review"]["installed"] = True
        with patch.object(gate, "CANDIDATES", self.root / "candidates.json"), patch.object(
            gate, "CATALOG_FILE", self.root / "catalog.json"
        ), patch.object(gate, "inspect_candidates", return_value=[]):
            (self.root / "candidates.json").write_text(
                json.dumps({"candidates": [{"app_key": "thinktank-web", **candidate}]})
            )
            (self.root / "catalog.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "CANDIDATE_PROMOTION_OR_DRIFT"):
                gate.reviewed_candidate()

    def test_absent_or_symlink_root_refused(self):
        with self.assertRaisesRegex(ValueError, "ROOT_UNAVAILABLE"):
            gate.safe_root(self.root / "missing")
        alias = self.root / "alias"
        alias.symlink_to(self.desktop)
        with self.assertRaisesRegex(ValueError, "ROOT_SYMLINK"):
            gate.safe_root(alias)

    def test_untrusted_or_oversize_receipt_refused(self):
        source = self.root / "source.json"
        source.write_text("{}")
        alias = self.root / "alias.json"
        alias.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "JSON_PATH_INVALID"):
            gate.read_json(alias)
        source.write_bytes(b"0" * (gate.MAX_JSON_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "JSON_OVERSIZE"):
            gate.read_json(source)

    def test_valid_local_install_does_not_prove_vm_or_release(self):
        item, install, package = self._ready()
        with patch.object(gate.AppInstallReceipt, "from_dict", return_value=install), patch.object(
            gate.BuildPackagePlan, "from_dict", return_value=package
        ):
            report = self._run(items=(item,))
        self.assertTrue(report["guest_local_installed_tree_observed"])
        self.assertTrue(report["guest_local_desktop_catalog_ready"])
        self.assertFalse(report["actual_guest_boot_attested"])
        self.assertFalse(report["installer_or_release_authorized"])
        self.assertFalse(report["external_done"])

    def test_wrong_installed_source_refused(self):
        item, install, package = self._ready()
        package.commit_sha = "0" * 40
        with patch.object(gate.AppInstallReceipt, "from_dict", return_value=install), patch.object(
            gate.BuildPackagePlan, "from_dict", return_value=package
        ):
            with self.assertRaisesRegex(ValueError, "INSTALLED_SOURCE_OR_PACKAGE_LINEAGE_DRIFT"):
                self._run(items=(item,))

    def test_launch_receipt_cannot_mismatch_grant(self):
        item, install, package = self._ready()
        evidence = self.root / "launch.json"
        evidence.write_text("{}")
        fake = SimpleNamespace(app_id=gate.APP_ID, app_version="0.1.0", status="completed",
                               desktop_launch_grant_sha256="0" * 64,
                               desktop_app_plan_sha256="1" * 64,
                               install_receipt_sha256="3" * 64)
        with patch.object(gate.AppInstallReceipt, "from_dict", return_value=install), patch.object(
            gate.BuildPackagePlan, "from_dict", return_value=package
        ), patch.object(gate.DesktopLaunchReceipt, "from_dict", return_value=fake):
            with self.assertRaisesRegex(ValueError, "LAUNCH_RECEIPT_NOT_BOUND"):
                self._run(items=(item,), launch_receipt=evidence)

    def test_matching_launch_receipt_is_consistency_only(self):
        item, install, package = self._ready()
        evidence = self.root / "launch.json"
        evidence.write_text("{}")
        fake = SimpleNamespace(app_id=gate.APP_ID, app_version="0.1.0", status="completed",
                               desktop_launch_grant_sha256="2" * 64,
                               desktop_app_plan_sha256="1" * 64,
                               install_receipt_sha256="3" * 64)
        with patch.object(gate.AppInstallReceipt, "from_dict", return_value=install), patch.object(
            gate.BuildPackagePlan, "from_dict", return_value=package
        ), patch.object(gate.DesktopLaunchReceipt, "from_dict", return_value=fake):
            report = self._run(items=(item,), launch_receipt=evidence)
        self.assertTrue(report["launch_receipt_consistency_checked"])
        self.assertFalse(report["production_qualified"])


if __name__ == "__main__":
    unittest.main()
