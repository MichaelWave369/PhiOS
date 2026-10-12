import copy
import unittest

from scripts.verify_frontend_locks import APPROVED
from scripts.review_native_license_sources import LOCK
from scripts.frontend_release_preflight import (
    APPS, FILES, SCHEMA, canonical_digest, create_packet, load_receipts,
)
import json
import tempfile
from pathlib import Path


class FrontendReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads(LOCK.read_text(encoding="utf-8"))
        self.receipts=self.fixture()

    def fixture(self):
        data={}
        for app in APPS:
            cfg=APPROVED[app]
            data[app+"-closure"]={
                "schema":"phios.trellis_npm_closure.v0.1",
                "app":app,"source_sha":cfg["git"],
                "manifest_sha256":cfg["package_json_sha256"],
                "lock_sha256":cfg["lock_sha256"],
                "npm_install_command":"npm ci --ignore-scripts",
                "dependency_package_count":71,
                "source_modified":True,
                "phios_installed":False,"license_audit_complete":False,
                "external_done":False,
            }
            rows=[e for e in self.lock["entries"] if e["app"]==app]
            components=[{
                "path":"node_modules/"+e["package"],
                "name":e["package"],"version":e["version"],
                "license_declaration":"MIT",
                "requires_human_review":True,
                "license_or_notice_files":[],
            } for e in rows]
            data[app+"-census"]={
                "schema":"phios.frontend_license_evidence.v0.1",
                "status":"INVENTORY_COMPLETE","app":app,
                "source_sha":cfg["git"],
                "package_json_sha256":cfg["package_json_sha256"],
                "npm_lock_sha256":cfg["lock_sha256"],
                "all_installed_packages_accounted_for":True,
                "license_metadata_verified_against_installed_packages":True,
                "license_conclusions_human_reviewed":False,
                "license_redistribution_cleared":False,
                "release_or_installer_authorized":False,
                "external_done":False,
                "components":components,
                "installed_count":len(components),
                "flagged_count":len(components),
                "human_review_queue":[
                    {"path":c["path"],"reasons":["no-root-legal-file-found"]}
                    for c in components
                ],
                "component_manifest_sha256":canonical_digest(components),
            }
            assets={"index.html":"a"*64,"assets/index.js":"b"*64}
            data[app+"-replay"]={
                "schema":"phios.trellis_two_clean_builds.v0.1",
                "status":"PASS","app":app,"source_sha":cfg["git"],
                "npm_lock_sha256":cfg["lock_sha256"],
                "same_runner_two_independent_source_trees":True,
                "multi_machine_reproducibility_verified":False,
                "license_clearance_verified":False,
                "phios_installed":False,"phios_launch_authorized":False,
                "external_done":False,
                "file_sha256":assets,"output_file_count":len(assets),
                "output_manifest_sha256":canonical_digest(assets),
            }
        proofs=[{
            "app":e["app"],"package":e["package"],"version":e["version"],
            "upstream_repo":e["upstream_repo"],
            "upstream_commit":e["upstream_commit"],
            "source_path":e["source_path"],
            "source_git_blob_sha":e["source_git_blob_sha"],
            "source_sha256":"a"*64,
            "evidence_class":e["evidence_class"],
            "human_review_required":True,
            "release_or_redistribution_cleared":False,
            "upstream_parent_child_binary_provenance_verified":False
        } for e in self.lock["entries"]]
        data["native-source"]={
            "schema":"phios.native_license_sources_verified.v0.1",
            "status":"SOURCE_EVIDENCE_LOCKED",
            "upstream_sources_checked":4,
            "upstream_license_files_checked":3,
            "declaration_only_source_count":1,
            "four_native_packages_reviewed_for_evidence":True,
            "full_legal_obligations_reviewed":False,
            "transitive_cargo_license_reviewed":False,
            "native_binary_provenance_verified":False,
            "redistribution_approved":False,
            "phios_install_authorized":False,
            "phios_launch_authorized":False,
            "external_done":False,
            "proofs":proofs,"source_evidence_sha256":canonical_digest(proofs),
        }
        return data

    def test_evidence_complete_but_release_held(self):
        packet=create_packet(self.receipts,self.lock)
        self.assertEqual(packet["schema"],SCHEMA)
        self.assertEqual(packet["status"],"HOLD_FOR_OPERATOR_REVIEW")
        self.assertEqual(packet["release_blocker_count"],7)
        self.assertEqual(len(packet["receipts_sha256"]),7)
        self.assertEqual(len(packet["reviewed_apps"]),2)
        for field in ("release_authority_present","license_redistribution_cleared",
                      "installer_packaging_authorized","external_done",
                      "phios_launch_authorized","provider_or_model_authorized"):
            self.assertIs(packet[field],False)

    def test_forged_redistribution_grant_rejected(self):
        r=copy.deepcopy(self.receipts)
        r["native-source"]["redistribution_approved"]=True
        with self.assertRaisesRegex(ValueError,"SOURCE_REPORT_IDENTITY_OR_AUTHORITY_DRIFT"):
            create_packet(r,self.lock)

    def test_forged_installer_status_rejected(self):
        r=copy.deepcopy(self.receipts)
        r["vessie-web-census"]["release_or_installer_authorized"]=True
        with self.assertRaisesRegex(ValueError,"CENSUS_IDENTITY_OR_AUTHORITY_DRIFT"):
            create_packet(r,self.lock)

    def test_changed_replay_byte_hash_without_manifest_fails(self):
        r=copy.deepcopy(self.receipts)
        r["thinktank-web-replay"]["file_sha256"]["assets/index.js"]="f"*64
        with self.assertRaisesRegex(ValueError,"REPLAY_OUTPUT_MANIFEST_DRIFT"):
            create_packet(r,self.lock)

    def test_changed_component_manifest_fails(self):
        r=copy.deepcopy(self.receipts)
        r["vessie-web-census"]["components"][0]["version"]="9999"
        with self.assertRaisesRegex(ValueError,"CENSUS_COMPONENT_DIGEST_DRIFT"):
            create_packet(r,self.lock)

    def test_missing_review_flag_rejected(self):
        r=copy.deepcopy(self.receipts)
        r["vessie-web-census"]["human_review_queue"].pop()
        r["vessie-web-census"]["flagged_count"]-=1
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_LICENSE_REVIEW_QUEUE"):
            create_packet(r,self.lock)

    def test_missing_receipt_rejected(self):
        r=copy.deepcopy(self.receipts)
        del r["vessie-web-closure"]
        with self.assertRaisesRegex(ValueError,"MISSING_RECEIPT"):
            create_packet(r,self.lock)

    def test_wrong_source_sha_rejected(self):
        r=copy.deepcopy(self.receipts)
        r["thinktank-web-closure"]["source_sha"]="0"*40
        with self.assertRaisesRegex(ValueError,"DEPENDENCY_CLOSURE_DRIFT"):
            create_packet(r,self.lock)

    def test_source_blob_sha_drift_rejected_even_with_matching_digest(self):
        r=copy.deepcopy(self.receipts)
        r["native-source"]["proofs"][0]["source_git_blob_sha"]="0"*40
        r["native-source"]["source_evidence_sha256"]=canonical_digest(
            r["native-source"]["proofs"])
        with self.assertRaisesRegex(ValueError,"SOURCE_PROOF_PIN_DRIFT"):
            create_packet(r,self.lock)

    def test_missing_symlinked_receipts_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,"RECEIPT_FILE_MISSING_OR_LINKED"):
                load_receipts(root)
            outside=root/"payload.json"
            outside.write_text("{}")
            (root/FILES["vessie-web-closure"]).symlink_to(outside)
            with self.assertRaisesRegex(ValueError,"RECEIPT_FILE_MISSING_OR_LINKED"):
                load_receipts(root)

if __name__=="__main__":
    unittest.main()
