"""PhiOS Rung 11: untrusted static PhiVine triage is display-only and HELD."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phios.apps.cli import main
from phios.apps.phivine_triage_review import (
    MAX_BYTES, read_phivine_triage_json, review_phivine_triage,
)


def fixture() -> dict:
    return {
        "schema": "phivine.import_triage.v0.1",
        "source_schema": "phivine.pe_imports.v0.1",
        "status": "HELD_STATIC_IMPORT_TRIAGE_REVIEW_ONLY",
        "name": "synthetic.exe",
        "source_sha256_observed": "a" * 64,
        "source_size_bytes_observed": 1024,
        "architecture_observed": "x86_64",
        "static_parser_status": "OBSERVED_IMPORT_NAMES_REVIEW_ONLY",
        "direct_import_dll_count": 2,
        "review_areas": [
            {
                "area": "graphics_apis",
                "dll_names_observed": ["d3d11.dll"],
                "review_prompt": "Human graphics review only.",
                "capability_or_dependency_availability_verified": False,
            },
            {
                "area": "network_apis",
                "dll_names_observed": ["ws2_32.dll"],
                "review_prompt": "Human network policy review only.",
                "capability_or_dependency_availability_verified": False,
            },
        ],
        "unclassified_direct_imports": [],
        "import_scope": "DIRECT_IMPORT_DIRECTORY_ONLY",
        "other_dependencies_not_scanned": [
            "delayed_imports", "dynamic_library_loading",
            "imported_symbols_and_ordinals", "manifests_and_side_by_side",
            "managed_assemblies", "external_installer_effects",
        ],
        "dependency_availability_verified": False,
        "wine_compatibility_verified": False,
        "origin_attested": False,
        "source_immutable": False,
        "sandbox_verified": False,
        "operator_approval_granted": False,
        "effect_lease_issued": False,
        "execution_authorized": False,
        "windows_execution_attempted": False,
        "wine_executed": False,
        "note": "Name-only manual-review hints; no compatibility verdict, runtime probes, or grants.",
    }


class PhiVineStaticTriageReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "triage.json"

    def assert_held(self, payload, valid=True):
        review = review_phivine_triage(payload)
        self.assertTrue(review["status"].startswith("HELD_"))
        for field in (
            "source_immutability_verified", "binary_file_read_by_phios",
            "source_repo_profiler_called", "wine_compatibility_verified",
            "network_granted", "app_registry_read_or_modified",
            "phios_install_or_launch_called", "operator_approval_minted",
            "effect_lease_issued", "execution_authorized", "windows_binary_executed",
        ):
            self.assertIs(review[field], False, field)
        if valid:
            self.assertEqual(review["status"], "HELD_STATIC_DLL_REVIEW_UNTRUSTED")
            self.assertEqual([a["area"] for a in review["review_groups"]],
                             ["graphics_apis", "network_apis"])
        else:
            self.assertEqual(review["status"], "HELD_INVALID_OR_UNTRUSTED_STATIC_TRIAGE")
            self.assertIsNone(review["artifact_name_observed"])
            self.assertEqual(review["review_groups"], [])
        return review

    def test_valid_review_and_no_grants(self):
        v = self.assert_held(fixture())
        self.assertEqual(v["artifact_name_observed"], "synthetic.exe")
        self.assertEqual(v["source_schema"], "phivine.import_triage.v0.1")

    def test_empty_no_imports_remains_held_and_display_only(self):
        p = fixture()
        p["status"] = "HELD_STATIC_INPUT_INSUFFICIENT"
        p["static_parser_status"] = "HELD_NO_IMPORT_TABLE_OBSERVED"
        p["direct_import_dll_count"] = 0
        p["review_areas"] = []
        self.assertEqual(review_phivine_triage(p)["status"], "HELD_STATIC_DLL_REVIEW_UNTRUSTED")
        self.assertEqual(review_phivine_triage(p)["review_groups"], [])

    def test_wrong_fields_and_authority_claims_rejected(self):
        for field in ("dependency_availability_verified", "origin_attested",
                      "sandbox_verified", "operator_approval_granted",
                      "execution_authorized", "effect_lease_issued"):
            p = fixture()
            p[field] = True
            with self.subTest(field=field):
                self.assert_held(p, valid=False)
        p = fixture()
        p["phios_native_install_authorized"] = False
        self.assert_held(p, valid=False)

    def test_concealed_classified_name_rejected(self):
        p = fixture()
        p["review_areas"][0]["dll_names_observed"] = ["d3d11.dll"]
        p["review_areas"] = p["review_areas"][:1]
        p["unclassified_direct_imports"] = ["ws2_32.dll"]
        self.assert_held(p, valid=False)

    def test_inconsistent_counts_and_invented_category_rejected(self):
        for alteration in (
            {"direct_import_dll_count": 3},
            {"import_scope": "ALL_DYNAMIC_IMPORTS"},
            {"status": "COMPATIBLE_WITH_WINE"},
            {"name": "../synthetic.exe"},
            {"source_sha256_observed": "not-hash"},
            {"architecture_observed": "arm64"},
        ):
            with self.subTest(alteration=alteration):
                p = fixture()
                p.update(alteration)
                self.assert_held(p, valid=False)
        p = fixture()
        p["review_areas"][0]["area"] = "root_access"
        self.assert_held(p, valid=False)
        p = fixture()
        p["review_areas"][0]["dll_names_observed"] = ["evil.dll"]
        self.assert_held(p, valid=False)

    def test_duplicate_and_broken_json_rejected(self):
        self.path.write_text('{"schema": 1, "schema": 2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            read_phivine_triage_json(self.path)
        self.path.write_text('{"x": NaN}', encoding="utf-8")
        with self.assertRaises(ValueError):
            read_phivine_triage_json(self.path)
        self.path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_phivine_triage_json(self.path)

    def test_bounded_file_and_symlink(self):
        self.path.write_bytes(b"x" * (MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            read_phivine_triage_json(self.path)
        self.path.write_text(json.dumps(fixture()), encoding="utf-8")
        alias = self.path.parent / "alias.json"
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            read_phivine_triage_json(alias)
        self.assertEqual(read_phivine_triage_json(self.path), fixture())

    def test_cli_always_returns_held_exit_three_without_subprocess(self):
        self.path.write_text(json.dumps(fixture()), encoding="utf-8")
        output = io.StringIO()
        with patch("subprocess.run", side_effect=AssertionError("subprocess")), \
             patch("subprocess.Popen", side_effect=AssertionError("subprocess")), \
             contextlib.redirect_stdout(output):
            code = main(["review-phivine-triage", str(self.path)])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "HELD_STATIC_DLL_REVIEW_UNTRUSTED")

    def test_cli_invalid_and_missing_remains_held(self):
        for contents in ("{broken", None):
            if contents is None:
                self.path.unlink(missing_ok=True)
            else:
                self.path.write_text(contents, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["review-phivine-triage", str(self.path)])
            self.assertEqual(code, 3)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "HELD_INVALID_OR_UNTRUSTED_STATIC_TRIAGE")
            self.assertIsNone(result["artifact_name_observed"])


if __name__ == "__main__":
    unittest.main()
