#!/usr/bin/env python3
"""PhiOS v0.60: reviewed static web assets -> UNTRUSTED Trellis staging only.
No network, source builds, Trellis execution, AppRegistry writes or launch grants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_ecosystem_app_candidates import (
    CANDIDATES, CATALOG_FILE, FIXED_SOURCES, inspect_candidates
)

SCHEMA = "phios.trellis_staging_receipt.v0.1"
VERSION = "0.1.0"
MAX_FILES = 2048
MAX_SIZE = 64 * 1024 * 1024
HEX = re.compile(r"^[a-f0-9]{64}$")


def demand(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("PHIOS_TRELLIS_BRIDGE_" + message)


def candidates() -> dict[str, dict]:
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    inspect_candidates(payload, catalog)
    return {x["app_key"]: x for x in payload["candidates"]}


def regular_files(root: Path) -> list[Path]:
    demand(root.is_dir() and not root.is_symlink(), "SOURCE_NOT_REGULAR_DIRECTORY")
    files: list[Path] = []
    total = 0
    for base, directories, names in os.walk(root, followlinks=False):
        for name in directories:
            demand(not (Path(base) / name).is_symlink(), "SOURCE_SYMLINK_DIRECTORY")
        for name in names:
            path = Path(base) / name
            demand(not path.is_symlink() and path.is_file(), "SOURCE_NONREGULAR_FILE")
            st = path.stat()
            demand(st.st_nlink == 1, "SOURCE_HARDLINK_REFUSED")
            total += st.st_size
            demand(total <= MAX_SIZE, "SIZE_BUDGET")
            files.append(path.relative_to(root))
            demand(len(files) <= MAX_FILES, "FILE_COUNT_BUDGET")
    demand(len(files) > 1 and Path("index.html") in files, "MISSING_FRONTEND_ENTRY")
    return sorted(files, key=lambda path: path.as_posix().encode("utf-8"))


def dir_digest(root: Path, files: list[Path]) -> tuple[str, list[dict]]:
    # Exactly Trellis 1.0-rc1 src/trust/checksum.rs: relative POSIX path,
    # NUL, full file bytes, 0xff, sorted by UTF-8 bytewise path.
    h = hashlib.sha256()
    entries = []
    for rel in files:
        data = (root / rel).read_bytes()
        h.update(rel.as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\xff")
        entries.append({"path": rel.as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data)})
    return h.hexdigest(), entries


def check_html(root: Path, files: list[Path]) -> None:
    html = (root / "index.html").read_text(encoding="utf-8")
    demand('id="root"' in html, "REACT_ROOT_MISSING")
    demand(not re.search(r"""(?:src|href)=["']/(?:assets/|SuperPhiVessel/|think-tank/)""", html),
           "NONRELOCATABLE_PAGES_ASSET_BASE")
    demand(not re.search(r"""(?:src|href)=["']https?://""", html),
           "EXTERNAL_ENTRY_ASSET")
    demand('src="./assets/' in html or 'src="assets/' in html, "MISSING_RELATIVE_JS")
    demand(any(p.as_posix().startswith("assets/") and p.suffix == ".js" for p in files),
           "MISSING_COMPILED_JS")
    demand(any(p.as_posix().startswith("assets/") and p.suffix == ".css" for p in files),
           "MISSING_COMPILED_CSS")
    # HTML entrypoint validation is NOT proof that runtime HTTP calls are offline.


def pinned_git_sha(checkout: Path) -> str:
    p = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                       capture_output=True, text=True, timeout=10, check=True)
    sha = p.stdout.strip()
    demand(re.fullmatch(r"[a-f0-9]{40}", sha) is not None, "INVALID_GIT_SHA")
    return sha


def plan(key: str) -> dict[str, Any]:
    entry = candidates().get(key)
    demand(entry is not None, "UNKNOWN_CANDIDATE")
    return {"schema": "phios.trellis_bridge_plan.v0.1", "candidate": key,
            "source_sha": entry["source_sha"],
            "source_repository": entry["manifest"]["source"]["repository_url"],
            "staging_package_name": "phios-" + key, "package_kind": "source",
            "trellis_source_type": "local_dir", "sha256_required": True,
            "trellis_executed_by_bridge": False, "staging_only": True,
            "installed_by_phios": False, "launch_authority": False,
            "redistribution_reviewed": False, "runtime_offline_verified": False,
            "external_done": False}


