"""Agent dispatch orchestration service for experimental AgentCeption integration."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import build_coherence_report, build_status_report
from phios.services.visualizer import (
    VisualizerError,
    add_visual_bloom_storyboard_section,
    create_visual_bloom_storyboard,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agents_root() -> Path:
    return Path.home() / ".phios" / "agents"


def _runs_dir() -> Path:
    root = _agents_root() / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.json"


def _events_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.events.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_event(run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    events = stream_agent_run_events(run_id)
    events.append(
        {
            "event_id": f"evt_{len(events)+1:04d}",
            "run_id": run_id,
            "event_type": event_type,
            "generated_at": _utc_now_iso(),
            "payload": payload or {},
        }
    )
    _write_json(_events_path(run_id), events)


def _agentception_enabled() -> bool:
    raw = os.getenv("PHIOS_AGENTCEPTION_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}


def _agentception_base_url() -> str:
    return os.getenv("PHIOS_AGENTCEPTION_BASE_URL", "http://127.0.0.1:8787").strip().rstrip("/")


def _agentception_token() -> str | None:
    token = os.getenv("PHIOS_AGENTCEPTION_TOKEN")
    if not token:
        return None
    token = token.strip()
    return token or None


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_s: float = 10.0,
) -> tuple[bool, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    token = _agentception_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return True, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        return False, {"http_status": exc.code, "error": body or str(exc)}
    except Exception as exc:
        return False, {"error": str(exc)}


def build_dispatch_context(
    *,
    task: str,
    adapter: PhiKernelCLIAdapter,
    field_guided: bool,
    arch: str | None,
    review_panel: bool,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "task": task,
        "generated_at": _utc_now_iso(),
        "orchestrator": "phios",
        "experimental": True,
        "arch": arch or "default",
        "review_panel": review_panel,
        "framing": {
            "c_star_theoretical": True,
            "bio_vacuum_target_experimental": True,
            "hunters_c_unconfirmed": True,
        },
        "status": build_status_report(adapter),
    }
    if field_guided:
        context["field_state"] = build_coherence_report(adapter)
    return context


def run_agentception_plan(*, task: str, context: dict[str, Any]) -> dict[str, Any]:
    if not _agentception_enabled():
        return {
            "source": "local-fallback",
            "planner_available": False,
            "plan_steps": [
                {"step": "decompose task", "status": "pending"},
                {"step": "assign specialist agents", "status": "pending"},
                {"step": "collect review artifacts", "status": "pending"},
            ],
            "task": task,
            "context_summary": {
                "field_guided": "field_state" in context,
                "arch": context.get("arch", "default"),
            },
        }

    ok, payload = _http_json(
        f"{_agentception_base_url()}/planner/plan",
        method="POST",
        payload={"task": task, "context": context},
    )
    if not ok:
        return {
            "source": "local-fallback",
            "planner_available": False,
            "plan_steps": [{"step": "planner unavailable", "status": "blocked", "error": payload}],
            "task": task,
        }

    plan_steps_obj = payload.get("plan_steps")
    plan_steps = plan_steps_obj if isinstance(plan_steps_obj, list) else []
    return {
        "source": "agentception",
        "planner_available": True,
        "task": task,
        "plan_id": payload.get("plan_id", ""),
        "plan_steps": plan_steps,
        "raw": payload,
    }


def dispatch_agentception_run(
    *,
    task: str,
    context: dict[str, Any],
    plan: dict[str, Any],
    stream: bool,
) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    remote_run_id = ""
    remote_status = "not_attempted"

    if _agentception_enabled():
        ok, payload = _http_json(
            f"{_agentception_base_url()}/dispatch/runs",
            method="POST",
            payload={"task": task, "context": context, "plan": plan, "stream": stream},
        )
        if ok:
            remote_run_id = str(payload.get("run_id", ""))
            remote_status = str(payload.get("status", "running"))
        else:
            remote_status = "degraded_local_tracking"
            _append_event(run_id, "remote_dispatch_error", {"error": payload})

    record: dict[str, Any] = {
        "run_id": run_id,
        "task": task,
        "status": "running",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "stream_requested": stream,
        "remote_run_id": remote_run_id,
        "remote_status": remote_status,
        "context": context,
        "plan": plan,
        "outcome": "pending",
    }
    _write_json(_run_path(run_id), record)
    _append_event(run_id, "dispatch_created", {"task": task, "remote_status": remote_status})
    return record


def list_agent_runs(*, active_only: bool = False) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in sorted(_runs_dir().glob("run_*.json"), reverse=True):
        run = _read_json(path, {})
        if not isinstance(run, dict):
            continue
        if active_only and str(run.get("status", "")).lower() in {"completed", "cancelled", "failed"}:
            continue
        runs.append(run)
    runs.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return runs


def get_agent_run_status(run_id: str) -> dict[str, Any]:
    run = _read_json(_run_path(run_id), {})
    if not isinstance(run, dict) or not run:
        return {"ok": False, "run_id": run_id, "error": "run_not_found"}
    run["events_count"] = len(stream_agent_run_events(run_id))
    return run


def cancel_agent_run(run_id: str) -> dict[str, Any]:
    run = _read_json(_run_path(run_id), {})
    if not isinstance(run, dict) or not run:
        return {"ok": False, "run_id": run_id, "error": "run_not_found"}

    if _agentception_enabled() and run.get("remote_run_id"):
        ok, payload = _http_json(
            f"{_agentception_base_url()}/dispatch/runs/{run['remote_run_id']}/cancel",
            method="POST",
            payload={"reason": "operator_cancelled"},
        )
        _append_event(run_id, "remote_cancel_attempt", {"ok": ok, "payload": payload})

    run["status"] = "cancelled"
    run["updated_at"] = _utc_now_iso()
    run["outcome"] = "cancelled_by_operator"
    _write_json(_run_path(run_id), run)
    _append_event(run_id, "run_cancelled", {"run_id": run_id})
    return {"ok": True, "run_id": run_id, "status": "cancelled"}


def stream_agent_run_events(run_id: str) -> list[dict[str, Any]]:
    events = _read_json(_events_path(run_id), [])
    if not isinstance(events, list):
        return []
    out: list[dict[str, Any]] = []
    for item in events:
        if isinstance(item, dict):
            out.append(item)
    return out


def persist_dispatch_storyboard(
    *,
    run: dict[str, Any],
    plan: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    run_id = str(run.get("run_id", "dispatch"))
    storyboard_name = f"dispatch_{run_id}"
    payload = {
        "field_state_at_dispatch": run.get("context", {}).get("field_state"),
        "plan_spec": plan,
        "run_metadata": {
            "run_id": run.get("run_id", ""),
            "created_at": run.get("created_at", ""),
            "remote_run_id": run.get("remote_run_id", ""),
            "remote_status": run.get("remote_status", ""),
        },
        "agent_events_summary": {
            "event_count": len(events),
            "latest_event": events[-1] if events else None,
        },
        "outcome_status": run.get("status", "unknown"),
    }

    try:
        create_visual_bloom_storyboard(
            name=storyboard_name,
            title=f"Agent dispatch {run_id}",
            summary="Experimental AgentCeption dispatch narrative.",
            tags=["dispatch", "agentception", "experimental"],
        )
    except VisualizerError:
        # idempotent-friendly when rerun for same run_id
        pass

    add_visual_bloom_storyboard_section(
        name=storyboard_name,
        section_type="narrative",
        artifact_ref=f"phios://agents/{run_id}",
        title="Dispatch Narrative",
        summary="Field-guided dispatch context and run trace.",
        notes=json.dumps(payload, indent=2),
        tags=["dispatch", "agentception", "narrative"],
    )
    return {
        "ok": True,
        "storyboard_name": storyboard_name,
        "artifact_ref": f"phios://agents/{run_id}",
    }
