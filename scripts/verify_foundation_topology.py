"""Read-only validator for the proposed PhiOS foundation topology.
No network, imports from PhiKernel, package installs, file writes or execution rights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "phishell/src/ecosystem/foundation-topology.v0.1.json"
SCHEMA = "phios.foundation_topology.v0.1"
PROVENANCE = "SOURCE_REVIEW_AND_ARCHITECTURE_PROPOSAL_ONLY"
OWNER_ROOT = "https://github.com/MichaelWave369/"
ROLES = {
    "os_shell", "governance_runtime", "ai_home", "commons", "bridge_lab",
    "package_manager", "cognitive_ui", "model_service", "resource_policy",
    "weight_engine_lab", "portable_ai_client", "council_app",
    "creative_source", "animation_editor", "media_finishing", "game_runtime",
}
KINDS = {
    "governance_contract", "ai_home_adapter", "world_portal", "governed_interop",
    "staged_package_bridge", "app_candidate", "model_service_adapter",
    "budget_advisory", "weight_execution_adapter", "portable_client_adapter",
    "glb_animation_handoff", "rendered_media_handoff", "bridged_game_runtime",
}
LINK_STATUSES = {"DOCUMENTED", "PROPOSED", "STAGED_UNQUALIFIED"}
NODE_KEYS = {
    "id", "repository_url", "role", "assessment", "installed_in_phios",
    "launch_authorized", "model_execution_authorized",
    "redistribution_approved", "note",
}
LINK_KEYS = {"from", "to", "kind", "status", "evidence_url", "note"}
AUTHORITY_KEYS = {
    "install", "launch", "model_execute", "network_connect",
    "grant", "publish", "native_boot",
}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 350:
        raise ValueError(f"{label} must be bounded non-empty text")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains a control character")
    return value


def validate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "snapshot_date", "provenance", "authority", "nodes", "links"
    }:
        raise ValueError("invalid foundation envelope")
    if payload["schema_version"] != SCHEMA or payload["provenance"] != PROVENANCE:
        raise ValueError("unknown topology schema or authority/provenance label")
    if payload["snapshot_date"] != "2026-10-24":
        raise ValueError("snapshot changes need a separately reviewed revision")
    authority = payload["authority"]
    if not isinstance(authority, dict) or set(authority) != AUTHORITY_KEYS:
        raise ValueError("invalid authority keys")
    if any(value is not False for value in authority.values()):
        raise ValueError("a topology cannot grant any runtime authority")

    nodes = payload["nodes"]
    links = payload["links"]
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 32:
        raise ValueError("invalid bounded node inventory")
    if not isinstance(links, list) or not 1 <= len(links) <= 64:
        raise ValueError("invalid bounded relationship inventory")
    known: dict[str, str] = {}
    for item in nodes:
        if not isinstance(item, dict) or set(item) != NODE_KEYS:
            raise ValueError("unexpected topology node fields")
        name = _text(item["id"], "node ID")
        if not name.replace("-", "").isalnum() or name in known:
            raise ValueError("duplicate or unsafe node identifier")
        if item["repository_url"] != OWNER_ROOT + name:
            raise ValueError("node repository URL/identity mismatch")
        role = _text(item["role"], "node role")
        if role not in ROLES:
            raise ValueError("unsupported role")
        if item["assessment"] != "SOURCE_REVIEW_ONLY":
            raise ValueError("topology cannot promote readiness")
        for flag in (
            "installed_in_phios", "launch_authorized",
            "model_execution_authorized", "redistribution_approved"
        ):
            if item[flag] is not False:
                raise ValueError(f"unsupported promotion: {name}.{flag}")
        _text(item["note"], "node note")
        known[name] = role
    if known.get("PhiOS") != "os_shell" or known.get("PhiKernel") != "governance_runtime":
        raise ValueError("foundation owners missing or reassigned")

    seen: set[tuple[str, str, str]] = set()
    for edge in links:
        if not isinstance(edge, dict) or set(edge) != LINK_KEYS:
            raise ValueError("unexpected topology link fields")
        src = _text(edge["from"], "link source")
        dst = _text(edge["to"], "link destination")
        kind = _text(edge["kind"], "link kind")
        if src not in known or dst not in known or src == dst or kind not in KINDS:
            raise ValueError("invalid link endpoints or kind")
        key = (src, dst, kind)
        if key in seen:
            raise ValueError("duplicate link")
        seen.add(key)
        if edge["status"] not in LINK_STATUSES:
            raise ValueError("unsupported relationship status")
        url = _text(edge["evidence_url"], "link evidence")
        if not url.startswith(OWNER_ROOT) or "/blob/" not in url:
            raise ValueError("link evidence must be a repository file URL")
        _text(edge["note"], "link note")
    return {"schema_version": SCHEMA, "node_count": len(nodes), "link_count": len(links),
            "all_runtime_authority_denied": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate offline PhiOS foundation topology")
    parser.add_argument("--check", action="store_true", help="validate only; never modify data")
    args = parser.parse_args()
    if TOPOLOGY.is_symlink() or not TOPOLOGY.is_file() or TOPOLOGY.stat().st_size > 256_000:
        raise ValueError("missing, symlinked or oversized topology file")
    data = TOPOLOGY.read_bytes()
    summary = validate(json.loads(data.decode("utf-8")))
    summary["sha256"] = hashlib.sha256(data).hexdigest()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
