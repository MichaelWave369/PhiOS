"""Scope-limited portability regression tests, not a PhiOS-wide exit attestation."""
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sovereignty_exit_v01 import pack, unpack, verified_files  # noqa: E402


class ExitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / "user"
        self.src.mkdir()
        (self.src / "notes").mkdir()
        (self.src / "notes" / "journal.txt").write_text("owned by the user", encoding="utf8")
        self.bundle = self.root / "portable.zip"

    def test_offline_roundtrip_and_independently_readable_zip(self):
        pack(self.src, self.bundle)
        with zipfile.ZipFile(self.bundle) as z:
            self.assertEqual(z.read("data/notes/journal.txt"), b"owned by the user")
        self.assertEqual(len(verified_files(self.bundle)), 1)
        dest = self.root / "restored"
        unpack(self.bundle, dest)
        self.assertEqual((dest / "notes" / "journal.txt").read_text(), "owned by the user")

    def test_refuses_unsafe_output_and_overwrite(self):
        with self.assertRaises(ValueError):
            pack(self.src, self.src / "self.zip")
        pack(self.src, self.bundle)
        with self.assertRaises(ValueError):
            pack(self.src, self.bundle)
        dest = self.root / "exists"
        dest.mkdir()
        with self.assertRaises(ValueError):
            unpack(self.bundle, dest)

    def test_rejects_modified_archive_contents(self):
        pack(self.src, self.bundle)
        with zipfile.ZipFile(self.bundle, "a") as z:
            z.writestr("data/notes/journal.txt", "tampered")
        with self.assertRaises(ValueError):
            verified_files(self.bundle)

    def test_rejects_traversal_members(self):
        pack(self.src, self.bundle)
        with zipfile.ZipFile(self.bundle, "a") as z:
            z.writestr("data/../outside", "not allowed")
        with self.assertRaises(ValueError):
            unpack(self.bundle, self.root / "should-not-exist")
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_symlink_exclusion(self):
        link = self.src / "alias"
        try:
            link.symlink_to(self.src / "notes", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            pack(self.src, self.bundle)


if __name__ == "__main__":
    unittest.main()