def spec_yaml(package: str, digest: str, paths: list[str], homepage: str) -> str:
    demand(HEX.fullmatch(digest) is not None, "INVALID_SOURCE_DIGEST")
    demand(all(re.fullmatch(r"[a-zA-Z0-9._-]+", x) for x in paths), "INVALID_SPEC_ENTRY")
    # All interpolated fields are controlled by the strict candidate schema.
    return (f'schema_version: "0.2"\nname: {package}\nversion: {VERSION}\n'
            'description: "Unapproved PhiOS static frontend staging only"\n'
            f'homepage: "{homepage}"\nkind: source\nsource:\n'
            '  type: local_dir\n  path: payload\n'
            f'  checksum_sha256: {digest}\n  signature: null\n'
            'install:\n  strategy: copy\n  entries:\n' +
            "".join(f'    - "{x}"\n' for x in paths) +
            'bin: {}\ndependencies: []\nprovenance:\n'
            '  publisher: MichaelWave369\n  license: MIT\n'
            '  registry: phios-untrusted-staging-only\n'
            'platform:\n  os: [linux]\n  arch: [x86_64]\n'
            'post_install: null\nhealth:\n'
            '  notes: "License and PhiOS install / launch reviews not yet complete"\n')


def stage(key: str, checkout: Path, output: Path) -> dict[str, Any]:
    entry = candidates().get(key)
    demand(entry is not None, "UNKNOWN_CANDIDATE")
    demand(not checkout.is_symlink(), "CHECKOUT_SYMLINK")
    checkout = checkout.resolve(strict=True)
    demand(checkout.is_dir(), "CHECKOUT_NOT_DIRECTORY")
    demand(pinned_git_sha(checkout) == entry["source_sha"], "SOURCE_SHA_MISMATCH")
    root = checkout / entry["source_build"]["current_output_from_repo_root"]
    files = regular_files(root)
    check_html(root, files)
    output = output.absolute()
    demand(not output.exists() and not output.is_symlink(), "DESTINATION_EXISTS")
    demand(checkout not in output.parents and output != checkout, "DESTINATION_IN_CHECKOUT")
    demand(not any(p.is_symlink() for p in output.parents), "DESTINATION_PARENT_SYMLINK")
    payload = output / "payload"
    try:
        payload.mkdir(parents=True, exist_ok=False)
        for rel in files:
            target = payload / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, target)
        copied = regular_files(payload)
        demand(files == copied, "COPIED_FILESET_MISMATCH")
        digest, entries = dir_digest(payload, copied)
        demand(dir_digest(root, files)[0] == digest, "COPIED_BYTES_MISMATCH")
        pkg = "phios-" + key
        spec_file = pkg + ".trellis.yaml"
        spec = spec_yaml(pkg, digest, sorted({p.parts[0] for p in files}), entry["web"]["url"])
        (output / spec_file).write_text(spec, encoding="utf-8")
        report = {"schema": SCHEMA, "candidate": key, "source_sha": entry["source_sha"],
                  "manifest_app_id": entry["manifest"]["app_id"],
                  "package": pkg, "version": VERSION, "payload_sha256": digest,
                  "files": entries, "spec": spec_file,
                  "spec_sha256": hashlib.sha256(spec.encode()).hexdigest(),
                  "trellis_binary_included": False, "staging_only": True,
                  "installed_by_phios": False, "launch_authority": False,
                  "redistribution_reviewed": False, "runtime_offline_verified": False,
                  "external_done": False}
        (output / "bridge-receipt.json").write_text(json.dumps(report, indent=2)+"\n",
                                                     encoding="utf-8")
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return report


