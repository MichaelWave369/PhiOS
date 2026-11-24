import copy
import unittest

from interop.capability_discovery_v1 import CATALOG, DECLARATIONS, discover, read_json, validate


class CapabilityDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.data = read_json(DECLARATIONS)
        self.catalog = read_json(CATALOG)

    def test_real_checked_in_catalog(self):
        self.assertEqual(len(validate(self.data, self.catalog)["entries"]), 4)
        for row in self.data["entries"]:
            result = discover(self.data, self.catalog, row["capability"], row["input_contract"],
                              row["output_contract"], row["mode"])
            self.assertEqual(result["matches"], [row["id"]])
            self.assertEqual(result["decision"], "REVIEW_CANDIDATES")
            self.assertEqual(result["authority"], "NONE")
            self.assertFalse(result["execution_authorized"])

    def test_no_coercion_or_mode_upgrade(self):
        row = self.data["entries"][0]
        for cap, inp, out, mode in (
            ("unknown", row["input_contract"], row["output_contract"], row["mode"]),
            (row["capability"], "wrong.input", row["output_contract"], row["mode"]),
            (row["capability"], row["input_contract"], "wrong.output", row["mode"]),
            (row["capability"], row["input_contract"], row["output_contract"],
             "synthetic" if row["mode"] == "opt-in-local" else "opt-in-local"),
        ):
            result = discover(self.data, self.catalog, cap, inp, out, mode)
            self.assertEqual(result["decision"], "NO_DECLARED_MATCH")
            self.assertEqual(result["matches"], [])

    def test_reject_forged_grants_unmeasured_cost_and_unpinned_source(self):
        for patch in (
            {"authority": "GRANTED"}, {"execution_authorized": True},
            {"latency_ms": 0}, {"memory_mib": 1}, {"revision": "main"},
            {"repository": "https://github.com/MichaelWave369/UnknownPrivate"},
            {"repository": "https://github.com/OtherOwner/Example"},
            {"evidence": {"path": "../README.md", "start": 1, "end": 2}},
            {"evidence": {"path": "README.md", "start": True, "end": 2}},
            {"mode": "remote"}, {"input_contract": "https://example.com"},
            {"limitations": " "},
        ):
            data = copy.deepcopy(self.data)
            data["entries"][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate(data, self.catalog)

    def test_duplicate_and_catalog_authority_refused(self):
        self.data["entries"].append(copy.deepcopy(self.data["entries"][0]))
        with self.assertRaises(ValueError):
            validate(self.data, self.catalog)
        self.data["entries"].pop()
        self.catalog["entries"][0]["launch_authorized"] = True
        with self.assertRaises(ValueError):
            validate(self.data, self.catalog)

    def test_deterministic_result_when_catalog_order_changes(self):
        row = self.data["entries"][0]
        args = (row["capability"], row["input_contract"], row["output_contract"], row["mode"])
        first = discover(self.data, self.catalog, *args)
        self.data["entries"].reverse()
        self.catalog["entries"].reverse()
        self.assertEqual(first, discover(self.data, self.catalog, *args))


if __name__ == "__main__":
    unittest.main()
