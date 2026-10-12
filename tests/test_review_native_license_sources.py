import copy
import hashlib
import json
import unittest
from pathlib import Path

from scripts.review_native_license_sources import (
    EXPECTED, LOCK, build_report, git_blob_sha, validate_census,
    validate_lock, verify_source
)
from scripts.verify_frontend_locks import APPROVED


def fake_censuses(lock):
    output = []
    for app in ("vessie-web", "thinktank-web"):
        rows = [row for row in lock["entries"] if row["app"] == app]
        components = [{
            "path": "node_modules/" + r["package"],
            "name": r["package"], "version": r["version"],
            "license_declaration": "MIT",
            "requires_human_review": True,
            "license_or_notice_files": [],
        } for r in rows]
        output.append({
            "schema": "phios.frontend_license_evidence.v0.1",
            "status": "INVENTORY_COMPLETE", "app": app,
            "source_sha": APPROVED[app]["git"],
            "npm_lock_sha256": APPROVED[app]["lock_sha256"],
            "license_redistribution_cleared": False,
            "external_done": False, "components": components,
            "installed_count": len(components),
            "human_review_queue": [
                {"path": c["path"], "reasons": ["no-root-legal-file-found"]}
                for c in components
            ], "flagged_count": len(components),
        })
    return output


class NativeSourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(LOCK.read_text(encoding="utf-8"))

    def test_expected_four_source_locks_and_authority(self):
        entries = validate_lock(self.manifest)
        self.assertEqual({(r["app"],r["package"],r["version"]) for r in entries},
                         EXPECTED)
        self.assertEqual(
            sum(r["evidence_class"].startswith("DECLARATION_ONLY") for r in entries), 1)
        self.assertFalse(self.manifest["redistribution_approved"])

    def test_duplicate_or_foreign_package_cannot_claim_review(self):
        bad = copy.deepcopy(self.manifest)
        bad["entries"][0] = copy.deepcopy(bad["entries"][1])
        with self.assertRaisesRegex(ValueError,"MISSING_OR_DUPLICATE_FLAG"):
            validate_lock(bad)
        bad = copy.deepcopy(self.manifest)
        bad["entries"][0]["package"]="@unknown/native"
        with self.assertRaisesRegex(ValueError,"UNREVIEWED_NATIVE_PACKAGE"):
            validate_lock(bad)

    def test_forged_clearance_denied(self):
        bad = copy.deepcopy(self.manifest)
        bad["redistribution_approved"]=True
        with self.assertRaisesRegex(ValueError,"FORGED_AUTHORITY"):
            validate_lock(bad)

    def test_exact_census_review_queue_mandatory(self):
        censuses = fake_censuses(self.manifest)
        validate_census(censuses, validate_lock(self.manifest))
        censuses[0]["human_review_queue"].pop()
        censuses[0]["flagged_count"]-=1
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_LICENSE_REVIEW_QUEUE"):
            validate_census(censuses, validate_lock(self.manifest))

    def test_no_legal_rights_granted_by_source_evidence(self):
        static_data = b"MIT License\n\nSynthetic license fixture, not third-party text."
        parent = json.dumps({"name":"@napi-rs/lzma","version":"1.5.1",
                             "license":"MIT"}).encode()
        manifest = copy.deepcopy(self.manifest)
        by_key={}
        for row in manifest["entries"]:
            data = parent if "DECLARATION_ONLY" in row["evidence_class"] else static_data
            row["source_bytes"]=len(data)
            row["source_git_blob_sha"]=git_blob_sha(data)
            by_key[row["package"]]=data
        report=build_report(
            manifest,fake_censuses(manifest),
            fetcher=lambda r: by_key[r["package"]])
        self.assertEqual(report["status"],"SOURCE_EVIDENCE_LOCKED")
        self.assertEqual(report["upstream_sources_checked"],4)
        self.assertEqual(report["declaration_only_source_count"],1)
        for key in ("redistribution_approved","external_done",
                    "phios_install_authorized","phios_launch_authorized",
                    "native_binary_provenance_verified"):
            self.assertIs(report[key], False)
        self.assertEqual(len(report["source_evidence_sha256"]),64)

    def test_mutated_source_bytes_fail_closed(self):
        row=self.manifest["entries"][0]
        with self.assertRaisesRegex(ValueError,"SOURCE_BYTES_DRIFT"):
            verify_source(row,b"MIT License\nnot the pinned bytes")

    def test_source_has_been_bound_to_immutable_git_blob_format(self):
        value=b"MIT License\nsynthetic source"
        self.assertEqual(git_blob_sha(value),
            hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest())


if __name__=="__main__":
    unittest.main()
