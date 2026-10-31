"""R2 scoped snapshot portability. No EXIT-VERIFIED claim from these tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from phios.state_recovery import backup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sovereignty_exit_r2 import (  # noqa: E402
    bundle, inventory, restore_snapshot, verify_bundle,
)
from sovereignty_exit_v01 import pack  # noqa: E402


class SovereigntyR2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "operator-state"
        (self.state / "curiosity").mkdir(parents=True)
        # Valid empty JSONL file: actual producer validates and snapshots it.
        (self.state / "curiosity" / "artifacts.jsonl").write_bytes(b"")
        self.producer = self.root / "producer-backup"
        backup(self.state, self.producer)
        self.output = self.root / "portable.zip"

    def test_verified_producer_bundle_and_private_inert_restore(self) -> None:
        receipt = bundle(self.producer, self.output)
        self.assertEqual(receipt["status"], "PARTIAL")
        self.assertFalse(receipt["exitVerified"])
        self.assertFalse(receipt["authorityGranted"])
        self.assertFalse(receipt["captureCompletenessVerified"])
        with zipfile.ZipFile(self.output) as archive:
            self.assertIn("data/phi-state/manifest.json", archive.namelist())
        self.assertEqual(verify_bundle(self.output)["contentFiles"], 1)
        restored = self.root / "extracted"
        result = restore_snapshot(self.output, restored)
        self.assertTrue(result["snapshotExtracted"])
        self.assertFalse(result["activeStateRestored"])
        self.assertEqual(
            json.loads((restored / "manifest.json").read_text())["schema_version"],
            "phios.data-backup.v1",
        )
        if os.name == "posix":
            self.assertEqual(restored.stat().st_mode & 0o077, 0)
            self.assertEqual((restored / "manifest.json").stat().st_mode & 0o077, 0)
        with self.assertRaises(ValueError):
            restore_snapshot(self.output, restored)

    def test_no_automatic_discovery_and_no_secrets_or_unknown_file_in_archive(self) -> None:
        self.assertFalse(inventory()["automaticDiscovery"])
        self.assertIn("GitPorch", " ".join(inventory()["omissions"]))
        (self.producer / "api-token.txt").write_text("NOT-FOR-EXPORT")
        bundle(self.producer, self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertNotIn("data/phi-state/api-token.txt", archive.namelist())
        with self.assertRaises(ValueError):
            bundle(self.producer, self.output)

    def test_rejects_duplicate_zip_and_tampered_embedded_manifest(self) -> None:
        bundle(self.producer, self.output)
        with zipfile.ZipFile(self.output, "a") as archive:
            archive.writestr("data/phi-state/manifest.json", "{}")
        with self.assertRaises(ValueError):
            verify_bundle(self.output)
        # Build an internally valid outer ZIP with an invalid nested authority flag.
        source = self.root / "forged-source"
        target = source / "phi-state"
        target.mkdir(parents=True)
        manifest = json.loads((self.producer / "manifest.json").read_text())
        manifest["authority_restored"] = True
        (target / "manifest.json").write_text(json.dumps(manifest))
        for name in manifest["files"]:
            dst = target / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.producer / name, dst)
        forged_zip = self.root / "forged.zip"
        pack(source, forged_zip)
        with self.assertRaises(ValueError):
            verify_bundle(forged_zip)

    def test_rejects_missing_nested_state_and_preexisting_output(self) -> None:
        nested = self.root / "incomplete"
        (nested / "phi-state").mkdir(parents=True)
        shutil.copyfile(self.producer / "manifest.json", nested / "phi-state" / "manifest.json")
        incomplete = self.root / "missing.zip"
        pack(nested, incomplete)
        with self.assertRaises(ValueError):
            verify_bundle(incomplete)
        self.output.touch()
        with self.assertRaises(ValueError):
            bundle(self.producer, self.output)

    def test_independent_python_stdlib_verify_and_extract(self) -> None:
        bundle(self.producer, self.output)
        isolated = self.root / "standalone-tools"
        isolated.mkdir()
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        for name in ("sovereignty_exit_v01.py", "sovereignty_exit_r2.py"):
            shutil.copyfile(scripts / name, isolated / name)
        external = self.root / "independent-machine"
        external.mkdir()
        for arguments in (
            ["verify", "--bundle", str(self.output)],
            ["extract", "--bundle", str(self.output), "--output", str(external / "data")],
        ):
            result = subprocess.run(
                [sys.executable, "-S", str(isolated / "sovereignty_exit_r2.py"), *arguments],
                cwd=external, capture_output=True, text=True, timeout=15, check=False,
                env={**os.environ, "PYTHONPATH": ""},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["exitVerified"])
        self.assertTrue((external / "data" / "manifest.json").exists())

    def test_cli_refuses_export_without_explicit_approval(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "sovereignty_exit_r2.py"
        result = subprocess.run(
            [sys.executable, str(script), "bundle",
             "--verified-phi-state-backup", str(self.producer),
             "--output", str(self.output)],
            capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("approval", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
