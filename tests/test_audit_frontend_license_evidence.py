import tempfile
import unittest
from pathlib import Path

from scripts.audit_frontend_license_evidence import (
    census, canonical_package_name, installed_paths, license_metadata, legal_evidence
)


class FrontendLicenseEvidenceTests(unittest.TestCase):
    def fixture(self, root: Path, *, licensed=True):
        node=root/"node_modules"/"@example"/"lib"
        node.mkdir(parents=True)
        manifest='{"name":"@example/lib","version":"1.2.3"'
        manifest+=',"license":"MIT"}' if licensed else '}'
        (node/"package.json").write_text(manifest,encoding="utf-8")
        if licensed:
            (node/"LICENSE-MIT").write_bytes(b"synthetic fixture; NOT a real license")
            (node/"NOTICE.txt").write_bytes(b"fixture notice")
        lock={"packages":{
            "":{"name":"fixture","version":"0.1.0"},
            "node_modules/@example/lib":{
                "version":"1.2.3","integrity":"sha512-"+"A"*60},
            "node_modules/@example/unused-linux":{
                "version":"1.2.3","integrity":"sha512-"+"B"*60,"optional":True}
        }}
        return node,lock

    def test_declared_license_and_hashed_legal_files_are_only_metadata(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t); node,lock=self.fixture(source)
            result=census(source,lock)
            self.assertEqual(result["installed_count"],1)
            self.assertEqual(result["flagged_count"],0)
            self.assertEqual(result["optional_not_installed"],
                             ["node_modules/@example/unused-linux"])
            files=result["components"][0]["license_or_notice_files"]
            self.assertEqual({x["name"] for x in files},{"LICENSE-MIT","NOTICE.txt"})
            self.assertTrue(all(len(x["sha256"])==64 for x in files))
            self.assertEqual(canonical_package_name("node_modules/@example/lib"),
                             "@example/lib")

    def test_unknown_license_does_not_get_fictional_clearance(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t);self.fixture(source,licensed=False)
            result=census(source,self.fixture_lock_without_rewrite())
            self.assertEqual(result["flagged_count"],1)
            self.assertIn("license-metadata-missing",
                          result["human_review_queue"][0]["reasons"])
            self.assertIn("no-root-legal-file-found",
                          result["human_review_queue"][0]["reasons"])

    def fixture_lock_without_rewrite(self):
        return {"packages":{
            "":{"name":"fixture","version":"0.1.0"},
            "node_modules/@example/lib":{"version":"1.2.3",
                 "integrity":"sha512-"+"A"*60}
        }}

    def test_unlocked_installed_package_is_denied(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t);self.fixture(source)
            with self.assertRaisesRegex(ValueError,"EXTRANEOUS_INSTALLED_PACKAGE"):
                census(source,{"packages":{"":{"name":"fixture"}}})

    def test_missing_mandatory_dependency_is_denied(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t);_,lock=self.fixture(source)
            lock["packages"]["node_modules/required-but-absent"]={
                "version":"1.0.0","integrity":"sha512-"+"A"*60}
            with self.assertRaisesRegex(ValueError,"MANDATORY_LOCKED_PACKAGE_MISSING"):
                census(source,lock)

    def test_package_version_drift_is_denied(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t);node,lock=self.fixture(source)
            (node/"package.json").write_text('{"name":"@example/lib","version":"9.9.9"}')
            with self.assertRaisesRegex(ValueError,"PACKAGE_NAME_OR_VERSION_DRIFT"):
                census(source,lock)

    def test_symlinked_legal_document_is_denied(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t);node,lock=self.fixture(source)
            (node/"LICENSE-MIT").unlink()
            (node/"LICENSE-MIT").symlink_to(node/"NOTICE.txt")
            with self.assertRaisesRegex(ValueError,"LINKED_OR_INVALID_LICENSE_FILE"):
                census(source,lock)

    def test_symlinked_package_is_denied(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t); node,lock=self.fixture(source)
            extra=source/"node_modules"/"fake"
            extra.symlink_to(node,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"PACKAGE_DIRECTORY_INVALID"):
                installed_paths(source)

    def test_legacy_declarations_need_review(self):
        self.assertEqual(license_metadata("MIT"),("MIT","declared"))
        self.assertEqual(license_metadata(None),("","missing"))
        self.assertEqual(license_metadata("UNLICENSED"),("UNLICENSED","review-needed"))
        self.assertEqual(license_metadata({"type":"MIT"})[1],
                         "nonstandard-review-needed")

if __name__=="__main__":
    unittest.main()
