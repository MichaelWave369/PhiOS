"""PhiOS Rung 8: untrusted PhiVine input never becomes permission."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phios.apps.phivine_advisory_intake import (
    MAX_HANDOFF_BYTES,
    REVIEW_SCHEMA,
    REQUIRED_GATES,
    read_phivine_advisory_json,
    review_phivine_advisory,
)


def fixture():
    body = {
        "schema": "phivine.phios_advisory.v0.1",
        "producer": "phivine",
        "target": "phios",
        "handoff_type": "local_windows_binary_advisory",
        "status": "HELD_PHIOS_BINARY_INTAKE_NOT_IMPLEMENTED",
        "proposal_id_observed": "pv-" + "4" * 24,
        "artifact": {
            "name": "legacy.exe",
            "sha256_observed": "a" * 64,
            "size_bytes_observed": 256,
            "format_observed": "pe",
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
            "phios_api_called": False,
            "phios_app_registered": False,
            "trusted_origin_attested": False,
            "runtime_attested": False,
            "sandbox_verified": False,
            "install_authorized": False,
            "execution_authorized": False,
            "effect_lease_present": False,
            "windows_execution_attempted": False,
        },
        "required_before_execution": list(REQUIRED_GATES),
        "limitations": [
            "This is an unsigned advisory record and cannot grant PhiOS authority.",
            "Matching source or staged bytes are momentary observations, not immutable pins.",
            "ELF fingerprints and symlink traces do not attest a Wine runtime.",
            "No Windows executable, Wine runner or shell wrapper is launched.",
            "No source repository intake, installation or trusted broker is invoked.",
            "Absolute local paths are intentionally excluded from this handoff.",
        ],
    }
    return check(body)


def check(record):
    base = {k: v for k, v in record.items() if k != "handoff_id"}
    canonical = json.dumps(base, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    record["handoff_id"] = "pha-" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
    return record


class PhiVineAdvisoryIntakeTests(unittest.TestCase):
    def assert_held(self, payload):
        result = review_phivine_advisory(payload)
        self.assertTrue(result["status"].startswith("HELD_"))
        self.assertEqual(result["schema"], REVIEW_SCHEMA)
        for flag in (
            "repo_profile_schema_used", "repo_compatibility_classification_performed",
            "app_registry_read_or_modified", "phios_install_or_launch_called",
            "operator_approval_minted", "effect_lease_issued",
            "execution_authorized", "windows_binary_executed",
        ):
            self.assertIs(result[flag], False, flag)
        return result

    def test_complete_matching_observations_remain_held(self):
        result = self.assert_held(fixture())
        self.assertEqual(result["status"], "HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE")
        self.assertEqual(result["artifact"]["name"], "legacy.exe")
        self.assertEqual(result["observations"]["stage_bytes_match_observed"], True)
        self.assertEqual(result["requested_effects"]["network"], "deny_requested")
        self.assertEqual(result["unmet_execution_gates"], list(REQUIRED_GATES))

    def test_deterministic_review_id_is_not_a_signature(self):
        a, b = self.assert_held(fixture()), self.assert_held(fixture())
        self.assertEqual(a, b)
        self.assertRegex(a["review_id"], r"^pvr-[0-9a-f]{24}$")

    def test_invalid_producer_proposal_stays_held(self):
        p = fixture()
        p["status"] = "HELD_INVALID_OR_TAMPERED_PROPOSAL"
        p["proposal_id_observed"] = None
        p["artifact"] = None
        p["requested_effects"] = None
        p["observations"] = {
            "source_status": "NOT_CHECKED_INVALID_PLAN",
            "stage_status": "NOT_CHECKED_INVALID_PLAN",
            "runner_status": "NOT_CHECKED_INVALID_PLAN",
            "source_bytes_match_observed": False,
            "stage_bytes_match_observed": False,
            "runner_elf_observed": False,
        }
        result = self.assert_held(check(p))
        self.assertEqual(result["status"], "HELD_PHIVINE_PROPOSAL_INVALID")
        self.assertIsNone(result["artifact"])

    def test_all_approval_flags_forged_even_with_recomputed_id(self):
        for name in fixture()["authority"]:
            p = fixture()
            p["authority"][name] = True
            result = self.assert_held(check(p))
            self.assertEqual(result["status"], "HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY", name)
            self.assertIsNone(result["artifact"])

    def test_changed_digest_cannot_keep_old_checksum(self):
        p = fixture()
        p["artifact"]["sha256_observed"] = "b" * 64
        result = self.assert_held(p)
        self.assertIsNone(result["artifact"])

    def test_recomputed_checksum_still_cannot_invent_permission(self):
        p = fixture()
        p["requested_effects"]["network"] = "allow"
        result = self.assert_held(check(p))
        self.assertIsNone(result["requested_effects"])

    def test_inconsistent_stage_status_rejected(self):
        p = fixture()
        p["observations"]["stage_bytes_match_observed"] = False
        result = self.assert_held(check(p))
        self.assertEqual(result["status"], "HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY")

    def test_unrequested_stage_stays_visible_but_held(self):
        p = fixture()
        p["observations"]["stage_status"] = "NOT_REQUESTED"
        p["observations"]["stage_bytes_match_observed"] = False
        result = self.assert_held(check(p))
        self.assertEqual(result["status"], "HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE")

    def test_reject_unknown_top_level_fields(self):
        p = fixture()
        p["may_execute"] = True
        self.assertIsNone(self.assert_held(check(p))["artifact"])

    def test_reject_unknown_authority_fields(self):
        p = fixture()
        p["authority"]["phi_root_access"] = False
        self.assertIsNone(self.assert_held(check(p))["artifact"])

    def test_reject_unmet_gates_removed(self):
        p = fixture()
        p["required_before_execution"].pop()
        self.assertIsNone(self.assert_held(check(p))["artifact"])

    def test_reject_wrong_schema_and_non_object(self):
        for p in ([], None, 4, {"schema": "phios.repo_profile.v0.1"}):
            self.assertIsNone(self.assert_held(p)["artifact"])

    def test_msi_candidate_is_reviewed_but_never_accepted_for_launch(self):
        p = fixture()
        p["artifact"]["name"] = "legacy-installer.msi"
        p["artifact"]["format_observed"] = "msi_cfb_candidate"
        p["artifact"]["architecture_observed"] = None
        p["observations"]["source_status"] = "HELD_INVALID_OR_TAMPERED_PROPOSAL"
        p["observations"]["source_bytes_match_observed"] = False
        result = self.assert_held(check(p))
        self.assertEqual(result["status"], "HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE")
        self.assertFalse(result["execution_authorized"])

    def test_reject_path_in_filename(self):
        for filename in ("../legacy.exe", "C:\\legacy.exe", "legacy\n.exe"):
            p = fixture()
            p["artifact"]["name"] = filename
            self.assertIsNone(self.assert_held(check(p))["artifact"])

    def test_pathless_result_is_display_only(self):
        p = fixture()
        record = self.assert_held(p)
        self.assertNotIn("path_observed", json.dumps(record))
        self.assertNotIn("stage_store", json.dumps(record))

    def test_reviewer_does_not_touch_launch_registry_or_subprocess(self):
        with patch("subprocess.run", side_effect=AssertionError("spawn")), \
             patch("subprocess.Popen", side_effect=AssertionError("spawn")):
            self.assert_held(fixture())

    def test_local_bounded_json_reader(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "handoff.json"
            original = fixture()
            path.write_text(json.dumps(original), encoding="utf-8")
            self.assertEqual(read_phivine_advisory_json(path), original)
            path.write_bytes(b"x" * (MAX_HANDOFF_BYTES + 1))
            with self.assertRaises(ValueError):
                read_phivine_advisory_json(path)

    def test_local_json_symlink_and_garbage_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "source.json"
            target.write_text("garbage", encoding="utf-8")
            alias = Path(td) / "alias.json"
            alias.symlink_to(target)
            with self.assertRaises(ValueError):
                read_phivine_advisory_json(alias)
            with self.assertRaises(ValueError):
                read_phivine_advisory_json(target)


if __name__ == "__main__":
    unittest.main()
