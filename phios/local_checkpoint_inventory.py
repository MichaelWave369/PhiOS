"""Explicit, read-only checkpoint byte inventory; not model loading or validation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

MAX_FILES = 9
MAX_BUDGET = 128 * 1024**3
DEFAULT_BUDGET = 32 * 1024**3
MAX_HEADER = 1024 * 1024
CHUNK = 1024 * 1024


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def ordinary(info):
    # Reject symlinks, directories, devices and Windows reparse points.
    return stat.S_ISREG(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def header_hint(prefix, size):
    """Only identify plausible headers; never certify tensors or architecture."""
    if len(prefix) >= 8 and prefix[:4] == b"GGUF":
        version = struct.unpack_from("<I", prefix, 4)[0]
        if version in (2, 3) and size >= 24:
            return "GGUF_HEADER_HINT"
        return "UNRECOGNIZED"
    if len(prefix) >= 8:
        length = struct.unpack_from("<Q", prefix)[0]
        if 2 <= length <= MAX_HEADER and 8 + length <= len(prefix):
            try:
                data = json.loads(prefix[8:8 + length])
                tensors = [v for k, v in data.items() if k != "__metadata__"]
                if tensors and all(
                    isinstance(v, dict)
                    and isinstance(v.get("dtype"), str)
                    and isinstance(v.get("shape"), list)
                    and all(type(d) is int and d >= 0 for d in v["shape"])
                    and isinstance(v.get("data_offsets"), list)
                    and len(v["data_offsets"]) == 2
                    and all(type(d) is int for d in v["data_offsets"])
                    and 0 <= v["data_offsets"][0] <= v["data_offsets"][1] <= size - 8 - length
                    for v in tensors
                ):
                    return "SAFETENSORS_HEADER_HINT"
            except (ValueError, AttributeError, RecursionError):
                pass
    return "UNRECOGNIZED"


def inspect_file(path, before, expected):
    """Read the selected bytes once; compare metadata before and after."""
    digest = hashlib.sha256()
    prefix = bytearray()
    count = 0
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not ordinary(opened) or identity(opened) != identity(before):
            raise ValueError("selected file changed before reading")
        while count < opened.st_size:
            block = stream.read(min(CHUNK, opened.st_size - count))
            if not block:
                raise ValueError("selected file shortened during reading")
            count += len(block)
            digest.update(block)
            remaining = MAX_HEADER + 8 - len(prefix)
            if remaining > 0:
                prefix.extend(block[:remaining])
        if stream.read(1):
            raise ValueError("selected file grew during reading")
        after = os.fstat(stream.fileno())
        named = os.lstat(path)
        if not ordinary(named) or identity(after) != identity(opened) or identity(named) != identity(opened):
            raise ValueError("selected file changed during reading")
    actual = digest.hexdigest()
    return {
        "observed_bytes": count,
        "sha256": actual,
        "format_hint": header_hint(prefix, count),
        "comparison": "NOT_PROVIDED" if expected is None else (
            "MATCH" if actual == expected else "MISMATCH"
        ),
    }


def inventory(paths, expected=None, budget=DEFAULT_BUDGET):
    if type(budget) is not int or not 1 <= budget <= MAX_BUDGET:
        raise ValueError("invalid byte budget")
    if not 1 <= len(paths) <= MAX_FILES:
        raise ValueError("select between one and nine explicit files")
    expected = [None] * len(paths) if expected is None else expected
    if len(expected) != len(paths) or any(
        x is not None and (not isinstance(x, str) or not re.fullmatch(r"[0-9a-f]{64}", x))
        for x in expected
    ):
        raise ValueError("provide one lowercase SHA-256 per selected file")
    selected = []
    seen = set()
    total = 0
    for path in paths:
        p = Path(path)
        info = os.lstat(p)
        if not ordinary(info) or info.st_size <= 0:
            raise ValueError("select a nonempty ordinary file")
        key = (info.st_dev, info.st_ino)
        if key in seen:
            raise ValueError("duplicate file identity")
        seen.add(key)
        total += info.st_size
        if total > budget:
            raise ValueError("selected files exceed byte budget")
        selected.append((p, info))
    rows = []
    for i, ((path, before), wanted) in enumerate(zip(selected, expected), 1):
        rows.append({"selection": i, **inspect_file(path, before, wanted)})
    mismatch = any(row["comparison"] == "MISMATCH" for row in rows)
    return {
        "schema": "phios.local-intelligence.checkpoints.r02",
        "status": "HASH_MISMATCH" if mismatch else "REVIEW_ONLY",
        "observed_total_bytes": sum(row["observed_bytes"] for row in rows),
        "checkpoints": rows,
        "model_loaded": False,
        "inference_executed": False,
        "weight_validity_verified": False,
        "authority_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="append", required=True)
    parser.add_argument("--expected-sha256", action="append")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_BUDGET)
    args = parser.parse_args()
    try:
        report = inventory(args.checkpoint, args.expected_sha256, args.max_bytes)
    except (OSError, ValueError):
        # Do not echo private filesystem paths or partial receipts.
        print(json.dumps({"status": "INVALID_OR_UNREADABLE_SELECTION"}))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 3 if report["status"] == "HASH_MISMATCH" else 0


if __name__ == "__main__":
    raise SystemExit(main())
