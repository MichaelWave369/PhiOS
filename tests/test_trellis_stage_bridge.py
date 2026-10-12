"""v0.60: bridge is a staging adapter, never an OS package executor."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import trellis_stage_bridge as bridge


class TrellisBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = bridge.candidates()

    def test_pinned_trellis_upstream_is_merged_mit_revision(self):
        # This is a deliberately frozen CI source contract, not a floating main branch.
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/trellis-stage-bridge.yml").read_text()
        docs = (root / "docs/PHIOS_TRELLIS_BRIDGE_V0.60.md").read_text()
        expected = "8c8f54f1539c688fd02247f82c9bd48d0b5444c1"
        historic = "c4036f38e8b635709d069e505506191dfccf8c5c"
        self.assertIn("ref: " + expected, workflow)
        self.assertIn('rev-parse HEAD)" = ' + expected, workflow)
        self.assertNotIn(historic, workflow)
        self.assertIn('grep -Fxq \'license = "MIT"\' .ci-sources/Trellis/Cargo.toml', workflow)
        self.assertIn("grep -Fxq 'MIT License' .ci-sources/Trellis/LICENSE", workflow)
        self.assertIn("test -f .ci-sources/Trellis/docs/LICENSE_TRANSITION.md", workflow)
        self.assertIn(expected, docs)
        self.assertIn("AGPL-3.0-only", docs)  # historical revisions only
        self.assertIn(historic, docs)

    def test_only_reviewed_candidates_are_plannable(self):
        for key in ("vessie-web", "thinktank-web"):
            p = bridge.plan(key)
            self.assertEqual(p["candidate"], key)
            self.assertEqual(p["source_sha"], self.entries[key]["source_sha"])
            self.assertTrue(p["staging_only"])
            for guard in ("trellis_executed_by_bridge", "installed_by_phios",
                          "launch_authority", "redistribution_reviewed",
                          "runtime_offline_verified", "external_done"):
                self.assertFalse(p[guard])
        with self.assertRaisesRegex(ValueError, "UNKNOWN_CANDIDATE"):
            bridge.plan("unreviewed-app")

    def fixture(self, root: Path, *, key="vessie-web"):
        checkout = root / "repo"
        checkout.mkdir()
        asset_root = checkout / self.entries[key]["source_build"]["current_output_from_repo_root"]
        (asset_root / "assets").mkdir(parents=True)
        (asset_root / "index.html").write_text(
            '<html><body><div id="root"></div>'
            '<script type="module" src="./assets/main.js"></script>'
            '<link rel="stylesheet" href="./assets/main.css"></body></html>')
        (asset_root / "assets/main.js").write_text('console.log("synthetic fixture")')
        (asset_root / "assets/main.css").write_text('body{margin:0}')
        return checkout, asset_root

    def test_staging_produces_trellis_compatible_checksum_without_grants(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checkout, _ = self.fixture(root)
            output = root / "stage"
            with patch.object(bridge, "pinned_git_sha", return_value=self.entries["vessie-web"]["source_sha"]):
                report = bridge.stage("vessie-web", checkout, output)
            self.assertEqual(report["candidate"], "vessie-web")
            self.assertEqual(report["payload_sha256"], bridge.dir_digest(
                output / "payload", bridge.regular_files(output / "payload"))[0])
            self.assertEqual(len(report["files"]), 3)
            self.assertEqual(report["source_sha"], self.entries["vessie-web"]["source_sha"])
            spec = (output / report["spec"]).read_text()
            self.assertIn("checksum_sha256: " + report["payload_sha256"], spec)
            self.assertIn("kind: source", spec)
            self.assertIn("signature: null", spec)
            self.assertIn("registry: phios-untrusted-staging-only", spec)
            self.assertIn('    - "assets"', spec)
            self.assertIn('    - "index.html"', spec)
            self.assertNotIn("post_install:\n  policy:", spec)
            self.assertFalse(report["installed_by_phios"])
            self.assertFalse(report["launch_authority"])
            with self.assertRaisesRegex(ValueError, "DESTINATION_EXISTS"):
                with patch.object(bridge, "pinned_git_sha", return_value=self.entries["vessie-web"]["source_sha"]):
                    bridge.stage("vessie-web", checkout, output)

    def test_wrong_source_commit_rejected_before_any_stage_files(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checkout, _ = self.fixture(root)
            output = root / "stage"
            with patch.object(bridge, "pinned_git_sha", return_value="0"*40):
                with self.assertRaisesRegex(ValueError, "SOURCE_SHA_MISMATCH"):
                    bridge.stage("vessie-web", checkout, output)
            self.assertFalse(output.exists())

    def test_pages_absolute_asset_paths_and_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checkout, assets = self.fixture(root)
            (assets / "index.html").write_text(
                '<div id="root"></div><script src="/SuperPhiVessel/vessie/assets/main.js"></script>')
            with patch.object(bridge, "pinned_git_sha", return_value=self.entries["vessie-web"]["source_sha"]):
                with self.assertRaisesRegex(ValueError, "NONRELOCATABLE_PAGES_ASSET_BASE"):
                    bridge.stage("vessie-web", checkout, root / "stage")
            self.assertFalse((root / "stage").exists())
            (assets / "index.html").write_text(
                '<div id="root"></div><script src="./assets/main.js"></script>')
            (assets / "assets/evil.js").symlink_to(assets / "assets/main.js")
            with patch.object(bridge, "pinned_git_sha", return_value=self.entries["vessie-web"]["source_sha"]):
                with self.assertRaisesRegex(ValueError, "SOURCE_NONREGULAR_FILE"):
                    bridge.stage("vessie-web", checkout, root / "stage")

    def test_malicious_or_incomplete_staged_receipts_are_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            checkout, _ = self.fixture(root)
            stage = root / "stage"
            with patch.object(bridge, "pinned_git_sha", return_value=self.entries["vessie-web"]["source_sha"]):
                report = bridge.stage("vessie-web", checkout, stage)
            home = root / "trellis-home"
            home.mkdir()
            altered = dict(report)
            altered["launch_authority"] = True
            (stage / "bridge-receipt.json").write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "RECEIPT_AUTHORITY"):
                bridge.verify_staged(stage, home)
            altered = dict(report)
            altered["spec"] = "../untrusted.yaml"
            (stage / "bridge-receipt.json").write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "SPEC_PATH"):
                bridge.verify_staged(stage, home)
            (stage / "bridge-receipt.json").write_text(json.dumps(report))
            (stage / "payload/assets/main.js").write_text("tampered output!")
            with self.assertRaisesRegex(ValueError, "STAGED_PAYLOAD_DRIFT"):
                bridge.verify_staged(stage, home)

    def test_package_spec_rejects_uncontrolled_tokens(self):
        with self.assertRaisesRegex(ValueError, "INVALID_SOURCE_DIGEST"):
            bridge.spec_yaml("phios-vessie-web", "bad", ["assets"], "https://example.org")
        with self.assertRaisesRegex(ValueError, "INVALID_SPEC_ENTRY"):
            bridge.spec_yaml("phios-vessie-web", "0"*64, ["../bin"], "https://example.org")


if __name__ == "__main__":
    unittest.main()
