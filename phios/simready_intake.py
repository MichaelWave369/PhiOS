"""Offline, advisory planner for NVIDIA SimReady package downloads."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

DATASET = "nvidia/simready-assets"
MANIFEST = "com.nvidia.simready.packaging.json"
LICENSE = "CC-BY-4.0"
MAX_FILES = 250_000
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_ASSETS = 36


def safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError("invalid path")
    parts = value.split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9._-]+", p) or p in (".", "..") for p in parts):
        raise ValueError("unsafe or unsupported path")
    return PurePosixPath(value)


def plan(inventory, selected, budget_bytes):
    """Build a deterministic plan; sizes are declared, not independently verified."""
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be an object")
    if inventory.get("dataset") != DATASET:
        raise ValueError("unexpected dataset")
    revision = inventory.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("a pinned 40-character revision is required")
    if type(budget_bytes) is not int or budget_bytes <= 0:
        raise ValueError("positive integer byte budget required")
    if not isinstance(selected, list) or not 1 <= len(selected) <= MAX_ASSETS:
        raise ValueError("select between 1 and 36 packages")
    roots = sorted(str(safe_path(p)) for p in selected)
    if len(set(roots)) != len(roots):
        raise ValueError("duplicate package selection")
    rows = inventory.get("files")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise ValueError("invalid inventory file list")
    entries = {}
    manifests = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid inventory row")
        path = safe_path(row.get("path"))
        size = row.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("invalid declared file size")
        if str(path) in entries:
            raise ValueError("duplicate inventory path")
        entries[str(path)] = size
        if path.name == MANIFEST:
            manifests.add(str(path.parent))
    for root in roots:
        if root not in manifests:
            raise ValueError("selected package has no manifest: " + root)
        if any(other != root and other.startswith(root + "/") for other in manifests):
            raise ValueError("nested package boundary is ambiguous: " + root)
    groups = defaultdict(list)
    total = 0
    for path, size in sorted(entries.items()):
        for root in roots:
            if path.startswith(root + "/"):
                groups[root].append({"path": path, "size": size})
                total += size
                break
    packages = [
        {
            "package": root,
            "declared_bytes": sum(item["size"] for item in groups[root]),
            "files": groups[root],
        }
        for root in roots
    ]
    return {
        "schema": "phisimready.plan.v1",
        "dataset": DATASET,
        "revision": revision,
        "license": LICENSE,
        "attribution": "NVIDIA SimReady Assets",
        "source": "https://huggingface.co/datasets/nvidia/simready-assets",
        "declared_total_bytes": total,
        "budget_bytes": budget_bytes,
        "status": "REVIEW_ONLY" if total <= budget_bytes else "OVER_BUDGET",
        "packages": packages,
        "limitations": [
            "Inventory completeness, file sizes and license claims are not authenticated.",
            "External USD dependencies and physics conformance are not verified.",
            "No download, conversion, extraction or execution authority.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--package", action="append", required=True)
    parser.add_argument("--budget-bytes", type=int, required=True)
    args = parser.parse_args()
    try:
        with args.inventory.open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("inventory exceeds input limit")
        receipt = plan(json.loads(raw), args.package, args.budget_bytes)
    except (OSError, ValueError, RecursionError) as exc:
        parser.exit(2, f"intake rejected: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "REVIEW_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
