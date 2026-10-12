#!/usr/bin/env python3
"""PhiOS v0.69: compose immutable, evidence-only frontend promotion preflight.

The successful outcome is HOLD_FOR_OPERATOR_REVIEW, never permission to ship.
All receipts must come from the same CI execution and match reviewed sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts.verify_frontend_locks import APPROVED
from scripts.review_native_license_sources import (
    LOCK, EXPECTED, validate_lock, validate_census
)

SCHEMA="phios.frontend_release_preflight.v0.1"
APPS=("vessie-web","thinktank-web")
HEX64=re.compile(r"[0-9a-f]{64}\Z")

# These are human review/engineering blockers, NOT automatic tasks that CI can
# approve using unverified booleans or a manually authored YAML override.
HOLDS=(
  ("native.lzma_standalone_document",
   "LZMA native package has declaration-only parent source; no tagged root license document"),
  ("notices.rollup_composite",
   "Rollup combined legal notices and third-party attributions have not been reconciled"),
  ("binary.source_provenance",
   "Native npm binary tarballs have not been traced to reviewed source/build provenance"),
  ("license.transitive_platforms",
   "Transitive Rust obligations and other platform-optional packages have not been reviewed"),
  ("distribution.notice_bundle",
   "Approved license and attribution notice bundle is not assembled"),
  ("security.vulnerabilities",
   "Complete pinned dependency vulnerability review has not been performed"),
  ("approval.operator_release",
   "No separate founder/operator-approved distribution and installer authorization exists"),
)

def require(ok:bool,code:str)->None:
    if not ok:
        raise ValueError("PHIOS_RELEASE_PREFLIGHT_"+code)

def canonical_digest(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,
       separators=(",",":"),ensure_ascii=True).encode("utf-8")).hexdigest()

def valid_hash(value:Any)->bool:
    return isinstance(value,str) and HEX64.fullmatch(value) is not None

def review_lock()->dict:
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    validate_lock(lock)
    return lock

def validate_closure(app:str,value:dict)->None:
    cfg=APPROVED[app]
    require(value.get("schema")=="phios.trellis_npm_closure.v0.1" and
            value.get("app")==app and
            value.get("source_sha")==cfg["git"] and
            value.get("manifest_sha256")==cfg["package_json_sha256"] and
            value.get("lock_sha256")==cfg["lock_sha256"] and
            value.get("npm_install_command")=="npm ci --ignore-scripts" and
            value.get("source_modified") is True and
            value.get("phios_installed") is False and
            value.get("license_audit_complete") is False and
            value.get("external_done") is False,
            "DEPENDENCY_CLOSURE_DRIFT_"+app)
    require(isinstance(value.get("dependency_package_count"),int) and
            value["dependency_package_count"]>=20,"DEPENDENCY_COUNT_"+app)

def validate_census_receipt(app:str,value:dict)->None:
    cfg=APPROVED[app]
    require(value.get("schema")=="phios.frontend_license_evidence.v0.1" and
            value.get("app")==app and
            value.get("status")=="INVENTORY_COMPLETE" and
            value.get("source_sha")==cfg["git"] and
            value.get("package_json_sha256")==cfg["package_json_sha256"] and
            value.get("npm_lock_sha256")==cfg["lock_sha256"] and
            value.get("all_installed_packages_accounted_for") is True and
            value.get("license_metadata_verified_against_installed_packages") is True and
            value.get("license_conclusions_human_reviewed") is False and
            value.get("license_redistribution_cleared") is False and
            value.get("release_or_installer_authorized") is False and
            value.get("external_done") is False,
            "CENSUS_IDENTITY_OR_AUTHORITY_DRIFT_"+app)
    components=value.get("components")
    require(isinstance(components,list) and len(components)==value.get("installed_count") and
            value.get("component_manifest_sha256")==canonical_digest(components),
            "CENSUS_COMPONENT_DIGEST_DRIFT_"+app)
    indexed={c.get("path"):c for c in components}
    require(len(indexed)==len(components),"CENSUS_DUPLICATE_COMPONENT_"+app)
    queue=value.get("human_review_queue")
    require(isinstance(queue,list) and
            len(queue)==value.get("flagged_count"),"CENSUS_REVIEW_QUEUE_"+app)

def validate_replay(app:str,value:dict)->None:
    cfg=APPROVED[app]
    require(value.get("schema")=="phios.trellis_two_clean_builds.v0.1" and
            value.get("status")=="PASS" and value.get("app")==app and
            value.get("source_sha")==cfg["git"] and
            value.get("npm_lock_sha256")==cfg["lock_sha256"] and
            value.get("same_runner_two_independent_source_trees") is True and
            value.get("multi_machine_reproducibility_verified") is False and
            value.get("license_clearance_verified") is False and
            value.get("phios_installed") is False and
            value.get("phios_launch_authorized") is False and
            value.get("external_done") is False,
            "REPLAY_IDENTITY_OR_AUTHORITY_DRIFT_"+app)
    file_hashes=value.get("file_sha256")
    require(isinstance(file_hashes,dict) and
            len(file_hashes)==value.get("output_file_count") and
            "index.html" in file_hashes and
            any(k.startswith("assets/") and k.endswith(".js") for k in file_hashes) and
            all(isinstance(k,str) and valid_hash(v) for k,v in file_hashes.items()) and
            canonical_digest(file_hashes)==value.get("output_manifest_sha256"),
            "REPLAY_OUTPUT_MANIFEST_DRIFT_"+app)

def validate_source_proofs(report:dict,lock:dict)->None:
    require(report.get("schema")=="phios.native_license_sources_verified.v0.1" and
            report.get("status")=="SOURCE_EVIDENCE_LOCKED" and
            report.get("upstream_sources_checked")==4 and
            report.get("upstream_license_files_checked")==3 and
            report.get("declaration_only_source_count")==1 and
            report.get("four_native_packages_reviewed_for_evidence") is True and
            report.get("full_legal_obligations_reviewed") is False and
            report.get("transitive_cargo_license_reviewed") is False and
            report.get("native_binary_provenance_verified") is False and
            report.get("redistribution_approved") is False and
            report.get("phios_install_authorized") is False and
            report.get("phios_launch_authorized") is False and
            report.get("external_done") is False,
            "SOURCE_REPORT_IDENTITY_OR_AUTHORITY_DRIFT")
    proofs=report.get("proofs")
    require(isinstance(proofs,list) and len(proofs)==4 and
            canonical_digest(proofs)==report.get("source_evidence_sha256"),
            "SOURCE_REPORT_DIGEST_DRIFT")
    pins={(r["app"],r["package"],r["version"]):r for r in lock["entries"]}
    seen=set()
    for p in proofs:
        key=(p.get("app"),p.get("package"),p.get("version"))
        require(key in EXPECTED and key not in seen, "SOURCE_PROOF_UNREVIEWED")
        seen.add(key)
        pinned=pins[key]
        require(p.get("upstream_repo")==pinned["upstream_repo"] and
                p.get("upstream_commit")==pinned["upstream_commit"] and
                p.get("source_path")==pinned["source_path"] and
                p.get("source_git_blob_sha")==pinned["source_git_blob_sha"] and
                p.get("evidence_class")==pinned["evidence_class"] and
                valid_hash(p.get("source_sha256")) and
                p.get("human_review_required") is True and
                p.get("release_or_redistribution_cleared") is False and
                p.get("upstream_parent_child_binary_provenance_verified") is False,
                "SOURCE_PROOF_PIN_DRIFT")
    require(seen==EXPECTED,"SOURCE_PROOF_MISSING")

def create_packet(receipts:dict[str,dict],source_lock:dict|None=None)->dict:
    lock=review_lock() if source_lock is None else source_lock
    validate_lock(lock)
    for app in APPS:
        for key in ("closure","census","replay"):
            require(app+"-"+key in receipts,"MISSING_RECEIPT_"+app+"_"+key)
        validate_closure(app,receipts[app+"-closure"])
        validate_census_receipt(app,receipts[app+"-census"])
        validate_replay(app,receipts[app+"-replay"])
    proof=receipts.get("native-source")
    require(isinstance(proof,dict),"MISSING_NATIVE_SOURCE_RECEIPT")
    validate_census([receipts[a+"-census"] for a in APPS],lock["entries"])
    validate_source_proofs(proof,lock)
    fingerprints={key:canonical_digest(receipts[key]) for key in sorted(receipts)}
    apps=[{
        "app":app, "source_sha":APPROVED[app]["git"],
        "npm_lock_sha256":APPROVED[app]["lock_sha256"],
        "installed_packages":receipts[app+"-census"]["installed_count"],
        "review_flags":receipts[app+"-census"]["flagged_count"],
        "same_runner_byte_replay_pass":True,
        "redistribution_approved":False,
    } for app in APPS]
    return {
      "schema":SCHEMA,
      "status":"HOLD_FOR_OPERATOR_REVIEW",
      "review_packet_only":True,
      "evidence_consistency_verified":True,
      "receipts_sha256":fingerprints,
      "receipts_manifest_sha256":canonical_digest(fingerprints),
      "reviewed_apps":apps,
      "blocking_obligations":[{"id":key,"reason":reason,"state":"UNRESOLVED"}
                              for key,reason in HOLDS],
      "release_blocker_count":len(HOLDS),
      "missing_standalone_license_document":"@napi-rs/lzma-linux-x64-gnu@1.5.1",
      "release_authority_present":False,
      "license_redistribution_cleared":False,
      "installer_packaging_authorized":False,
      "phios_installed":False,
      "phios_launch_authorized":False,
      "provider_or_model_authorized":False,
      "external_done":False
    }

FILES={
  "vessie-web-closure":"vessie-verified-lock.json",
  "thinktank-web-closure":"thinktank-verified-lock.json",
  "vessie-web-census":"vessie-license-evidence.json",
  "thinktank-web-census":"thinktank-license-evidence.json",
  "vessie-web-replay":"vessie-double-build.json",
  "thinktank-web-replay":"thinktank-double-build.json",
  "native-source":"native-license-source-review.json",
}

def load_receipts(directory:Path)->dict[str,dict]:
    require(directory.is_dir() and not directory.is_symlink(),
            "RECEIPT_DIRECTORY_INVALID")
    results={}
    for key,filename in FILES.items():
        path=directory/filename
        require(path.is_file() and not path.is_symlink(),
                "RECEIPT_FILE_MISSING_OR_LINKED_"+key)
        require(path.stat().st_size<2_000_000, "RECEIPT_OVERSIZED_"+key)
        content=json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(content,dict),"RECEIPT_INVALID_"+key)
        results[key]=content
    return results

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--receipts-dir",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--require-release-authority",action="store_true",
                   help="Negative control: should always refuse this CI-only evidence.")
    args=p.parse_args()
    packet=create_packet(load_receipts(args.receipts_dir))
    require(not args.report.exists() and not args.report.is_symlink(),
            "REPORT_ALREADY_EXISTS")
    with args.report.open("x",encoding="utf-8") as fp:
        json.dump(packet,fp,indent=2,sort_keys=True)
        fp.write("\n")
    print(json.dumps({"schema":SCHEMA,"status":packet["status"],
        "blockers":packet["release_blocker_count"],"authority":False,
        "receipts_manifest_sha256":packet["receipts_manifest_sha256"]},
        sort_keys=True))
    if args.require_release_authority:
        raise SystemExit("PHIOS_RELEASE_PREFLIGHT_RELEASE_DENIED")

if __name__=="__main__":
    main()
