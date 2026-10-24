"""PhiOS foundation topology is a proposal, never an install or execution grant."""
from __future__ import annotations

import copy
import json
import unittest

from scripts.verify_foundation_topology import TOPOLOGY, validate


class FoundationTopologyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(TOPOLOGY.read_text(encoding="utf-8"))

    def test_actual_frozen_snapshot(self) -> None:
        summary = validate(self.payload)
        self.assertEqual(summary["node_count"], 16)
        self.assertEqual(summary["link_count"], 14)
        self.assertTrue(summary["all_runtime_authority_denied"])

    def test_forged_install_grant_rejected(self) -> None:
        candidate = copy.deepcopy(self.payload)
        candidate["nodes"][0]["installed_in_phios"] = True
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_forged_model_execution_rejected(self) -> None:
        candidate = copy.deepcopy(self.payload)
        candidate["authority"]["model_execute"] = True
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_unreviewed_external_source_rejected(self) -> None:
        candidate = copy.deepcopy(self.payload)
        candidate["nodes"][2]["repository_url"] = "https://example.com/porch"
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_missing_edge_target_rejected(self) -> None:
        candidate = copy.deepcopy(self.payload)
        candidate["links"][0]["to"] = "PhantomKernel"
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_duplicate_and_false_promotion_rejected(self) -> None:
        candidate = copy.deepcopy(self.payload)
        candidate["links"].append(copy.deepcopy(candidate["links"][0]))
        with self.assertRaises(ValueError):
            validate(candidate)
        candidate = copy.deepcopy(self.payload)
        candidate["links"][0]["status"] = "INSTALLED"
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_extra_unreviewed_fields_rejected(self) -> None:
        candidate = copy.deepcopy(self.payload)
        candidate["nodes"][0]["shell_command"] = "sh -c anything"
        with self.assertRaises(ValueError):
            validate(candidate)


if __name__ == "__main__":
    unittest.main()
