"""Read-only PhiARK R0.6 integration observation. Never grants install/launch authority."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

SCHEMA = "phios.phiark_observation.v0.1"
SHA = re.compile(r"^[a-f0-9]{64}$")
KIWIX = {
    "firstaid-medicine": "wikipedia_en_medicine_mini_2026-10.zim",
    "chemistry": "wikipedia_en_chemistry_mini_2026-10.zim",
    "physics": "wikipedia_en_physics_mini_2026-10.zim",
    "climate": "wikipedia_en_climate-change_mini_2026-10.zim",
    "mathematics": "wikipedia_en_mathematics_mini_2026-06.zim",
    "knots": "wikipedia_en_knots_maxi_2026-10.zim",
}

def _regular(path: Path, limit: int) -> int:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= limit:
        raise ValueError("file is not a bounded, regular non-symlink file")
    return info.st_size

def _directory(path: Path) -> None:
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError("path is not a real non-symlink directory")

def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        for part in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()

def _json(path: Path, limit: int) -> Any:
    _regular(path, limit)
    return json.loads(path.read_text(encoding="utf-8"))

def _documents(root: Path) -> dict[str, Any]:
    catalog_path = root / "catalog.json"
    try:
        catalog = _json(catalog_path, 2 * 1024 * 1024)
    except FileNotFoundError:
        return {"status": "CATALOG_ABSENT", "documents": 0, "hash_verified": 0, "failed": 0}
    if not isinstance(catalog, list) or len(catalog) > 1000:
        raise ValueError("catalog must be a bounded list")
    seen: set[str] = set()
    failures = 0
    passed = 0
    if catalog:
        _directory(root / "objects")
    for item in catalog:
        if not isinstance(item, dict):
            raise ValueError("invalid document metadata")
        digest, size = item.get("id"), item.get("bytes")
        if (not isinstance(digest, str) or not SHA.fullmatch(digest) or digest in seen or
                type(size) is not int or not 0 <= size <= 512 * 1024 * 1024):
            raise ValueError("invalid or duplicate document digest/size")
        seen.add(digest)
        try:
            doc = root / "objects" / digest
            if _regular(doc, 512 * 1024 * 1024) != size or _hash(doc) != digest:
                raise ValueError("document size/hash mismatch")
            passed += 1
        except (ValueError, OSError):
            failures += 1
    return {"status": "BYTES_INCOMPLETE" if failures else ("BYTES_MATCHED" if passed else "EMPTY"),
            "documents": len(catalog), "hash_verified": passed, "failed": failures,
            "content_approved": False}

def _archives(root: Path) -> dict[str, Any]:
    rows = []
    for selected, filename in KIWIX.items():
        folder = root / "kiwix" / "installed" / selected
        row = {"id": selected, "status": "NOT_INSTALLED"}
        try:
            _directory(folder)
            zim = folder / filename
            sha_file = folder / (filename + ".sha256")
            receipt = _json(folder / "receipt.json", 16384)
            bytes_seen = _regular(zim, 1024 * 1024 * 1024)
            _regular(sha_file, 4096)
            sidecar = sha_file.read_text(encoding="utf-8").strip()
            match = re.fullmatch(r"([0-9a-fA-F]{64})(?:[ \t]+\*?([^\s]+))?", sidecar)
            if not match or (match.group(2) and match.group(2) != filename):
                raise ValueError("invalid checksum sidecar")
            if (not isinstance(receipt, dict) or receipt.get("schema") != "phiark-kiwix-intake-v1" or
                    receipt.get("id") != selected or receipt.get("filename") != filename or
                    receipt.get("bytes") != bytes_seen or receipt.get("sha256") != match.group(1).lower()):
                raise ValueError("invalid receipt")
            if _hash(zim) != match.group(1).lower():
                raise ValueError("archive bytes do not match checksum")
            row["status"] = "CHECKSUM_MATCHED"
        except FileNotFoundError:
            try:
                folder.lstat()
                row["status"] = "FAIL"  # Partial installation is not NOT_INSTALLED.
            except FileNotFoundError:
                pass
        except (ValueError, OSError, UnicodeError, json.JSONDecodeError):
            row["status"] = "FAIL"
        rows.append(row)
    return {
        "status": "SCANNED_NOT_APPROVED", "items": rows,
        "checksum_matched": sum(x["status"] == "CHECKSUM_MATCHED" for x in rows),
        "failed": sum(x["status"] == "FAIL" for x in rows),
        "content_approved": False, "rights_approved": False,
    }

def _probe(port: int) -> dict[str, Any]:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("loopback port must be 1024..65535")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.5)
    try:
        connection.request("GET", "/api/status", headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            return {"status": "NO_VALID_STATUS"}
        payload = response.read(8193)
        if len(payload) > 8192:
            return {"status": "NO_VALID_STATUS"}
        data = json.loads(payload)
        if (not isinstance(data, dict) or data.get("mode") != "LOCAL" or
                data.get("networkRequired") is not False or type(data.get("documents")) is not int or
                data["documents"] < 0):
            return {"status": "NO_VALID_STATUS"}
        return {"status": "LOCAL_HTTP_OBSERVED", "reported_documents": data["documents"],
                "process_identity_attested": False}
    except (OSError, ValueError, json.JSONDecodeError):
        return {"status": "UNAVAILABLE"}
    finally:
        connection.close()

def observe_phiark(data_root: str | Path, *, verify_kiwix: bool = False,
                   probe_loopback: bool = False, port: int = 3691) -> dict[str, Any]:
    if not isinstance(data_root, (str, Path)) or not str(data_root).strip():
        raise ValueError("explicit data root required")
    expanded = Path(data_root).expanduser()
    if not expanded.is_absolute():
        raise ValueError("data root must be an absolute path")
    root = Path(os.path.abspath(expanded))
    # No symlink may redirect any component of the caller's data root.
    for parent in (root, *root.parents):
        try:
            if stat.S_ISLNK(parent.lstat().st_mode):
                raise ValueError("symlink in data root path")
        except FileNotFoundError:
            pass
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "app_id": "phi.phiark",
        "source_repository": "https://github.com/MichaelWave369/PhiARK",
        "status": "BLOCKED",
        "data_root": str(root),
        "catalog": {"status": "NOT_SCANNED", "documents": 0, "hash_verified": 0, "failed": 0},
        "kiwix": {"status": "NOT_SCANNED", "checksum_matched": 0, "failed": 0},
        "loopback": {"status": "NOT_PROBED", "process_identity_attested": False},
        "issues": [],
        "source_commit_attested": False,
        "install_authority": False, "launch_authority": False,
        "network_authority": False, "data_mutation_authority": False,
        "content_review_verified": False, "license_review_verified": False,
    }
    try:
        _directory(root)
        result["catalog"] = _documents(root)
        if verify_kiwix:
            result["kiwix"] = _archives(root)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        result["issues"].append("LOCAL_DATA_INVALID:" + type(exc).__name__)
    if probe_loopback:
        result["loopback"] = _probe(port)
    if result["issues"] or result["catalog"]["failed"] or result["kiwix"]["failed"]:
        result["status"] = "BLOCKED"
    elif result["catalog"]["hash_verified"] or result["kiwix"]["checksum_matched"]:
        result["status"] = "LOCAL_BYTES_OBSERVED"
    else:
        result["status"] = "NOT_INSTALLED_OR_EMPTY"
    return result
