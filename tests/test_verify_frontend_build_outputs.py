import tempfile
import unittest
from pathlib import Path

from scripts.verify_frontend_build_outputs import compare

class ReplayOutputContracts(unittest.TestCase):
    def build(self, root):
        root.mkdir(parents=True)
        (root / "assets").mkdir()
        (root / "index.html").write_bytes(b'<html><script src="./assets/index.js"></script></html>')
        (root / "assets" / "index.js").write_bytes(b"console.log('ok')")

    def test_identical_independent_trees_pass(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            self.build(a)
            self.build(b)
            receipt = compare("vessie-web", a, b)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["output_file_count"], 2)
            self.assertFalse(receipt["multi_machine_reproducibility_verified"])
            self.assertFalse(receipt["external_done"])

    def test_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            self.build(a)
            self.build(b)
            (b / "assets" / "index.js").write_bytes(b"console.log('different')")
            with self.assertRaisesRegex(ValueError, "OUTPUT_BYTE_DRIFT"):
                compare("thinktank-web", a, b)

    def test_added_and_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            self.build(a)
            self.build(b)
            (b / "assets" / "unexpected.txt").write_text("extra")
            with self.assertRaisesRegex(ValueError, "OUTPUT_FILESET_DRIFT"):
                compare("vessie-web", a, b)
            (b / "assets" / "unexpected.txt").unlink()
            (b / "assets" / "index.js").unlink()
            with self.assertRaisesRegex(ValueError, "COMPILED_SCRIPT_MISSING"):
                compare("vessie-web", a, b)

    def test_symlinked_assets_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            self.build(a)
            self.build(b)
            (b / "assets" / "index.js").unlink()
            (b / "assets" / "index.js").symlink_to(a / "assets" / "index.js")
            with self.assertRaisesRegex(ValueError, "UNSAFE_OUTPUT_FILE"):
                compare("vessie-web", a, b)

    def test_same_and_nested_roots_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/"a"
            self.build(a)
            with self.assertRaisesRegex(ValueError, "SHARED_OUTPUT_DIRECTORY"):
                compare("vessie-web", a, a)
            with self.assertRaisesRegex(ValueError, "SHARED_OUTPUT_DIRECTORY"):
                compare("vessie-web", a, a/"assets")

    def test_unreviewed_app_denied(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "UNREVIEWED_APP"):
                compare("unreviewed", Path(d)/"x",Path(d)/"y")

if __name__ == "__main__":
    unittest.main()
