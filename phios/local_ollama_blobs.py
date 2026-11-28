"""Offline verification of explicitly selected Ollama manifest blob bytes."""

import argparse
import json
import os
from pathlib import Path
import re
import stat

from phios.local_checkpoint_inventory import (
    DEFAULT_BUDGET,
    MAX_BUDGET,
    identity,
    inspect_file,
    ordinary,
)

MAX_MANIFEST = 256 * 1024
MAX_BLOBS = 64
WEIGHT_TYPE = "application/vnd.ollama.image.model"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_manifest(path):
    before = os.lstat(path)
    if not ordinary(before) or not 0 < before.st_size <= MAX_MANIFEST:
        raise ValueError("invalid manifest file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not ordinary(opened) or identity(opened) != identity(before):
            raise ValueError("manifest changed before reading")
        body = stream.read(MAX_MANIFEST + 1)
        if (len(body) != before.st_size
                or identity(os.fstat(stream.fileno())) != identity(before)
                or identity(os.lstat(path)) != identity(before)):
            raise ValueError("manifest changed during reading")
    return json.loads(body, object_pairs_hook=unique_object)


def descriptors(manifest):
    if not isinstance(manifest, dict) or type(manifest.get("schemaVersion")) is not int:
        raise ValueError("invalid manifest schema")
    if manifest["schemaVersion"] != 2:
        raise ValueError("unsupported manifest schema")
    layers = manifest.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) < MAX_BLOBS:
        raise ValueError("invalid layer count")
    result = {}
    weight_count = 0
    for index, row in enumerate([manifest.get("config"), *layers]):
        if not isinstance(row, dict):
            raise ValueError("invalid descriptor")
        digest, size, media = row.get("digest"), row.get("size"), row.get("mediaType")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("invalid descriptor digest")
        if type(size) is not int or not 0 < size <= MAX_BUDGET:
            raise ValueError("invalid descriptor size")
        if not isinstance(media, str) or not media or len(media) > 256:
            raise ValueError("invalid descriptor media type")
        if row.get("urls") or row.get("data"):
            raise ValueError("external or inline descriptors unsupported")
        is_weight = index > 0 and media == WEIGHT_TYPE
        weight_count += int(is_weight)
        if digest in result:
            if result[digest]["size"] != size:
                raise ValueError("conflicting descriptor sizes")
            result[digest]["weight"] |= is_weight
        else:
            result[digest] = {"size": size, "weight": is_weight}
    return result, weight_count


def ordinary_directory(path):
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("select ordinary local directories")


def verify(root, manifest_relative, budget=DEFAULT_BUDGET):
    if type(budget) is not int or not 1 <= budget <= MAX_BUDGET:
        raise ValueError("invalid byte budget")
    # Accept portable relative manifest names only; never infer from model tags.
    if not isinstance(manifest_relative, str) or len(manifest_relative) > 1024:
        raise ValueError("invalid manifest path")
    parts = manifest_relative.split("/")
    if (len(parts) < 2 or len(parts) > 12 or parts[0] != "manifests"
            or any(not re.fullmatch(r"[A-Za-z0-9._-]+", p) or p in (".", "..")
                   for p in parts)):
        raise ValueError("invalid manifest path")
    root = Path(root)
    ordinary_directory(root)
    parent = root
    for part in parts[:-1]:
        parent = parent / part
        ordinary_directory(parent)
    manifest_path = parent / parts[-1]
    declared, weight_count = descriptors(read_manifest(manifest_path))
    total = sum(row["size"] for row in declared.values())
    if total > budget:
        raise ValueError("declared blobs exceed byte budget")
    if not weight_count:
        return receipt("NO_MODEL_WEIGHT_DESCRIPTOR", [], weight_count)
    blob_dir = root / "blobs"
    ordinary_directory(blob_dir)
    selected = []
    seen = set()
    for digest, row in sorted(declared.items()):
        path = blob_dir / digest.replace(":", "-", 1)
        before = os.lstat(path)
        if not ordinary(before) or before.st_size != row["size"]:
            raise ValueError("missing, nonregular or size-mismatched blob")
        key = (before.st_dev, before.st_ino)
        if key in seen:
            raise ValueError("duplicate physical blob identity")
        seen.add(key)
        selected.append((path, before, digest, row["weight"]))
    rows = []
    for path, before, digest, weight in selected:
        observed = inspect_file(path, before, digest[7:])
        rows.append({
            "observed_bytes": observed["observed_bytes"],
            "comparison": observed["comparison"],
            "model_weight_descriptor": weight,
            "format_hint": observed["format_hint"] if weight else "NOT_CHECKED",
        })
    if any(row["comparison"] != "MATCH" for row in rows):
        status = "HASH_MISMATCH"
    elif any(row["model_weight_descriptor"] and row["format_hint"] != "GGUF_HEADER_HINT"
             for row in rows):
        status = "BLOB_BYTES_MATCH_WEIGHT_FORMAT_UNVERIFIED"
    else:
        status = "BLOB_BYTES_MATCH_REVIEW_ONLY"
    return receipt(status, rows, weight_count)


def receipt(status, rows, weight_count):
    return {
        "schema": "phios.local-intelligence.ollama-blobs.r02b",
        "status": status,
        "weight_descriptor_count": weight_count,
        "verified_selection_bytes": sum(row["observed_bytes"] for row in rows),
        "blobs": rows,
        "model_loaded": False,
        "inference_executed": False,
        "weight_validity_verified": False,
        "offline_readiness_verified": False,
        "authority_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_BUDGET)
    args = parser.parse_args()
    try:
        report = verify(args.root, args.manifest, args.max_bytes)
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"status": "INVALID_OR_UNREADABLE_SELECTION"}))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "BLOB_BYTES_MATCH_REVIEW_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
