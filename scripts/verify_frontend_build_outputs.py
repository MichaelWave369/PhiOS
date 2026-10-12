#!/usr/bin/env python3
"""PhiOS v0.66: compare exact bytes of two separately built pinned React bundles.

No install, desktop launch, license review or cross-platform reproducibility claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_frontend_locks import APPROVED

SCHEMA = "phios.trellis_two_clean_builds.v0.1"


def demand(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError("PHIOS_BUILD_REPLAY_" + code)


def hash_data(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(root: Path) -> tuple[dict[str, str], str]:
    root = root.absolute()
    demand(root.exists() and root.is_dir() and not root.is_symlink() and
           root.resolve() == root, "OUTPUT_DIRECTORY_INVALID")
    files: dict[str, str] = {}
    for directory, dirs, names in os.walk(root, topdown=True, followlinks=False):
        parent = Path(directory)
        demand(not parent.is_symlink(), "SYMLINK_DIRECTORY")
        for dirname in dirs:
            demand(not (parent / dirname).is_symlink(), "SYMLINK_DIRECTORY")
            demand(not dirname.startswith("."), "HIDDEN_DIRECTORY")
        for filename in names:
            file = parent / filename
            demand(file.is_file() and not file.is_symlink(), "UNSAFE_OUTPUT_FILE")
            relative = file.relative_to(root).as_posix()
            demand(not filename.startswith(".") and
                   all(bit not in ("", ".", "..") for bit in relative.split("/")),
                   "UNSAFE_OUTPUT_PATH")
            files[relative] = hash_data(file.read_bytes())
    demand("index.html" in files and len(files) >= 2, "OUTPUT_SET_INCOMPLETE")
    demand(any(name.startswith("assets/") and name.endswith(".js")
               for name in files), "COMPILED_SCRIPT_MISSING")
    sorted_files = dict(sorted(files.items()))
    manifest = json.dumps(sorted_files, ensure_ascii=True,
                          sort_keys=True, separators=(",", ":")).encode()
    return sorted_files, hash_data(manifest)


def compare(app: str, first: Path, second: Path) -> dict[str, Any]:
    demand(app in APPROVED, "UNREVIEWED_APP")
    first = first.absolute()
    second = second.absolute()
    demand(first != second and first not in second.parents and
           second not in first.parents, "SHARED_OUTPUT_DIRECTORY")
    a, adigest = inventory(first)
    b, bdigest = inventory(second)
    demand(a.keys() == b.keys(), "OUTPUT_FILESET_DRIFT")
    demand(a == b, "OUTPUT_BYTE_DRIFT")
    demand(adigest == bdigest, "OUTPUT_MANIFEST_DRIFT")
    return {
        "schema": SCHEMA, "app": app, "status": "PASS",
        "source_sha": APPROVED[app]["git"],
        "npm_lock_sha256": APPROVED[app]["lock_sha256"],
        "output_file_count": len(a), "file_sha256": a,
        "output_manifest_sha256": adigest,
        "same_runner_two_independent_source_trees": True,
        "comparison": "same filenames and exact SHA-256 of every output byte",
        "multi_machine_reproducibility_verified": False,
        "physical_airgap_verified": False,
        "license_clearance_verified": False,
        "phios_installed": False, "phios_launch_authorized": False,
        "model_execution_verified": False, "external_done": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", choices=sorted(APPROVED), required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(args.app, args.first, args.second)
    except (ValueError, OSError) as exc:
        result = {
            "schema": SCHEMA, "app": args.app, "status": "FAIL",
            "issues": [str(exc)], "multi_machine_reproducibility_verified": False,
            "license_clearance_verified": False, "phios_installed": False,
            "phios_launch_authorized": False, "external_done": False,
        }
    args.report.absolute().write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
