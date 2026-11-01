"""Strict, local, review-only consumer for PhiVine Rung 10 static DLL triage.

A PhiVine triage JSON document is untrusted observational data. This module
never accesses Windows binaries, Wine, the app registry, the network, or grants.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from typing import Any

PHIVINE_SCHEMA = "phivine.import_triage.v0.1"
REVIEW_SCHEMA = "phios.phivine_import_triage_review.v0.1"
MAX_BYTES = 65536
_FILENAME = re.compile(r"[A-Za-z0-9_.+ -]{1,255}\.exe\Z", re.IGNORECASE)
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_DLL = re.compile(r"[a-z0-9_.+-]{1,128}\Z")
_ALLOWED = {
    "graphics_apis": frozenset({
        "d3d8.dll", "d3d9.dll", "d3d10.dll", "d3d10_1.dll", "d3d11.dll",
        "d3d12.dll", "dxgi.dll", "ddraw.dll", "opengl32.dll", "vulkan-1.dll",
    }),
    "network_apis": frozenset({
        "wsock32.dll", "ws2_32.dll", "winhttp.dll", "wininet.dll", "dnsapi.dll",
    }),
    "managed_runtime_bootstrap": frozenset({"mscoree.dll", "coreclr.dll", "hostfxr.dll"}),
    "visual_cpp_runtime": frozenset({
        "msvcrt.dll", "ucrtbase.dll", "msvcr100.dll", "msvcr110.dll",
        "msvcr120.dll", "msvcp100.dll", "msvcp110.dll", "msvcp120.dll",
        "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
        "vcruntime140.dll", "vcruntime140_1.dll",
    }),
    "com_and_automation": frozenset({"ole32.dll", "oleaut32.dll", "combase.dll"}),
    "windows_ui": frozenset({"user32.dll", "gdi32.dll", "comctl32.dll", "shell32.dll"}),
}
_ALLOWED_ORDER = tuple(_ALLOWED)
_FALSE = (
    "dependency_availability_verified", "wine_compatibility_verified",
    "origin_attested", "source_immutable", "sandbox_verified",
    "operator_approval_granted", "effect_lease_issued", "execution_authorized",
    "windows_execution_attempted", "wine_executed",
)
_OTHER = (
    "delayed_imports", "dynamic_library_loading", "imported_symbols_and_ordinals",
    "manifests_and_side_by_side", "managed_assemblies", "external_installer_effects",
)
_FIELDS = frozenset({
    "schema", "source_schema", "status", "name", "source_sha256_observed",
    "source_size_bytes_observed", "architecture_observed",
    "static_parser_status", "direct_import_dll_count", "review_areas",
    "unclassified_direct_imports", "import_scope",
    "other_dependencies_not_scanned", "note",
    *_FALSE,
})


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("Repeated JSON keys are not valid review evidence")
        out[key] = value
    return out


def read_phivine_triage_json(path: str | Path) -> Any:
    """Read at most 64 KiB from one no-follow regular local file descriptor."""
    source = Path(path).expanduser()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise ValueError("Unable to read PhiVine triage input") from exc
    with os.fdopen(fd, "rb") as handle:
        meta = os.fstat(handle.fileno())
        if not stat.S_ISREG(meta.st_mode) or not 1 <= meta.st_size <= MAX_BYTES:
            raise ValueError("PhiVine triage JSON must be a bounded regular file")
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("PhiVine triage exceeds 64 KiB")
    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid or duplicate-key PhiVine triage JSON") from exc


def _valid(p: Any) -> bool:
    if not isinstance(p, dict) or set(p) != _FIELDS:
        return False
    if p["schema"] != PHIVINE_SCHEMA or p["source_schema"] != "phivine.pe_imports.v0.1":
        return False
    if any(p[key] is not False for key in _FALSE):
        return False
    if p["import_scope"] != "DIRECT_IMPORT_DIRECTORY_ONLY":
        return False
    if p["other_dependencies_not_scanned"] != list(_OTHER):
        return False
    if not isinstance(p["note"], str) or len(p["note"]) > 300:
        return False
    if type(p["name"]) is not str or not _FILENAME.fullmatch(p["name"]):
        return False
    if type(p["source_sha256_observed"]) is not str or not _SHA.fullmatch(
        p["source_sha256_observed"]
    ):
        return False
    size = p["source_size_bytes_observed"]
    count = p["direct_import_dll_count"]
    if type(size) is not int or not 1 <= size <= 512 * 1024 * 1024:
        return False
    if type(count) is not int or not 0 <= count <= 128:
        return False
    if p["architecture_observed"] not in (None, "x86", "x86_64"):
        return False
    parser_status = p["static_parser_status"]
    if parser_status == "OBSERVED_IMPORT_NAMES_REVIEW_ONLY":
        if p["status"] != "HELD_STATIC_IMPORT_TRIAGE_REVIEW_ONLY" or count < 1:
            return False
        if p["architecture_observed"] not in ("x86", "x86_64"):
            return False
    elif parser_status in ("HELD_NO_IMPORT_TABLE_OBSERVED", "HELD_MALFORMED_OR_UNSUPPORTED_PE"):
        if p["status"] != "HELD_STATIC_INPUT_INSUFFICIENT" or count != 0:
            return False
    else:
        return False
    areas = p["review_areas"]
    unknown = p["unclassified_direct_imports"]
    if not isinstance(areas, list) or len(areas) > len(_ALLOWED):
        return False
    if not isinstance(unknown, list) or len(unknown) > 128:
        return False
    if any(type(n) is not str or not _DLL.fullmatch(n) for n in unknown):
        return False
    if sorted(set(unknown)) != unknown:
        return False
    seen: set[str] = set(unknown)
    categories: list[str] = []
    matched: dict[str, set[str]] = {}
    for item in areas:
        if not isinstance(item, dict) or set(item) != {
            "area", "dll_names_observed", "review_prompt",
            "capability_or_dependency_availability_verified",
        }:
            return False
        area = item["area"]
        if type(area) is not str or area not in _ALLOWED or area in categories:
            return False
        categories.append(area)
        if item["capability_or_dependency_availability_verified"] is not False:
            return False
        prompt = item["review_prompt"]
        if type(prompt) is not str or not 1 <= len(prompt) <= 300:
            return False
        names = item["dll_names_observed"]
        if (not isinstance(names, list) or not names
                or len(names) > 128 or any(type(n) is not str or n not in _ALLOWED[area] for n in names)):
            return False
        if sorted(set(names)) != names or any(n in seen for n in names):
            return False
        seen.update(names)
        matched[area] = set(names)
    if len(seen) != count:
        return False
    if categories != [name for name in _ALLOWED_ORDER if name in categories]:
        return False
    # A producer is not allowed to invent classifications OR conceal a name
    # that belongs to a known group by placing it among the unclassified.
    if any(n in known for n in unknown for known in _ALLOWED.values()):
        return False
    if count == 0 and (areas or unknown):
        return False
    return True


def review_phivine_triage(payload: Any) -> dict[str, Any]:
    """Display bounded untrusted categories, never infer or grant authority."""
    valid = _valid(payload)
    groups = (
        [
            {
                "area": item["area"],
                "dll_names_observed": item["dll_names_observed"],
                "review_only": True,
            }
            for item in payload["review_areas"]
        ] if valid else []
    )
    return {
        "schema": REVIEW_SCHEMA,
        "status": "HELD_STATIC_DLL_REVIEW_UNTRUSTED" if valid
                  else "HELD_INVALID_OR_UNTRUSTED_STATIC_TRIAGE",
        "source_schema": PHIVINE_SCHEMA,
        "input_kind": "untrusted_static_dll_import_review",
        "artifact_name_observed": payload["name"] if valid else None,
        "artifact_sha256_observed": payload["source_sha256_observed"] if valid else None,
        "source_immutability_verified": False,
        "review_groups": groups,
        "unclassified_direct_imports": payload["unclassified_direct_imports"] if valid else [],
        "other_dependencies_not_scanned": list(_OTHER),
        "source_repo_profiler_called": False,
        "binary_file_read_by_phios": False,
        "wine_compatibility_verified": False,
        "network_granted": False,
        "app_registry_read_or_modified": False,
        "phios_install_or_launch_called": False,
        "operator_approval_minted": False,
        "effect_lease_issued": False,
        "execution_authorized": False,
        "windows_binary_executed": False,
        "note": "Static names are untrusted evidence, not application compatibility or authority.",
    }
