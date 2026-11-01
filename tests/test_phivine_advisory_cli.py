"""End-to-end PhiOS phi-app review of an untrusted PhiVine handoff."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phios.apps.cli import main
from phios.apps.phivine_advisory_intake import REQUIRED_GATES


def handoff(*, valid=True):
    record = {
        "schema": "phivine.phios_advisory.v0.1",
        "producer": "phivine", "target": "phios",
        "handoff_type": "local_windows_binary_advisory",
        "status": "HELD_PHIOS_BINARY_INTAKE_NOT_IMPLEMENTED",
        "proposal_id_observed": "pv-" + "2" * 24,
        "artifact": {
            "name": "old.exe", "sha256_observed": "a" * 64,
            "size_bytes_observed": 256, "format_observed": "pe",
            "architecture_observed": "x86_64",
        },
        "requested_effects": {
            "runner_family_requested": "wine",
            "network": "deny_requested",
            "extra_host_filesystem_access": "not_requested",
        },
        "observations": {
            "source_status": "ARTIFACT_MATCHED_STILL_NOT_RUNNABLE",
            "stage_status": "STAGE_MATCHED_NOT_IMMUTABLE_NOT_RUNNABLE",
            "runner_status": "RUNNER_RESOLVED_ELF_OBSERVED_NOT_ATTESTED",
            "source_bytes_match_observed": True,
            "stage_bytes_match_observed": True,
            "runner_elf_observed": True,
        },
        "authority": {
            "phios_native_binary_intake_exists": False,
            "phios_api_called": False, "phios_app_registered": False,
            "trusted_origin_attested": False, "runtime_attested": False,
            "sandbox_verified": False, "install_authorized": False,
            "execution_authorized": False, "effect_lease_present": False,
            "windows_execution_attempted": False,
        },
        "required_before_execution": list(REQUIRED_GATES),
        "limitations": [
            "Unsigned advisory data only.",
            "No immutable execution artifact is present.",
            "No Wine runtime has been attested.",
        ],
    }
    body = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    record["handoff_id"] = "pha-" + hashlib.sha256(body.encode()).hexdigest()[:24]
    if not valid:
        record["authority"]["execution_authorized"] = True
    return record


class PhiAppReviewPhiVineCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "handoff.json"

    def call(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["review-phivine", str(self.path)])
        self.assertEqual(err.getvalue(), "")
        return code, json.loads(out.getvalue())

    def test_good_evidence_is_still_held_and_exit_three(self):
        self.path.write_text(json.dumps(handoff()), encoding="utf-8")
        code, result = self.call()
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["app_registry_read_or_modified"])
        self.assertFalse(result["phios_install_or_launch_called"])

    def test_fake_approval_is_rejected_and_not_displayed(self):
        self.path.write_text(json.dumps(handoff(valid=False)), encoding="utf-8")
        code, result = self.call()
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY")
        self.assertIsNone(result["artifact"])

    def test_invalid_json_returns_held_without_crashing(self):
        self.path.write_text("{broken", encoding="utf-8")
        code, result = self.call()
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY")

    def test_missing_file_returns_held_without_creating(self):
        code, result = self.call()
        self.assertEqual(code, 3)
        self.assertTrue(result["status"].startswith("HELD_"))
        self.assertFalse(self.path.exists())

    def test_no_subprocess_or_install_side_effects(self):
        self.path.write_text(json.dumps(handoff()), encoding="utf-8")
        with patch("subprocess.Popen", side_effect=AssertionError("Popen")), \
             patch("subprocess.run", side_effect=AssertionError("run")):
            code, _ = self.call()
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
