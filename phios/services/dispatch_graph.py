"""Experimental deterministic dispatch-graph optimization service."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from phios.core.constants import BIO_VACUUM_TARGET, C_STAR_THEORETICAL, HUNTER_C_STATUS


DispatchNode = dict[str, object]
DispatchGraph = dict[str, object]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _last_plan_path() -> Path:
    return Path.home() / ".phios" / "agents" / "dispatch_graph_last.json"


def normalize_dispatch_graph(graph: DispatchGraph | dict[str, object]) -> DispatchGraph:
    nodes_obj = graph.get("nodes", []) if isinstance(graph, dict) else []
    nodes = nodes_obj if isinstance(nodes_obj, list) else []
    out_nodes: list[DispatchNode] = []

    for idx, raw in enumerate(nodes):
        item = raw if isinstance(raw, dict) else {}
        node_id = str(item.get("id", f"n{idx+1}"))
        deps_obj = item.get("dependencies", [])
        deps = [str(dep) for dep in deps_obj if isinstance(dep, str)] if isinstance(deps_obj, list) else []
        skills_obj = item.get("skills", [])
        skills = [str(skill).strip().lower() for skill in skills_obj if str(skill).strip()] if isinstance(skills_obj, list) else []
        atom_obj = item.get("atom_overrides", {})
        atom_overrides = atom_obj if isinstance(atom_obj, dict) else {}

        out_nodes.append(
            {
                "id": node_id,
                "label": str(item.get("label", node_id)),
                "dependencies": deps,
                "estimated_cost": _as_float(item.get("estimated_cost"), 1.0),
                "sector": str(item.get("sector", "")) or None,
                "skills": skills,
                "figure": (str(item.get("figure", "")).strip() or None),
                "atom_overrides": atom_overrides,
                "priority": _as_int(item.get("priority"), 0),
            }
        )

    return {
        "nodes": out_nodes,
        "generated_at": _utc_now_iso(),
        "experimental": True,
    }


def validate_dispatch_graph(graph: DispatchGraph) -> dict[str, object]:
    nodes_obj = graph.get("nodes", [])
    nodes = nodes_obj if isinstance(nodes_obj, list) else []
    ids = [str(n.get("id", "")) for n in nodes if isinstance(n, dict)]
    id_set = set(ids)

    duplicates = sorted([node_id for node_id in id_set if ids.count(node_id) > 1])
    missing_deps: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        deps_obj = node.get("dependencies", [])
        deps = deps_obj if isinstance(deps_obj, list) else []
        for dep in deps:
            dep_id = str(dep)
            if dep_id not in id_set:
                missing_deps.append(f"{node_id}->{dep_id}")

    indegree: dict[str, int] = {node_id: 0 for node_id in id_set}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        deps_obj = node.get("dependencies", [])
        deps = deps_obj if isinstance(deps_obj, list) else []
        for dep in deps:
            dep_id = str(dep)
            if dep_id in id_set and node_id in id_set:
                indegree[node_id] += 1
                outgoing[dep_id].append(node_id)

    q = deque(sorted([node_id for node_id, deg in indegree.items() if deg == 0]))
    visited = 0
    while q:
        current = q.popleft()
        visited += 1
        for nxt in sorted(outgoing.get(current, [])):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)

    has_cycle = visited != len(id_set)
    return {
        "ok": len(duplicates) == 0 and len(missing_deps) == 0 and not has_cycle,
        "duplicates": duplicates,
        "missing_dependencies": sorted(missing_deps),
        "has_cycle": has_cycle,
    }


def build_dispatch_graph_context(graph: DispatchGraph) -> dict[str, object]:
    nodes_obj = graph.get("nodes", [])
    nodes = [n for n in nodes_obj if isinstance(n, dict)] if isinstance(nodes_obj, list) else []
    sectors = sorted({str(n.get("sector", "")) for n in nodes if n.get("sector")})
    figures = sorted({str(n.get("figure", "")) for n in nodes if n.get("figure")})
    return {
        "generated_at": _utc_now_iso(),
        "nodes_count": len(nodes),
        "sectors": sectors,
        "figures": figures,
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
    }


def _compute_depths(nodes: list[DispatchNode]) -> dict[str, int]:
    by_id = {str(n.get("id", "")): n for n in nodes}
    memo: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        node = by_id.get(node_id, {})
        deps_obj = node.get("dependencies", []) if isinstance(node, dict) else []
        deps = [str(d) for d in deps_obj] if isinstance(deps_obj, list) else []
        if not deps:
            memo[node_id] = 0
            return 0
        value = 1 + max(depth(dep) for dep in deps if dep in by_id)
        memo[node_id] = value
        return value

    for node_id in by_id:
        depth(node_id)
    return memo


def build_dispatch_waves(ordered_nodes: list[str], graph: DispatchGraph) -> list[list[str]]:
    nodes_obj = graph.get("nodes", [])
    nodes = nodes_obj if isinstance(nodes_obj, list) else []
    by_id: dict[str, DispatchNode] = {
        str(node.get("id", "")): node
        for node in nodes
        if isinstance(node, dict)
    }
    done: set[str] = set()
    remaining = list(ordered_nodes)
    waves: list[list[str]] = []

    def deps_for(node_id: str) -> list[str]:
        node = by_id.get(node_id)
        if not isinstance(node, dict):
            return []
        deps_obj = node.get("dependencies", [])
        deps = deps_obj if isinstance(deps_obj, list) else []
        return [str(dep) for dep in deps]

    while remaining:
        wave = [
            node_id
            for node_id in remaining
            if all(str(dep) in done for dep in deps_for(node_id))
        ]
        if not wave:
            break
        waves.append(wave)
        done.update(wave)
        remaining = [node_id for node_id in remaining if node_id not in done]

    if remaining:
        waves.append(remaining)
    return waves


def optimize_dispatch_graph(graph: DispatchGraph | dict[str, object]) -> dict[str, object]:
    normalized = normalize_dispatch_graph(graph)
    validation = validate_dispatch_graph(normalized)
    if not validation.get("ok"):
        unresolved = validation.get("missing_dependencies", []) if isinstance(validation.get("missing_dependencies"), list) else []
        return {
            "ok": False,
            "error_code": "INVALID_GRAPH",
            "reason": "Dispatch graph failed validation.",
            "unresolved_dependencies": unresolved,
            "validation": validation,
            "experimental": True,
        }

    nodes_obj = normalized.get("nodes", [])
    nodes = [node for node in nodes_obj if isinstance(node, dict)] if isinstance(nodes_obj, list) else []
    by_id = {str(node.get("id", "")): node for node in nodes}

    indegree: dict[str, int] = {node_id: 0 for node_id in by_id}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        node_id = str(node.get("id", ""))
        deps_obj = node.get("dependencies", [])
        deps = deps_obj if isinstance(deps_obj, list) else []
        for dep in deps:
            dep_id = str(dep)
            indegree[node_id] += 1
            outgoing[dep_id].append(node_id)

    depths = _compute_depths(nodes)

    def score(node_id: str) -> tuple[float, float, float, str]:
        node = by_id.get(node_id, {})
        priority = _as_float(node.get("priority"), 0.0)
        cost = _as_float(node.get("estimated_cost"), 1.0)
        depth = float(depths.get(node_id, 0))
        # deterministic scoring: prioritize deeper dependencies, then explicit priority, then lower cost, then lexical id
        return (-depth, -priority, cost, node_id)

    ready = [node_id for node_id, deg in indegree.items() if deg == 0]
    ready.sort(key=score)
    ordered: list[str] = []

    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for nxt in sorted(outgoing.get(current, [])):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=score)

    waves = build_dispatch_waves(ordered, normalized)

    fanout_scores = {
        node_id: len(outgoing.get(node_id, []))
        for node_id in by_id
    }
    bottlenecks = [node_id for node_id, out_count in sorted(fanout_scores.items(), key=lambda kv: (-kv[1], kv[0])) if out_count >= 2]

    max_depth = max(depths.values()) if depths else 0
    avg_wave = (sum(len(w) for w in waves) / len(waves)) if waves else 0.0
    graph_score = max(0.0, min(1.0, 0.55 + 0.1 * min(max_depth, 3) + 0.05 * min(avg_wave, 4)))

    reasons = [
        "Dependency correctness enforced via deterministic topological ordering.",
        "Ready queue is ranked by depth(desc), priority(desc), estimated_cost(asc), id(asc).",
        "Parallel waves group nodes whose dependencies are satisfied at each boundary.",
    ]

    result = {
        "ok": True,
        "ordered_nodes": ordered,
        "dispatch_waves": waves,
        "bottlenecks": bottlenecks,
        "unresolved_dependencies": [],
        "graph_score": round(graph_score, 6),
        "reasons": reasons,
        "context": build_dispatch_graph_context(normalized),
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
        "generated_at": _utc_now_iso(),
        "graph": normalized,
    }

    path = _last_plan_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def summarize_dispatch_graph_plan(plan: dict[str, object]) -> dict[str, object]:
    waves_obj = plan.get("dispatch_waves", [])
    waves = waves_obj if isinstance(waves_obj, list) else []
    ordered_obj = plan.get("ordered_nodes", [])
    ordered = ordered_obj if isinstance(ordered_obj, list) else []

    return {
        "ok": bool(plan.get("ok", False)),
        "nodes": len(ordered),
        "waves": len(waves),
        "max_wave_width": max((len(w) for w in waves if isinstance(w, list)), default=0),
        "bottlenecks": plan.get("bottlenecks", []),
        "graph_score": plan.get("graph_score", 0.0),
        "experimental": True,
        "generated_at": _utc_now_iso(),
    }


def read_last_dispatch_graph_plan() -> dict[str, object]:
    path = _last_plan_path()
    if not path.exists():
        return {
            "ok": True,
            "found": False,
            "reason": "No dispatch graph optimization has been recorded yet.",
            "generated_at": _utc_now_iso(),
            "experimental": True,
        }
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return {"ok": True, "found": True, **parsed}
    except Exception:
        pass
    return {
        "ok": False,
        "found": False,
        "error_code": "INVALID_LAST_PLAN",
        "reason": "Stored dispatch graph plan is unreadable.",
        "generated_at": _utc_now_iso(),
        "experimental": True,
    }
