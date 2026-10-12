#!/usr/bin/env python3
"""PhiOS v0.68: verify version-locked upstream legal evidence for four native package flags.
No legal clearance is inferred; no license source text is copied or shipped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
from pathlib import Path
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.verify_frontend_locks import APPROVED

LOCK = ROOT / "dependency-locks/native-license-source-evidence.v0.68.json"
SCHEMA = "phios.native_license_sources_verified.v0.1"
EXPECTED = {
    ("vessie-web", "@esbuild/linux-x64", "0.25.12"),
    ("vessie-web", "@napi-rs/lzma-linux-x64-gnu", "1.5.1"),
    ("vessie-web", "@rollup/rollup-linux-x64-gnu", "4.64.5"),
    ("thinktank-web", "@rolldown/binding-linux-x64-gnu", "1.2.13"),
}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
FILE = re.compile(r"[A-Za-z0-9_.-]+\Z")
CLASSES = {"IMMUTABLE_ROOT_LICENSE_FILE", "DECLARATION_ONLY_NO_ROOT_LICENSE_FILE_AT_TAG"}


def demand(ok: bool, key: str) -> None:
    if not ok:
        raise ValueError("PHIOS_NATIVE_LICENSE_" + key)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def validate_lock(document: dict) -> list[dict]:
    demand(isinstance(document, dict), "LOCK_NOT_OBJECT")
    demand(set(document) == {
        "schema", "review_scope", "entries", "redistribution_approved",
        "license_notice_obligations_reviewed", "native_binary_provenance_established",
        "external_done",
    }, "LOCK_FIELDS")
    demand(document["schema"] == "phios.native_license_source_lock.v0.1",
           "LOCK_SCHEMA")
    demand(all(document[k] is False for k in (
        "redistribution_approved", "license_notice_obligations_reviewed",
        "native_binary_provenance_established", "external_done")), "FORGED_AUTHORITY")
    entries = document["entries"]
    demand(isinstance(entries, list) and len(entries) == len(EXPECTED),
           "UNEXPECTED_ENTRY_COUNT")
    keys = []
    for row in entries:
        demand(isinstance(row, dict), "BAD_ENTRY")
        required = {"app", "package", "version", "upstream_repo", "upstream_commit",
                    "reviewed_tag", "source_path", "source_git_blob_sha",
                    "source_bytes", "evidence_class", "review_required"}
        demand(required <= set(row) and set(row) <= required | {"composite_notice_review"},
               "ENTRY_FIELDS")
        identity = (row["app"], row["package"], row["version"])
        demand(identity in EXPECTED, "UNREVIEWED_NATIVE_PACKAGE")
        keys.append(identity)
        demand(REPO.fullmatch(row["upstream_repo"]) is not None and
               HEX40.fullmatch(row["upstream_commit"]) is not None and
               HEX40.fullmatch(row["source_git_blob_sha"]) is not None,
               "INVALID_UPSTREAM_REVISION")
        demand(FILE.fullmatch(row["source_path"]) is not None and
               isinstance(row["source_bytes"], int) and
               0 < row["source_bytes"] < 100000 and
               row["evidence_class"] in CLASSES and
               row["review_required"] is True,
               "EVIDENCE_FIELDS")
        if row["evidence_class"] == "DECLARATION_ONLY_NO_ROOT_LICENSE_FILE_AT_TAG":
            demand(row["package"] == "@napi-rs/lzma-linux-x64-gnu" and
                   row["source_path"] == "package.json" and
                   row["upstream_repo"] == "Brooooooklyn/lzma",
                   "UNREVIEWED_DECLARATION_EXCEPTION")
        else:
            demand(row["source_path"] in {"LICENSE.md", "LICENSE"},
                   "NOT_A_LICENSE_SOURCE")
        if row.get("composite_notice_review") is not None:
            demand(row["package"] == "@rollup/rollup-linux-x64-gnu" and
                   row["composite_notice_review"] is True, "COMPOSITE_NOTICE_UNREVIEWED")
    demand(set(keys) == EXPECTED and len(set(keys)) == len(keys),
           "MISSING_OR_DUPLICATE_FLAG")
    return entries


def validate_census(rows: list[dict], evidence: list[dict]) -> None:
    demand(len(rows) == 2, "EXPECTED_TWO_CENSUSES")
    found = set()
    for c in rows:
        demand(c.get("schema") == "phios.frontend_license_evidence.v0.1" and
               c.get("status") == "INVENTORY_COMPLETE" and
               c.get("license_redistribution_cleared") is False and
               c.get("external_done") is False, "CENSUS_NOT_VERIFIED")
        app = c.get("app")
        demand(app in APPROVED and
               c.get("source_sha") == APPROVED[app]["git"] and
               c.get("npm_lock_sha256") == APPROVED[app]["lock_sha256"],
               "CENSUS_IDENTITY_DRIFT")
        queue = c.get("human_review_queue")
        components = c.get("components")
        demand(isinstance(queue, list) and isinstance(components, list) and
               len(queue) == c.get("flagged_count") and
               len(components) == c.get("installed_count"), "CENSUS_COUNTS")
        index = {item.get("path"): item for item in components}
        demand(len(index) == len(components), "DUPLICATE_COMPONENT")
        for flagged in queue:
            path = flagged.get("path")
            component = index.get(path)
            demand(component is not None and
                   path.startswith("node_modules/") and
                   "no-root-legal-file-found" in flagged.get("reasons", []),
                   "UNEXPECTED_REVIEW_REASON")
            key = (app, component["name"], component["version"])
            demand(key in EXPECTED and
                   component["license_declaration"] == "MIT" and
                   component["requires_human_review"] is True and
                   component["license_or_notice_files"] == [],
                   "FLAG_NOT_REVIEWED")
            found.add(key)
    demand(found == EXPECTED and
           len(evidence) == len(found), "INCOMPLETE_LICENSE_REVIEW_QUEUE")


def verify_source(row: dict, data: bytes) -> dict:
    demand(len(data) == row["source_bytes"] and
           git_blob_sha(data) == row["source_git_blob_sha"],
           "SOURCE_BYTES_DRIFT")
    if row["evidence_class"] == "IMMUTABLE_ROOT_LICENSE_FILE":
        intro = data[:700].decode("utf-8", errors="replace").lower()
        demand("mit license" in intro or "mit)" in intro,
               "NOT_A_REVIEWED_MIT_LICENSE_SOURCE")
    else:
        source = json.loads(data)
        demand(source.get("name") == "@napi-rs/lzma" and
               source.get("version") == "1.5.1" and
               source.get("license") == "MIT", "DECLARATION_DRIFT")
    return {
        "app": row["app"], "package": row["package"],
        "version": row["version"], "upstream_repo": row["upstream_repo"],
        "upstream_commit": row["upstream_commit"],
        "source_path": row["source_path"],
        "source_git_blob_sha": row["source_git_blob_sha"],
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "evidence_class": row["evidence_class"],
        "release_or_redistribution_cleared": False,
        "upstream_parent_child_binary_provenance_verified": False,
        "human_review_required": True,
    }


class RefuseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("PHIOS_NATIVE_LICENSE_REDIRECT_REJECTED")


def fetch_immutable_source(row: dict) -> bytes:
    # No dynamic hosts, credentials, redirects, repository writes, or artifact
    # packaging. Fetch only reviewed GitHub raw paths at immutable commits.
    url = ("https://raw.githubusercontent.com/" + row["upstream_repo"] + "/" +
           row["upstream_commit"] + "/" + row["source_path"])
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()),
                          RefuseRedirects())
    request = Request(url, headers={
        "User-Agent": "PhiOS-source-evidence-v068", "Accept": "text/plain",
    })
    with opener.open(request, timeout=20) as response:
        demand(response.status == 200 and
               response.geturl() == url, "UNEXPECTED_SOURCE_RESPONSE")
        data = response.read(row["source_bytes"] + 1)
    demand(len(data) == row["source_bytes"], "SOURCE_SIZE_DRIFT")
    return data


def build_report(manifest: dict, censuses: list[dict], fetcher=fetch_immutable_source) -> dict:
    evidence = validate_lock(manifest)
    validate_census(censuses, evidence)
    proofs = [verify_source(row, fetcher(row)) for row in evidence]
    manifest_digest = hashlib.sha256(json.dumps(
        proofs, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    return {
        "schema": SCHEMA, "status": "SOURCE_EVIDENCE_LOCKED",
        "source_evidence_sha256": manifest_digest,
        "upstream_sources_checked": len(proofs),
        "upstream_license_files_checked": 3,
        "declaration_only_source_count": 1,
        "proofs": proofs,
        "four_native_packages_reviewed_for_evidence": True,
        "full_legal_obligations_reviewed": False,
        "transitive_cargo_license_reviewed": False,
        "native_binary_provenance_verified": False,
        "redistribution_approved": False,
        "phios_install_authorized": False,
        "phios_launch_authorized": False,
        "external_done": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vessie-census", type=Path, required=True)
    parser.add_argument("--thinktank-census", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source_lock = json.loads(LOCK.read_text(encoding="utf-8"))
    censuses = [json.loads(args.vessie_census.read_text(encoding="utf-8")),
                json.loads(args.thinktank_census.read_text(encoding="utf-8"))]
    result = build_report(source_lock, censuses)
    demand(not args.report.exists() and not args.report.is_symlink(),
           "OUTPUT_ALREADY_EXISTS")
    with args.report.open("x", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2, sort_keys=True)
        fp.write("\n")
    print(json.dumps({
        "status": result["status"], "upstream_sources_checked": 4,
        "license_files": 3, "declaration_only": 1,
        "redistribution_approved": False, "external_done": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
