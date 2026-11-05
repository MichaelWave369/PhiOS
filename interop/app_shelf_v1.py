"""Φ Universal Shelf R2. Explicit, offline, source-only portable bookmarks.

This CLI manages a chosen JSON *shelf*, not application packages or executable
permissions. Existing PhiOS App Platform install/launch gates are unaffected.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from shell_catalog_v1 import read_catalog

FORMAT = "phios-app-shelf"
VERSION = 1
LIMIT = 24
MAX_BYTES = 16 * 1024
FIELDS = {"format", "version", "catalog_source_sha", "exported_at", "pinned"}
PIN = re.compile(r"github:[0-9]{1,20}\Z")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")


def _inventory() -> tuple[dict[str, dict], str]:
    catalog = read_catalog()
    return {entry["id"]: entry for entry in catalog["apps"]}, catalog["provenance"]["source_blob_sha"]


def validate_pins(pins: object, inventory: dict[str, dict]) -> list[str]:
    if not isinstance(pins, list) or len(pins) > LIMIT:
        raise ValueError("Shelf exceeds 24 source pins")
    seen: set[str] = set()
    for candidate in pins:
        if (not isinstance(candidate, str) or not PIN.fullmatch(candidate)
                or candidate not in inventory or candidate in seen):
            raise ValueError("Shelf pin is unknown, duplicate, or malformed")
        seen.add(candidate)
    return list(pins)


def encode_shelf(pins: list[str], *, timestamp: datetime | None = None) -> dict:
    inventory, sha = _inventory()
    verified = validate_pins(pins, inventory)
    when = timestamp or datetime.now(timezone.utc)
    if when.tzinfo is None:
        raise ValueError("Timestamp requires UTC")
    stamp = when.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {"format": FORMAT, "version": VERSION, "catalog_source_sha": sha,
            "exported_at": stamp, "pinned": verified}


def decode_shelf(value: object) -> list[str]:
    inventory, sha = _inventory()
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Unsupported shelf fields")
    if value.get("format") != FORMAT or type(value.get("version")) is not int or value["version"] != VERSION:
        raise ValueError("Unsupported shelf version")
    if value.get("catalog_source_sha") != sha:
        raise ValueError("Different catalog snapshot: do not silently map unknown identities")
    at = value.get("exported_at")
    if not isinstance(at, str) or not TIME.fullmatch(at):
        raise ValueError("Invalid shelf timestamp")
    try:
        datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid shelf timestamp") from exc
    return validate_pins(value.get("pinned"), inventory)


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Shelf file is missing, symlinked or too large")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid UTF-8 JSON shelf") from exc


def read_shelf(path: Path) -> list[str]:
    if not path.exists():
        if path.is_symlink():
            raise ValueError("Symlinked shelf denied")
        return []
    return decode_shelf(_read_json(path))


def _write_atomic(path: Path, contents: str) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Non-regular/symlink shelf denied")
    if not path.parent.is_dir():
        raise ValueError("Select an existing destination directory")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".phios-shelf-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(handle.name, 0o600)
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _serialize(pins: list[str]) -> str:
    return json.dumps(encode_shelf(pins), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Portable source-only PhiOS App Shelf. Never installs or launches.")
    p.add_argument("--shelf", type=Path, required=True, help="Explicit local shelf JSON path")
    sp = p.add_subparsers(dest="command", required=True)
    sp.add_parser("list")
    pin = sp.add_parser("pin")
    pin.add_argument("id", help="Public source ID, e.g. github:1312447255")
    unpin = sp.add_parser("unpin")
    unpin.add_argument("id")
    move = sp.add_parser("move")
    move.add_argument("id")
    move.add_argument("direction", choices=["up", "down"])
    export = sp.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    restore = sp.add_parser("import")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--confirm-replace", action="store_true")
    args = p.parse_args(argv)
    ids, _ = _inventory()
    current = read_shelf(args.shelf)
    if args.command == "list":
        print(f"Φ Shelf: {len(current)} / {LIMIT} pinned public sources. SOURCE ONLY.")
        for idx, identifier in enumerate(current, 1):
            print(f"{idx:2}. {ids[identifier]['name']} [{identifier}]  VIEW SOURCE: {ids[identifier]['repository']}")
    elif args.command in ("pin", "unpin", "move"):
        if args.id not in ids:
            raise ValueError("Only IDs in the reviewed public snapshot may be pinned")
        if args.command == "pin":
            if args.id not in current:
                current.append(args.id)
            validate_pins(current, ids)
        elif args.command == "unpin":
            current = [value for value in current if value != args.id]
        elif args.id in current:
            index = current.index(args.id)
            other = max(0, min(len(current) - 1, index + (-1 if args.direction == "up" else 1)))
            current.pop(index)
            current.insert(other, args.id)
        _write_atomic(args.shelf, _serialize(current))
        print(f"Shelf updated: {len(current)} source bookmarks; no application actions granted")
    elif args.command == "export":
        output = args.output
        if output.is_symlink() or output.exists():
            raise ValueError("Export destination exists; choose a new filename")
        if not output.parent.is_dir():
            raise ValueError("Export destination directory missing")
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_serialize(current))
        print("Portable shelf copied. Bookmarks only, no credentials or installed app state.")
    elif args.command == "import":
        if not args.confirm_replace:
            raise ValueError("Import requires --confirm-replace (export your previous shelf first)")
        proposed = decode_shelf(_read_json(args.input))
        _write_atomic(args.shelf, _serialize(proposed))
        print(f"Replaced selected local shelf with {len(proposed)} source bookmarks; no installs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
