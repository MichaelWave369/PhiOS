"""PhiVault R02: private, offline, single-snapshot conversation archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

MAX_BYTES = 256 * 1024 * 1024
SCHEMA = 1


class VaultError(ValueError):
    pass


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VaultError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_):
    raise VaultError("nonstandard JSON constant")


def project(raw):
    data = json.loads(raw, object_pairs_hook=unique_keys,
                      parse_constant=reject_constant)
    if not isinstance(data, list):
        raise VaultError("expected conversations JSON array")
    seen = set()
    rows = []
    for conv in data:
        if not isinstance(conv, dict):
            raise VaultError("invalid conversation")
        cid = conv.get("id") or conv.get("conversation_id")
        title = conv.get("title")
        mapping = conv.get("mapping")
        if (not isinstance(cid, str) or not cid or cid in seen
                or not isinstance(mapping, dict)):
            raise VaultError("missing or duplicate conversation identity or mapping")
        seen.add(cid)
        if not isinstance(title, str):
            title = ""
        for nid, node in mapping.items():
            if not isinstance(node, dict) or not nid:
                raise VaultError("invalid node")
            parent = node.get("parent")
            if parent is not None and not isinstance(parent, str):
                raise VaultError("invalid parent")
            msg = node.get("message")
            role, mid, created, body = "", None, None, ""
            if msg is not None:
                if not isinstance(msg, dict):
                    raise VaultError("invalid message")
                author = msg.get("author")
                if isinstance(author, dict) and isinstance(author.get("role"), str):
                    role = author["role"]
                mid = msg.get("id")
                if mid is not None and not isinstance(mid, str):
                    raise VaultError("invalid message identity")
                created = json.dumps(msg.get("create_time"), ensure_ascii=True)
                content = msg.get("content")
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list):
                        body = "\n".join(p for p in parts if isinstance(p, str))
                    elif isinstance(content.get("text"), str):
                        body = content["text"]
            # Every mapping node is represented, including hidden and alternate branches.
            rows.append((cid, nid, parent, mid, role, created, title, body,
                         (title + "\n" + body).casefold()))
    return sorted(rows, key=lambda row: (row[0], row[1]))


def private_destination(path):
    path = Path(path).resolve()
    if any((p / ".git").exists() for p in path.parents):
        raise VaultError("destination inside a Git checkout is forbidden")
    if not path.parent.is_dir():
        raise VaultError("create a private destination directory first")
    return path


def create_exclusive(path):
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)


def import_snapshot(source, target):
    target = private_destination(target)
    with Path(source).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise VaultError("source exceeds 256 MiB limit")
    rows = project(raw)
    digest = hashlib.sha256(raw).hexdigest()
    fd = create_exclusive(target)
    os.close(fd)
    try:
        with sqlite3.connect(target) as db:
            db.execute("CREATE TABLE snapshot (schema_version INTEGER NOT NULL, "
                       "sha256 TEXT NOT NULL, raw BLOB NOT NULL)")
            db.execute("CREATE TABLE nodes (cid TEXT NOT NULL, nid TEXT NOT NULL, "
                       "parent TEXT, mid TEXT, role TEXT NOT NULL, created TEXT, "
                       "title TEXT NOT NULL, body TEXT NOT NULL, folded TEXT NOT NULL, "
                       "PRIMARY KEY(cid, nid))")
            db.execute("INSERT INTO snapshot VALUES (?, ?, ?)", (SCHEMA, digest, raw))
            db.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        db.close()
    except BaseException:
        try:
            db.close()
        except UnboundLocalError:
            pass
        target.unlink(missing_ok=True)
        raise
    return {"schema": SCHEMA, "sha256": digest, "nodes": len(rows),
            "status": "IMPORTED_UNVERIFIED"}


def open_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def verified_raw(db):
    snapshots = db.execute("SELECT schema_version, sha256, raw FROM snapshot").fetchall()
    if len(snapshots) != 1:
        raise VaultError("expected exactly one snapshot")
    schema, digest, raw = snapshots[0]
    if (schema != SCHEMA or not isinstance(raw, bytes) or len(raw) > MAX_BYTES
            or hashlib.sha256(raw).hexdigest() != digest):
        raise VaultError("snapshot integrity failure")
    expected = project(raw)
    actual = db.execute("SELECT cid,nid,parent,mid,role,created,title,body,folded "
                        "FROM nodes ORDER BY cid,nid").fetchall()
    if actual != expected:
        raise VaultError("projection integrity failure")
    return raw, {"schema": schema, "sha256": digest, "nodes": len(expected),
                 "status": "INTEGRITY_VERIFIED"}


def verify(path):
    from contextlib import closing
    with closing(open_readonly(path)) as db:
        return verified_raw(db)[1]


def search(path, query, limit=20):
    from contextlib import closing
    if not query.strip() or len(query) > 1000 or not 1 <= limit <= 100:
        raise VaultError("invalid search query or limit")
    with closing(open_readonly(path)) as db:
        rows = db.execute("SELECT cid,nid,mid,role,title,body FROM nodes "
                          "WHERE instr(folded, ?) > 0 ORDER BY cid,nid LIMIT ?",
                          (query.casefold(), limit)).fetchall()
    results = []
    for cid, nid, mid, role, title, body in rows:
        # Keep the complete body in SQLite; return a bounded preview.
        # Casefold can expand characters, so this is an approximate excerpt offset.
        pos = max(0, body.casefold().find(query.casefold()) - 100)
        results.append({"conversation_id": cid, "node_id": nid, "message_id": mid,
                        "role": role, "title": title[:300], "preview": body[pos:pos+400]})
    return results


def restore(path, destination):
    from contextlib import closing
    destination = private_destination(destination)
    with closing(open_readonly(path)) as db:
        raw, receipt = verified_raw(db)
    fd = create_exclusive(destination)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return dict(receipt, status="RESTORED")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    imp = commands.add_parser("import")
    imp.add_argument("source")
    imp.add_argument("vault")
    ver = commands.add_parser("verify")
    ver.add_argument("vault")
    find = commands.add_parser("search")
    find.add_argument("vault")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=20)
    out = commands.add_parser("restore")
    out.add_argument("vault")
    out.add_argument("destination")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = import_snapshot(args.source, args.vault)
        elif args.command == "verify":
            result = verify(args.vault)
        elif args.command == "search":
            result = search(args.vault, args.query, args.limit)
        else:
            result = restore(args.vault, args.destination)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, RecursionError):
        # Do not leak source contents, private paths, or SQL error details.
        print("PhiVault operation failed; check format, paths, permissions and integrity.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
