import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import offline_shell_profile as profile
from scripts import trellis_stage_bridge as bridge


class OfflineProfileTests(unittest.TestCase):
    def fixture(self, root: Path):
        stage = root / "stage"
        payload = stage / "payload"
        (payload / "assets").mkdir(parents=True)
        (payload / "index.html").write_text(
            '<html><body><div id="root"></div>'
            '<script type="module" src="./assets/main.js"></script>'
            '</body></html>')
        (payload / "assets/main.js").write_text("console.log('testing')")
        (payload / "assets/main.css").write_text("body{color:red}")
        files = bridge.regular_files(payload)
        digest, _ = bridge.dir_digest(payload, files)
        (stage / "bridge-receipt.json").write_text(json.dumps({
            "candidate": "vessie-web",
            "source_sha": "a" * 40,
            "payload_sha256": digest
        }))
        return stage

    def test_prepared_profile_binds_verified_parent_and_all_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            stage = self.fixture(base)
            output = base / "output"
            with patch.object(profile.bridge, "verify_staged", return_value={
                "candidate": "vessie-web", "all_installed_bytes_rehashed": True
            }):
                report = profile.prepare(stage, base / "unused-home", output, "vessie-web")
            self.assertTrue(report["derived_artifact"])
            self.assertFalse(report["phios_installed"])
            self.assertFalse(report["phios_launch_authorized"])
            self.assertEqual(report["precache_count"], 4)
            self.assertIn('phios-offline-bootstrap.js', (output / "payload/index.html").read_text())
            worker = (output / "payload/phios-offline-sw.js").read_text()
            self.assertIn("OFFLINE_CACHE_DIGEST_DRIFT", worker)
            self.assertIn("Response.error()", worker)
            self.assertIn("assets/main.js", worker)
            self.assertEqual(len(report["files"]), 5)
            spec = (output / report["spec"]).read_text()
            self.assertIn("checksum_sha256: " + report["payload_sha256"], spec)
            with patch.object(profile.bridge, "verify_staged", return_value={
                "candidate": "vessie-web", "all_installed_bytes_rehashed": True
            }):
                with self.assertRaisesRegex(ValueError, "DESTINATION_EXISTS"):
                    profile.prepare(stage, base / "unused-home", output, "vessie-web")

    def test_unreviewed_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_APP"):
            profile.prepare(Path("/nonexistent"), Path("/nonexistent"),
                            Path("/nonexistent"), "../../evil")

    def test_manifest_requires_signed_off_by_prepended_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "assets").mkdir()
            (base / "assets/main.js").write_text("x")
            (base / "index.html").write_text("<html></html>")
            with self.assertRaisesRegex(ValueError, "CACHE_SET_INVALID"):
                profile.precache_manifest(base)


if __name__ == "__main__":
    unittest.main()
