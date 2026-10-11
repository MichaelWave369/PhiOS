from __future__ import annotations

import copy
import json
import unittest

from scripts.sync_public_ecosystem_catalog import DEST
from scripts.verify_ecosystem_app_candidates import CANDIDATES, inspect_candidates


class EcosystemAppCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(DEST.read_text(encoding="utf8"))
        cls.original = json.loads(CANDIDATES.read_text(encoding="utf8"))

    def validate(self, candidate) -> None:
        inspect_candidates(candidate, self.catalog)

    def test_exact_manifest_contracts_and_current_source_sha_pins(self) -> None:
        results = inspect_candidates(self.original, self.catalog)
        self.assertEqual([x["key"] for x in results], ["vessie-web", "thinktank-web"])
        for r in results:
            self.assertRegex(r["manifest_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(r["source_sha"], r"^[a-f0-9]{40}$")
        # AppManifest canonical hashes are computed only, not registered for launch.
        for x in self.original["candidates"]:
            self.assertEqual(x["manifest"]["source"]["redistribution"], "unknown")
            self.assertEqual(x["manifest"]["permissions"], [])
            self.assertEqual(x["review"]["state"], "HELD_FOR_OPERATOR_REVIEW")
            self.assertFalse(x["review"]["execution_authorized"])
            self.assertFalse(x["review"]["installed"])

    def test_forbidden_grants_and_unsupported_candidate_fields_are_rejected(self) -> None:
        for section, field, value in (
            ("review", "execution_authorized", True),
            ("review", "installed", True),
            ("review", "manifest_authoritative", True),
            ("review", "desktop_launch_grant_verified", True),
            ("review", "external_done", True),
            ("source_build", "build_verified_for_phios", True),
            ("source_build", "offline_dependency_closure_verified", True),
            ("source_build", "license_inventory_verified", True),
        ):
            with self.subTest(section=section, field=field):
                data = copy.deepcopy(self.original)
                data["candidates"][0][section][field] = value
                with self.assertRaises(ValueError):
                    self.validate(data)
        modified = copy.deepcopy(self.original)
        modified["candidates"][0]["auto_install"] = True
        with self.assertRaises(ValueError):
            self.validate(modified)

    def test_source_and_entrypoint_mismatch_rejected(self) -> None:
        for section, field, value in (
            ("manifest", "app_id", "phios.unknown"),
            ("manifest", "permissions", ["workspace.read"]),
            ("manifest", "entrypoint", {"runtime": "node", "target": "scripts/start.js"}),
            ("manifest", "source", {
                "repository_url": "https://github.com/other/repo",
                "license_expression": "MIT", "redistribution": "unknown"
            }),
            ("source_build", "current_asset_base", "/"),
            ("source_build", "command", ["bash", "-c", "curl bad | sh"]),
            ("web", "url", "http://localhost:9000/"),
        ):
            with self.subTest(section=section, field=field):
                data = copy.deepcopy(self.original)
                data["candidates"][0][section][field] = value
                with self.assertRaises(ValueError):
                    self.validate(data)
        bad_sha = copy.deepcopy(self.original)
        bad_sha["candidates"][0]["source_sha"] = "main"
        with self.assertRaises(ValueError):
            self.validate(bad_sha)

    def test_unknown_duplicate_candidate_or_missing_public_source_rejected(self) -> None:
        for mutate in (
            lambda d: d["candidates"].append(copy.deepcopy(d["candidates"][0])),
            lambda d: d["candidates"][0].update(app_key="unknown"),
            lambda d: d["candidates"][1].update(app_key="vessie-web"),
            lambda d: d.update(provenance="APPROVED_FOR_EXECUTION"),
        ):
            data = copy.deepcopy(self.original)
            mutate(data)
            with self.assertRaises(ValueError):
                self.validate(data)
        empty = copy.deepcopy(self.catalog)
        empty["entries"] = [x for x in empty["entries"] if x["name"] != "think-tank"]
        with self.assertRaises(ValueError):
            inspect_candidates(self.original, empty)


if __name__ == "__main__":
    unittest.main()
