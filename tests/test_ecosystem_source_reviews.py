from __future__ import annotations

import copy
import json
import unittest

from scripts.sync_public_ecosystem_catalog import DEST, OWNER, SOURCE_CONNECTED, create_snapshot
from scripts.verify_ecosystem_source_reviews import REVIEW_FILE, validate_source_reviews


class EcosystemSourceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(DEST.read_text(encoding="utf-8"))
        cls.reviews = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))

    def test_complete_catalog_and_public_source_review_boundary(self) -> None:
        self.assertEqual(self.catalog["source"], SOURCE_CONNECTED)
        self.assertGreaterEqual(len(self.catalog["entries"]), 194)
        names = [row["name"] for row in self.catalog["entries"]]
        for name in ("GitPorch", "PhiARK", "PhiOS-XR", "BTM", "LENZ", "PhiStream"):
            self.assertIn(name, names)
        self.assertEqual(validate_source_reviews(self.reviews, self.catalog), 9)
        self.assertEqual(self.reviews["default_family"], "UNREVIEWED")
        for item in self.reviews["reviews"]:
            self.assertEqual(item["review_basis"], "README_DECLARATION_ONLY")
            self.assertFalse(item["installed"])
            self.assertFalse(item["launch_authorized"])
            self.assertFalse(item["redistribution_reviewed"])
            self.assertFalse(item["offline_runnable_verified"])

    def test_forged_authority_or_runtime_readiness_rejected(self) -> None:
        for field in ("installed", "launch_authorized", "redistribution_reviewed",
                      "offline_runnable_verified"):
            bad = copy.deepcopy(self.reviews)
            bad["reviews"][0][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_source_reviews(bad, self.catalog)

    def test_unpinned_and_foreign_source_evidence_rejected(self) -> None:
        for key, value in (
            ("source_sha", "main"),
            ("source_sha", "0" * 40),
            ("evidence_url", "https://evil.example/README.md"),
            ("review_basis", "RUNTIME_VERIFIED"),
            ("name", "PrivateHiddenRepo"),
            ("family", "EXECUTION_APPROVED"),
        ):
            bad = copy.deepcopy(self.reviews)
            bad["reviews"][0][key] = value
            if key == "source_sha" and value == "0" * 40:
                bad["reviews"][0]["evidence_url"] = (
                    f"https://github.com/{OWNER}/{bad['reviews'][0]['name']}"
                    f"/blob/{value}/README.md"
                )
                # A syntactically valid but different, pinned SHA is not authenticated here.
                self.assertEqual(validate_source_reviews(bad, self.catalog), 9)
                continue
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_source_reviews(bad, self.catalog)

    def test_duplicate_unsorted_and_unexpected_fields_rejected(self) -> None:
        bad = copy.deepcopy(self.reviews)
        bad["reviews"].append(copy.deepcopy(bad["reviews"][0]))
        with self.assertRaises(ValueError):
            validate_source_reviews(bad, self.catalog)
        bad = copy.deepcopy(self.reviews)
        bad["reviews"][0], bad["reviews"][1] = bad["reviews"][1], bad["reviews"][0]
        with self.assertRaises(ValueError):
            validate_source_reviews(bad, self.catalog)
        bad = copy.deepcopy(self.reviews)
        bad["reviews"][0]["executed"] = False
        with self.assertRaises(ValueError):
            validate_source_reviews(bad, self.catalog)
        bad = copy.deepcopy(self.reviews)
        bad["default_family"] = "WEB_APP"
        with self.assertRaises(ValueError):
            validate_source_reviews(bad, self.catalog)

    def test_removed_public_source_or_wrong_catalog_owner_rejected(self) -> None:
        catalog = create_snapshot(["PhiOS"], source=SOURCE_CONNECTED)
        with self.assertRaises(ValueError):
            validate_source_reviews(self.reviews, catalog)
        catalog = copy.deepcopy(self.catalog)
        catalog["owner"] = "OtherPerson"
        with self.assertRaises(ValueError):
            validate_source_reviews(self.reviews, catalog)


if __name__ == "__main__":
    unittest.main()
