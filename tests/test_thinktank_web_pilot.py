from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.thinktank_web_pilot import verify_dist
from scripts.verify_ecosystem_app_candidates import CANDIDATES


class ThinkTankHostedPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dist = Path(self.tmp.name) / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "assets" / "app.js").write_text("document.querySelector('#root').textContent='Phi';", encoding="utf-8")
        (self.dist / "index.html").write_text(
            '<!doctype html><html><body><div id="root"></div>'
            '<script type="module" src="/assets/app.js"></script></body></html>',
            encoding="utf-8"
        )

    def test_static_dist_has_hashes_and_root_asset_mapping(self) -> None:
        proof = verify_dist(self.dist)
        self.assertEqual(proof["file_count"], 2)
        self.assertEqual(proof["entry_assets"], ["/assets/app.js"])
        self.assertRegex(proof["artifact_set_sha256"], r"^[a-f0-9]{64}$")

    def test_remote_script_rejected(self) -> None:
        (self.dist / "index.html").write_text(
            '<script type="module" src="https://cdn.example/script.js"></script>',
            encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "expected built module script absent|external"):
            verify_dist(self.dist)

    def test_missing_bundle_asset_rejected(self) -> None:
        (self.dist / "assets" / "app.js").unlink()
        (self.dist / "assets" / "app.css").write_text("body {}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing or escaping"):
            verify_dist(self.dist)

    def test_escape_outside_static_root_rejected(self) -> None:
        (self.dist / "index.html").write_text(
            '<script type="module" src="/assets/app.js"></script>'
            '<link rel="stylesheet" href="/../outside.css">',
            encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "unsafe static asset"):
            verify_dist(self.dist)

    def test_symlink_artifact_rejected(self) -> None:
        try:
            (self.dist / "assets" / "alias.js").symlink_to(self.dist / "assets" / "app.js")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_dist(self.dist)

    def test_no_automatic_app_authority_or_license_promotion(self) -> None:
        candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        thinktank = next(x for x in candidates["candidates"] if x["app_key"] == "thinktank-web")
        self.assertEqual(thinktank["review"]["state"], "HELD_FOR_OPERATOR_REVIEW")
        self.assertFalse(thinktank["review"]["installed"])
        self.assertFalse(thinktank["review"]["execution_authorized"])
        self.assertEqual(thinktank["manifest"]["source"]["redistribution"], "unknown")


if __name__ == "__main__":
    unittest.main()
