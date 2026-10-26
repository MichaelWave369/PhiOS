#!/usr/bin/env python3
"""Portable, PhiOS-independent ZIP export, verification and restore (no encryption)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

SCHEMA = "phios.exit.v0.1"
MAX_FILES = 10000
MAX_BYTES = 512 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not name.startswith("/") and "\\" not in name and (
        len(p.parts) > 0 and all(part not in ("", ".", "..") for part in name.split("/"))
    ) and not name.endswith("/") and not re.match(r"^[A-Za-z]:", name)


def pack(source: Path, output: Path) -> None:
    source = source.expanduser().resolve()
    output = output.expanduser().absolute()
    if not source.is_dir():
        raise ValueError("source must be an existing directory")
    if output.exists():
        raise ValueError("output already exists")
    if output.resolve().is_relative_to(source):
        raise ValueError("output must be outside the source directory")
    entries = []
    total = 0
    files = sorted(source.rglob("*"))
    for f in files:
        if f.is_symlink():
            raise ValueError(f"symlink not allowed: {f}")
        if f.is_dir():
            continue
        if not f.is_file():
            raise ValueError(f"not a regular file: {f}")
        name = f.relative_to(source).as_posix()
        if not safe_name(name) or name == "manifest.json":
            raise ValueError(f"invalid filename: {name}")
        total += f.stat().st_size
        if total > MAX_BYTES or len(entries) >= MAX_FILES:
            raise ValueError("archive limits exceeded")
        entries.append((name, f))
    manifest = {"schema": SCHEMA, "files": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
            for name, f in entries:
                data = f.read_bytes()
                manifest["files"].append({"path": name, "size": len(data), "sha256": digest(data)})
                z.writestr(f"data/{name}", data)
            z.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def verified_files(bundle: Path) -> list[tuple[str, bytes]]:
    results = []
    with zipfile.ZipFile(bundle, "r") as z:
        infos = z.infolist()
        names = [info.filename for info in infos]
        if len(set(names)) != len(names) or "manifest.json" not in names:
            raise ValueError("missing manifest or duplicate ZIP entries")
        if len(infos) > MAX_FILES + 1 or any(
            info.is_dir() or info.file_size > MAX_BYTES for info in infos
        ):
            raise ValueError("ZIP entry/size limit exceeded")
        if sum(i.file_size for i in infos) > MAX_BYTES + 1024 * 1024:
            raise ValueError("ZIP total size limit exceeded")
        if any(not safe_name(n) for n in names):
            raise ValueError("unsafe ZIP path")
        manifest = json.loads(z.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            raise ValueError("unknown schema")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) > MAX_FILES:
            raise ValueError("invalid file list")
        expected = {"manifest.json"}
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
                raise ValueError("invalid manifest entry")
            name, size, sha = item["path"], item["size"], item["sha256"]
            if not isinstance(name, str) or not safe_name(name) or name == "manifest.json":
                raise ValueError("unsafe manifest path")
            if type(size) is not int or size < 0 or size > MAX_BYTES:
                raise ValueError("invalid file size")
            if not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha):
                raise ValueError("invalid checksum")
            archive_name = f"data/{name}"
            if archive_name in expected:
                raise ValueError("duplicate manifest path")
            expected.add(archive_name)
            info = z.getinfo(archive_name)
            if info.file_size != size:
                raise ValueError("size mismatch")
            data = z.read(archive_name)
            if len(data) != size or digest(data) != sha:
                raise ValueError("checksum mismatch")
            results.append((name, data))
        if set(names) != expected:
            raise ValueError("unexpected or missing archive members")
    return results


def unpack(bundle: Path, output: Path) -> None:
    output = output.expanduser().absolute()
    if output.exists():
        raise ValueError("restore destination already exists")
    files = verified_files(bundle)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".phi-exit-") as staging:
        base = Path(staging) / "restore"
        base.mkdir()
        for name, data in files:
            dest = base.joinpath(*PurePosixPath(name).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        os.replace(base, output)


def main() -> int:
    p = argparse.ArgumentParser(description="Φ independent directory exit/restore tool (unencrypted)")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("pack")
    a.add_argument("--source", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    b = sub.add_parser("verify")
    b.add_argument("--bundle", type=Path, required=True)
    c = sub.add_parser("unpack")
    c.add_argument("--bundle", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "pack":
            pack(args.source, args.output)
        elif args.command == "verify":
            verified_files(args.bundle)
        else:
            unpack(args.bundle, args.output)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        p.exit(1, f"FAILED: {exc}\n")
    print(f"PASS: {args.command} (PhiOS services not required; archive is NOT encrypted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
