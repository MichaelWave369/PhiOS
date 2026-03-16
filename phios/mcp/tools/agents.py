"""MCP tools for experimental AgentCeption dispatch orchestration."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.policy import (
    CAP_AGENT_DISPATCH,
    CAP_AGENT_KILL,
    denied_capability_payload,
    is_capability_allowed,
)
from phios.mcp.schema import with_tool_schema
from phios.services.agent_dispatch import (
    build_dispatch_context,
    cancel_agent_run,
    dispatch_agentception_run,
    get_agent_run_status,
    list_agent_runs,
    persist_dispatch_storyboard,
    run_agentception_plan,
    stream_agent_run_events,
)


def run_phi_dispatch_agents(
    adapter: PhiKernelCLIAdapter,
    *,
    task: str,
    field_guided: bool = False,
    dry_run: bool = False,
    coherence_gate: float | None = None,
    arch: str | None = None,
    review_panel: bool = False,
    stream: bool = False,
) -> dict[str, object]:
    decision = is_capability_allowed(CAP_AGENT_DISPATCH)
    if not dry_run and not decision.allowed:
        return with_tool_schema(
            denied_capability_payload(decision=decision, error_code="AGENT_DISPATCH_NOT_PERMITTED")
        )

    context = build_dispatch_context(
        task=task,
        adapter=adapter,
        field_guided=field_guided,
        arch=arch,
        review_panel=review_panel,
    )

    if coherence_gate is not None and field_guided:
        field = context.get("field_state", {})
        current = field.get("C_current") if isinstance(field, dict) else None
        if isinstance(current, (int, float)) and float(current) < float(coherence_gate):
            return with_tool_schema(
                {
                    "ok": False,
                    "allowed": False,
                    "reason": f"Coherence gate not met: C_current={current:.3f} < {coherence_gate:.3f}",
                    "capability_scope": CAP_AGENT_DISPATCH,
                    "policy_source": decision.policy_source,
                    "error_code": "COHERENCE_GATE_BLOCKED",
                }
            )

    plan = run_agentception_plan(task=task, context=context)
    if dry_run:
        return with_tool_schema(
            {
                "ok": True,
                "allowed": True,
                "dry_run": True,
                "task": task,
                "context": context,
                "plan": plan,
            }
        )

    run = dispatch_agentception_run(task=task, context=context, plan=plan, stream=stream)
    events = stream_agent_run_events(str(run.get("run_id", "")))
    storyboard = persist_dispatch_storyboard(run=run, plan=plan, events=events)
    return with_tool_schema(
        {
            "ok": True,
            "allowed": True,
            "dry_run": False,
            "task": task,
            "run": run,
            "storyboard": storyboard,
        }
    )


def run_phi_list_agents() -> dict[str, object]:
    runs = list_agent_runs(active_only=False)
    return with_tool_schema({"ok": True, "runs": runs, "count": len(runs)})


def run_phi_agent_status(*, run_id: str) -> dict[str, object]:
    status = get_agent_run_status(run_id)
    if status.get("ok") is False:
        return with_tool_schema({"ok": False, "run_id": run_id, "error_code": "RUN_NOT_FOUND"})
    return with_tool_schema({"ok": True, "run": status})


def run_phi_kill_agent(*, run_id: str) -> dict[str, object]:
    decision = is_capability_allowed(CAP_AGENT_KILL)
    if not decision.allowed:
        return with_tool_schema(
            denied_capability_payload(decision=decision, error_code="AGENT_KILL_NOT_PERMITTED")
        )
    result = cancel_agent_run(run_id)
    if not result.get("ok"):
        return with_tool_schema({"ok": False, "run_id": run_id, "error_code": "RUN_NOT_FOUND"})
    return with_tool_schema({"ok": True, "result": result})
