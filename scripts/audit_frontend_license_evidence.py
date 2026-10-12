#!/usr/bin/env python3
"""PhiOS v0.67 read-only npm package/LICENSE/NOTICE evidence census.

A package declaring "MIT" is NOT a redistribution approval. Never copy license
contents, never grant app installation, and never silently suppress missing data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_frontend_locks import APPROVED, inspect

SCHEMA = "phios.frontend_license_evidence.v0.1"
PACKAGE_RE = re.compile(r"^(?:node_modules/)(?:(?:@[^/]+/)?[^/]+/node_modules/)*(?:@[^/]+/)?[^/]+$")
LEGAL_FILE_RE = re.compile(r"^(?:LICEN[CS]E(?:[.-].*)?|COPYING(?:[.-].*)?|NOTICE(?:[.-].*)?|UNLICENSE(?:[.-].*)?|PATENTS(?:[.-].*)?)$", re.I)

def demand(ok: bool,code: str) -> None:
    if not ok:
        raise ValueError("PHIOS_LICENSE_CENSUS_"+code)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def safe_manifest(file: Path) -> dict:
    demand(file.is_file() and not file.is_symlink(),"MISSING_OR_LINKED_PACKAGE_MANIFEST")
    data=file.read_bytes()
    demand(len(data)<=1024*1024,"PACKAGE_MANIFEST_OVERSIZE")
    value=json.loads(data)
    demand(isinstance(value,dict),"PACKAGE_MANIFEST_INVALID")
    return value

def installed_paths(source: Path) -> set[str]:
    root=source / "node_modules"
    demand(root.is_dir() and not root.is_symlink(),"NODE_MODULES_MISSING")
    found: set[str] = set()
    def walk(modules: Path) -> None:
        demand(modules.is_dir() and not modules.is_symlink(),"LINKED_MODULES")
        for entry in sorted(modules.iterdir()):
            if entry.name==".package-lock.json":
                demand(entry.is_file() and not entry.is_symlink(),"HIDDEN_LOCK_INVALID")
                continue
            if entry.name==".bin":
                demand(entry.is_dir() and not entry.is_symlink(),"BIN_DIR_INVALID")
                # npm creates executable symlinks in .bin. Those are deliberately
                # not package identities and not a distribution-license claim.
                continue
            demand(not entry.name.startswith("."),
                   "UNEXPECTED_HIDDEN_ENTRY:"+entry.relative_to(source).as_posix())
            if entry.name.startswith("@"):
                demand(entry.is_dir() and not entry.is_symlink(),"SCOPE_DIRECTORY_INVALID")
                for package in sorted(entry.iterdir()):
                    add(package)
            else:
                add(entry)
    def add(package: Path) -> None:
        demand(package.is_dir() and not package.is_symlink(),"PACKAGE_DIRECTORY_INVALID")
        relative=package.relative_to(source).as_posix()
        demand(PACKAGE_RE.fullmatch(relative) is not None,"PACKAGE_PATH_INVALID")
        demand(relative not in found,"DUPLICATE_PACKAGE")
        found.add(relative)
        nested=package/"node_modules"
        if nested.exists() or nested.is_symlink():
            walk(nested)
    walk(root)
    demand(len(found)>0,"EMPTY_INSTALLED_SET")
    return found

def canonical_package_name(path: str) -> str:
    demand(PACKAGE_RE.fullmatch(path) is not None,"PACKAGE_PATH_INVALID")
    components=path.split("/")
    return "/".join(components[-2:]) if components[-2].startswith("@") else components[-1]

def license_metadata(value: Any) -> tuple[str,str]:
    # Preserve the source's exact declared string for review; do not parse it
    # as permission. Non-SPDX legacy forms are explicitly unresolved.
    if isinstance(value,str) and value.strip():
        return value.strip(),("declared" if value.strip().upper() not in
            {"UNLICENSED","UNKNOWN","NONE","SEE LICENSE IN LICENSE","SEE LICENSE IN LICENSE.MD"}
            else "review-needed")
    if value is None:
        return "", "missing"
    return json.dumps(value,sort_keys=True), "nonstandard-review-needed"

def legal_evidence(package: Path) -> list[dict]:
    evidence=[]
    for file in sorted(package.iterdir()):
        if not LEGAL_FILE_RE.fullmatch(file.name):
            continue
        demand(file.is_file() and not file.is_symlink(),"LINKED_OR_INVALID_LICENSE_FILE")
        data=file.read_bytes()
        demand(len(data)<=5*1024*1024,"LICENSE_FILE_OVERSIZE")
        evidence.append({"name":file.name,"sha256":sha(data),"bytes":len(data)})
    return evidence

def census(source: Path, lock: dict) -> dict[str,Any]:
    source=source.absolute()
    locked=lock.get("packages")
    demand(isinstance(locked,dict),"LOCK_PACKAGES_MISSING")
    keys=set(locked)-{""}
    for key in keys:
        demand(PACKAGE_RE.fullmatch(key) is not None,"LOCK_PATH_INVALID")
    installed=installed_paths(source)
    demand(installed<=keys,"EXTRANEOUS_INSTALLED_PACKAGE")
    mandatory={k for k,v in locked.items() if k and v.get("optional") is not True}
    demand(mandatory<=installed,"MANDATORY_LOCKED_PACKAGE_MISSING")
    report=[]
    flagged=[]
    for path in sorted(installed):
        details=locked[path]
        pkgdir=source/path
        package=safe_manifest(pkgdir/"package.json")
        name=canonical_package_name(path)
        demand(package.get("name")==name and
               package.get("version")==details.get("version"),
               "PACKAGE_NAME_OR_VERSION_DRIFT")
        raw,status=license_metadata(package.get("license"))
        legal=legal_evidence(pkgdir)
        reasons=[]
        if status!="declared":reasons.append("license-metadata-"+status)
        if not legal:reasons.append("no-root-legal-file-found")
        if reasons:
            flagged.append({"path":path,"reasons":reasons})
        report.append({
            "path":path,"name":name,"version":package["version"],
            "lock_integrity":details.get("integrity"),
            "license_declaration":raw,"license_declaration_status":status,
            "license_or_notice_files":legal,"requires_human_review":bool(reasons),
            "optional_package":details.get("optional") is True,
            "dev_package":details.get("dev") is True
        })
    uninstalled=sorted(keys-installed)
    demand(all(locked[k].get("optional") is True for k in uninstalled),
           "UNEXPLAINED_MISSING_INSTALLED_PACKAGE")
    source_digest=sha(json.dumps(report,sort_keys=True,separators=(",",":")).encode())
    return {"components":report,"installed_count":len(report),
            "optional_not_installed":uninstalled,
            "human_review_queue":flagged,
            "flagged_count":len(flagged),
            "component_manifest_sha256":source_digest,
            "all_installed_packages_accounted_for":True}

def make_report(app: str, checkout: Path) -> dict[str,Any]:
    identity,source,lock_bytes=inspect(app,checkout)
    installed_lock=source/"package-lock.json"
    demand(installed_lock.is_file() and not installed_lock.is_symlink() and
           installed_lock.read_bytes()==lock_bytes,
           "INSTALLED_LOCK_DRIFT")
    result=census(source,json.loads(lock_bytes))
    return {
        "schema":SCHEMA,"app":app,"status":"INVENTORY_COMPLETE",
        "source_sha":identity["source_sha"],
        "package_json_sha256":identity["manifest_sha256"],
        "npm_lock_sha256":identity["lock_sha256"],
        "environment":"Node 24.21.0 + npm 11.19.0 / ubuntu-latest",
        **result,
        "scope":"npm packages installed in this CI runner node_modules tree",
        "license_metadata_verified_against_installed_packages":True,
        "license_conclusions_human_reviewed":False,
        "license_redistribution_cleared":False,
        "vulnerability_audit_completed":False,
        "release_or_installer_authorized":False,
        "provider_operations_authorized":False,
        "external_done":False
    }

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--app",choices=sorted(APPROVED),required=True)
    parser.add_argument("--checkout",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    result=make_report(args.app,args.checkout)
    target=args.report.absolute()
    demand(not target.exists() and not target.is_symlink(),"RECEIPT_EXISTS")
    with target.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,sort_keys=True)
        f.write("\n")
    print(json.dumps({
        "schema":SCHEMA,"app":args.app,"status":result["status"],
        "installed":result["installed_count"],
        "optional_not_installed":len(result["optional_not_installed"]),
        "human_review_flags":result["flagged_count"],
        "component_manifest_sha256":result["component_manifest_sha256"],
        "license_redistribution_cleared":False,"external_done":False
    },sort_keys=True))

if __name__=="__main__":
    main()
