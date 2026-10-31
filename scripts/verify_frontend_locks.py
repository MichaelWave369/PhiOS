#!/usr/bin/env python3
"""PhiOS v0.65: verify and stage exact-source npm lock snapshots, fail closed."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APPROVED = {
    "vessie-web": {
        "git": "69a558ea2d1e8b361e05ded9bed4fc27b32e30cd",
        "subdir": "apps/vessie-web",
        "package_json_sha256": "6bdbd921cea13474fc2b6fd5cbe02765345a48e345a9cc57913e9b0693e9664e",
        "lock_sha256": "4e0ac5153f3bc47cd78b4f5cfa42c2ede4dbfef8110a2d5deda49d5c81bd6c2a",
        "lock_bytes": 38188,
    },
    "thinktank-web": {
        "git": "655d96f7ff892c9989f75cf874e74689f7694127",
        "subdir": ".",
        "package_json_sha256": "1ca7b23585f4bbb6cbd83a5248c03bb106568cb0af9d69faf138b8d3191f2eb7",
        "lock_sha256": "1dc173319bd4e20a1441147563a71e2a2c01ab6c13606f6f9e774ed3cad221c6",
        "lock_bytes": 40332,
    }
}

def demand(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("PHIOS_NPM_LOCK_" + reason)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def validate_lock(lock: Any, manifest: Any) -> int:
    demand(isinstance(lock, dict) and isinstance(manifest, dict), "SCHEMA")
    demand(lock.get("lockfileVersion") == 3 and lock.get("requires") is True,
           "LOCKFILE_VERSION")
    packages = lock.get("packages")
    demand(isinstance(packages, dict) and len(packages) >= 2, "EMPTY_GRAPH")
    root = packages.get("")
    demand(isinstance(root, dict), "MISSING_ROOT")
    for key in ("name", "version", "dependencies", "devDependencies"):
        demand(root.get(key, {} if "Dependencies" in key else None) ==
               manifest.get(key, {} if "Dependencies" in key else None),
               "ROOT_DRIFT_" + key)
    demand(lock.get("name") == manifest.get("name") and
           lock.get("version") == manifest.get("version"), "PACKAGE_IDENTITY")
    for path, details in packages.items():
        if path == "":
            continue
        demand(isinstance(path, str) and path.startswith("node_modules/") and
               ".." not in path.split("/") and "\\" not in path and
               isinstance(details, dict), "UNSAFE_PACKAGE_PATH")
        url = details.get("resolved")
        integrity = details.get("integrity")
        demand(isinstance(url, str) and url.startswith("https://registry.npmjs.org/")
               and "@" not in url.split("/")[2] and "?" not in url and "#" not in url,
               "UNTRUSTED_REGISTRY")
        demand(isinstance(integrity, str) and integrity.startswith("sha512-")
               and len(integrity) > 40 and details.get("link") is not True,
               "INTEGRITY_MISSING")
    return len(packages) - 1

def inspect(app: str, checkout: Path) -> tuple[dict[str, Any], Path, bytes]:
    demand(app in APPROVED, "UNREVIEWED_APP")
    item = APPROVED[app]
    checkout = checkout.resolve(strict=True)
    demand(checkout.is_dir(), "CHECKOUT_NOT_DIR")
    head = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True, check=True, text=True, timeout=20
    ).stdout.strip()
    demand(head == item["git"], "SOURCE_REVISION_DRIFT")
    source = (checkout / item["subdir"]).resolve(strict=True)
    demand(source == checkout or checkout in source.parents, "SOURCE_ESCAPE")
    manifest_path = source / "package.json"
    demand(manifest_path.is_file() and not manifest_path.is_symlink(), "MANIFEST_PATH")
    manifest_bytes = manifest_path.read_bytes()
    demand(sha(manifest_bytes) == item["package_json_sha256"], "MANIFEST_DIGEST")
    lock_path = ROOT / "dependency-locks" / app / "package-lock.json"
    demand(lock_path.is_file() and not lock_path.is_symlink(), "LOCKFILE_MISSING")
    lock_bytes = lock_path.read_bytes()
    demand(len(lock_bytes) == item["lock_bytes"] and
           sha(lock_bytes) == item["lock_sha256"], "LOCKFILE_DIGEST")
    count = validate_lock(json.loads(lock_bytes), json.loads(manifest_bytes))
    destination = source / "package-lock.json"
    if app == "thinktank-web":
        # ThinkTank #54 now commits its reviewed npm graph. Refuse injecting
        # the old PhiOS snapshot into an upstream checkout or accepting drift.
        demand(destination.is_file() and not destination.is_symlink(),
               "UPSTREAM_LOCKFILE_MISSING")
        demand(destination.read_bytes() == lock_bytes, "UPSTREAM_LOCKFILE_DRIFT")
        tracked = subprocess.run(
            ["git", "-C", str(checkout), "ls-files", "--error-unmatch",
             "package-lock.json"],
            capture_output=True, check=False, timeout=20
        )
        demand(tracked.returncode == 0, "UPSTREAM_LOCKFILE_UNTRACKED")
        committed = subprocess.check_output(
            ["git", "-C", str(checkout), "show", "HEAD:package-lock.json"],
            timeout=20
        )
        demand(committed == lock_bytes, "UPSTREAM_LOCKFILE_COMMIT_DRIFT")
    else:
        # Vessie has no upstream lock. The original exact reviewed snapshot
        # continues to be staged into the disposable checkout only.
        demand(not destination.exists() and not destination.is_symlink(),
               "UPSTREAM_LOCKFILE_PRESENT")
    return ({
        "schema": "phios.trellis_npm_closure.v0.1", "app": app,
        "source_sha": item["git"], "manifest_sha256": item["package_json_sha256"],
        "lock_sha256": item["lock_sha256"], "dependency_package_count": count,
        "node_required_major": 24, "npm_install_command": "npm ci --ignore-scripts",
        "source_modified": False, "phios_installed": False,
        "lock_provenance": ("COMMITTED_UPSTREAM" if app == "thinktank-web"
                            else "PHIOS_REVIEWED_SNAPSHOT"),
        "license_audit_complete": False, "binary_reproducibility_verified": False,
        "external_done": False
    }, source, lock_bytes)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=sorted(APPROVED), required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true",
                        help="Copy approved bytes to ephemeral source checkout only")
    args = parser.parse_args()
    report, source, lock_bytes = inspect(args.app, args.checkout)
    destination = source / "package-lock.json"
    if args.prepare:
        if args.app == "vessie-web":
            with destination.open("xb") as fp:
                fp.write(lock_bytes)
            demand(sha(destination.read_bytes()) == report["lock_sha256"], "COPY_DRIFT")
            report["source_modified"] = True
            report["only_change"] = "ephemeral CI checkout package-lock.json"
            report["copied_snapshot_bytes"] = len(lock_bytes)
        else:
            # Source lock is already pinned, committed and byte-for-byte
            # validated. Preparation has no write authority for ThinkTank.
            demand(destination.read_bytes() == lock_bytes, "UPSTREAM_LOCKFILE_DRIFT")
            report["only_change"] = "none; verified committed upstream lock"
            report["copied_snapshot_bytes"] = 0
    print(json.dumps(report, sort_keys=True))

if __name__ == "__main__":
    main()
