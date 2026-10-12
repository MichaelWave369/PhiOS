from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.sync_public_ecosystem_catalog import (
    DEST, OWNER, SOURCE_API, collect_public_repositories,
    create_snapshot, make_entry, validate_snapshot
)


class PublicEcosystemCatalogTests(unittest.TestCase):
    def test_committed_catalog_is_offline_valid_and_grants_nothing(self) -> None:
        catalog = json.loads(DEST.read_text(encoding="utf-8"))
        count = validate_snapshot(catalog)
        self.assertGreaterEqual(count, 100)
        names = [entry["name"] for entry in catalog["entries"]]
        self.assertIn("PhiOS", names)
        self.assertIn("SuperPhiVessel", names)
        self.assertIn("think-tank", names)
        for entry in catalog["entries"]:
            self.assertFalse(entry["installed"])
            self.assertFalse(entry["launch_authorized"])
            self.assertFalse(entry["redistribution_reviewed"])
            self.assertEqual(entry["kind"], "source_catalog_entry")

    def test_list_is_deterministic_and_never_promotes_authority(self) -> None:
        content = create_snapshot(["think-tank", "PhiOS", "Domistika"])
        self.assertEqual([r["name"] for r in content["entries"]],
                         ["Domistika", "PhiOS", "think-tank"])
        self.assertEqual(validate_snapshot(content), 3)
        broken = json.loads(json.dumps(content))
        broken["entries"][0]["installed"] = True
        with self.assertRaises(ValueError):
            validate_snapshot(broken)
        broken = json.loads(json.dumps(content))
        broken["entries"][0]["launch_authorized"] = True
        with self.assertRaises(ValueError):
            validate_snapshot(broken)
        broken = json.loads(json.dumps(content))
        broken["entries"][0]["redistribution_reviewed"] = True
        with self.assertRaises(ValueError):
            validate_snapshot(broken)

    def test_unsupported_private_or_foreign_owner_halts_complete_refresh(self) -> None:
        def repo(name: str, **changes: object) -> dict:
            row = {
                "name": name,
                "private": False,
                "owner": {"login": OWNER},
                "html_url": make_entry(name)["repository_url"],
            }
            row.update(changes)
            return row
        for data in (
            [repo("Public"), repo("private-repo", private=True)],
            [repo("Public", owner={"login": "SomeoneElse"})],
            [repo("Public", html_url="https://evil.test/execute")],
            [{"name": "NoProof", "owner": {"login": OWNER}}],
        ):
            with self.assertRaises(ValueError):
                collect_public_repositories(lambda _: data)

    def test_fetches_multiple_complete_public_pages_without_repo_cloning(self) -> None:
        calls: list[str] = []
        names = [f"app-{n:03}" for n in range(102)]
        def fetch(url: str) -> list:
            calls.append(url)
            page = len(calls)
            selected = names[(page - 1) * 100:page * 100]
            return [
                {"name": name, "private": False,
                 "owner": {"login": OWNER},
                 "html_url": make_entry(name)["repository_url"]}
                for name in selected
            ]
        result = collect_public_repositories(fetch)
        self.assertEqual(result, names)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(url.startswith(
            f"https://api.github.com/users/{OWNER}/repos?"
        ) for url in calls))
        self.assertEqual(validate_snapshot(create_snapshot(result)), 102)

    def test_duplicate_unsafe_path_and_nonpublic_metadata_refused(self) -> None:
        for names in (["PhiOS", "phios"], ["../secret"], ["valid", "bad name"]):
            with self.assertRaises(ValueError):
                create_snapshot(names)
        payload = create_snapshot(["PhiOS"])
        payload["entries"][0]["repository_url"] = "http://github.com/MichaelWave369/PhiOS"
        with self.assertRaises(ValueError):
            validate_snapshot(payload)
        payload = create_snapshot(["PhiOS"])
        payload["source"] = "GITHUB_SOMEONES_PRIVATE_CACHE"
        with self.assertRaises(ValueError):
            validate_snapshot(payload)


if __name__ == "__main__":
    unittest.main()