def verify_staged(stage_dir: Path, trellis_home: Path) -> dict[str, Any]:
    """Independently rehash ALL installed assets. Trellis verify checks receipt
    and lock *existence*, but does not rehash all installed static asset bytes.
    """
    stage_dir = stage_dir.resolve(strict=True)
    trellis_home = trellis_home.resolve(strict=True)
    report = json.loads((stage_dir / "bridge-receipt.json").read_text(encoding="utf-8"))
    keys = {"schema", "candidate", "source_sha", "manifest_app_id", "package",
            "version", "payload_sha256", "files", "spec", "spec_sha256",
            "trellis_binary_included", "staging_only", "installed_by_phios",
            "launch_authority", "redistribution_reviewed", "runtime_offline_verified",
            "external_done"}
    demand(isinstance(report, dict) and set(report) == keys, "RECEIPT_FIELDS")
    demand(report["schema"] == SCHEMA and report["staging_only"] is True and
           report["trellis_binary_included"] is False and
           all(report[x] is False for x in (
               "installed_by_phios", "launch_authority", "redistribution_reviewed",
               "runtime_offline_verified", "external_done")), "RECEIPT_AUTHORITY")
    key = report["candidate"]
    entry = candidates().get(key)
    demand(entry is not None and entry["source_sha"] == report["source_sha"] and
           entry["manifest"]["app_id"] == report["manifest_app_id"], "CANDIDATE_DRIFT")
    demand(report["package"] == "phios-" + key and report["version"] == VERSION,
           "PACKAGE_IDENTITY")
    demand(report["spec"] == report["package"] + ".trellis.yaml", "SPEC_PATH")
    spec = stage_dir / report["spec"]
    demand(spec.is_file() and not spec.is_symlink() and
           hashlib.sha256(spec.read_bytes()).hexdigest() == report["spec_sha256"],
           "SPEC_DRIFT")
    payload = stage_dir / "payload"
    src_files = regular_files(payload)
    digest, hashes = dir_digest(payload, src_files)
    demand(digest == report["payload_sha256"] and hashes == report["files"],
           "STAGED_PAYLOAD_DRIFT")
    installed = trellis_home / "cellar" / report["package"] / VERSION
    installed_files = regular_files(installed)
    actual, installed_hashes = dir_digest(installed, installed_files)
    demand(actual == digest and installed_hashes == hashes, "INSTALLED_BYTES_DRIFT")
    trellis_receipt = json.loads(
        (trellis_home / "receipts" / (report["package"] + ".json")).read_text())
    demand(trellis_receipt["name"] == report["package"] and
           trellis_receipt["version"] == VERSION, "TRELLIS_RECEIPT_IDENTITY")
    demand(trellis_receipt["source"]["checksum_expected_sha256"] == digest and
           trellis_receipt["source"]["checksum_actual_sha256"] == digest and
           trellis_receipt["platform_evaluated"]["matched"] is True,
           "TRELLIS_RECEIPT_INTEGRITY")
    demand(set(trellis_receipt["installed_files"]) ==
           {str(installed / f) for f in installed_files}, "TRELLIS_RECEIPT_FILESET")
    lock = json.loads((trellis_home / "locks/default.lock.json").read_text())
    demand(lock["profile"] == "default" and any(
        x["name"] == report["package"] and x["version"] == VERSION
        for x in lock["packages"]), "TRELLIS_LOCK")
    return {"schema": "phios.trellis_stage_verification.v0.1", "candidate": key,
            "payload_sha256": digest, "verified_files": len(installed_files),
            "trellis_receipt_checked": True, "all_installed_bytes_rehashed": True,
            "disposable_trellis_home_only": True, "phi_os_installed": False,
            "phi_os_launch_authorized": False, "offline_runtime_verified": False,
            "external_done": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    view = subs.add_parser("plan")
    view.add_argument("app", choices=sorted(FIXED_SOURCES))
    staging = subs.add_parser("stage")
    staging.add_argument("app", choices=sorted(FIXED_SOURCES))
    staging.add_argument("--checkout", type=Path, required=True)
    staging.add_argument("--output", type=Path, required=True)
    check = subs.add_parser("verify-staged")
    check.add_argument("--staging", type=Path, required=True)
    check.add_argument("--trellis-home", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        result = plan(args.app)
    elif args.command == "stage":
        result = stage(args.app, args.checkout, args.output)
    else:
        result = verify_staged(args.staging, args.trellis_home)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
