from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.thinktank_web_pilot import verify_committed_lock, verify_dist
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

    def prepare_source(self) -> tuple[Path, Path]:
        source = Path(self.tmp.name) / "source"
        source.mkdir()
        manifest = {
            "name": "phi-think-tank",
            "version": "0.1.0",
            "dependencies": {"react": "1.0.0"},
            "devDependencies": {},
        }
        lock = {
            "name": "phi-think-tank",
            "version": "0.1.0",
            "lockfileVersion": 3,
            "packages": {
                "": manifest,
                "node_modules/react": {
                    "version": "1.0.0",
                    "integrity": "sha512-test-fixture-not-production",
                },
            },
        }
        (source / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = source / "package-lock.json"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add",
                        "package.json", "package-lock.json"], check=True)
        subprocess.run(
            ["git", "-C", str(source), "-c", "user.name=PhiOS CI",
             "-c", "user.email=ci@example.invalid",
             "commit", "-qm", "Test lock fixture"], check=True
        )
        return source, lock_path

    def test_committed_lock_provenance_and_exact_manifest_root(self) -> None:
        source, lock = self.prepare_source()
        result = verify_committed_lock(source, lock)
        self.assertEqual(result["package_count"], 2)
        self.assertRegex(result["sha256"], r"^[a-f0-9]{64}$")

    def test_post_checkout_lock_mutation_fails_closed(self) -> None:
        source, lock = self.prepare_source()
        lock.write_text(lock.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inputs changed|differs from pinned"):
            verify_committed_lock(source, lock)

    def test_untracked_lock_rejected(self) -> None:
        source, lock = self.prepare_source()
        subprocess.run(["git", "-C", str(source), "rm", "--cached", "package-lock.json"],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "committed upstream"):
            verify_committed_lock(source, lock)

    def test_inconsistent_manifest_vs_committed_lock_rejected(self) -> None:
        source, lock = self.prepare_source()
        manifest = json.loads((source / "package.json").read_text(encoding="utf-8"))
        manifest["dependencies"]["react"] = "2.0.0"
        (source / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "package.json"], check=True)
        subprocess.run(
            ["git", "-C", str(source), "-c", "user.name=PhiOS CI",
             "-c", "user.email=ci@example.invalid",
             "commit", "-qm", "Test intentionally inconsistent dependency"], check=True
        )
        with self.assertRaisesRegex(ValueError, "lockfile root differs"):
            verify_committed_lock(source, lock)

    def test_no_automatic_app_authority_or_license_promotion(self) -> None:
        candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        thinktank = next(x for x in candidates["candidates"] if x["app_key"] == "thinktank-web")
        self.assertEqual(thinktank["review"]["state"], "HELD_FOR_OPERATOR_REVIEW")
        self.assertFalse(thinktank["review"]["installed"])
        self.assertFalse(thinktank["review"]["execution_authorized"])
        self.assertEqual(thinktank["manifest"]["source"]["redistribution"], "unknown")


if __name__ == "__main__":
    unittest.main()
