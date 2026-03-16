"""PhiOS MCP server (Phase 1-4).

This module provides a stable stdio MCP server surface over existing PhiOS services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.prompts.field_guidance import build_field_guidance_prompt
from phios.mcp.resources.coherence_lt import read_coherence_lt_resource
from phios.mcp.resources.field_state import read_field_state_resource
from phios.mcp.resources.history import (
    read_recent_capsules_resource,
    read_recent_field_snapshots_resource,
    read_recent_sessions_resource,
)
from phios.mcp.resources.observatory import (
    read_observatory_atlas_gallery_resource,
    read_observatory_dashboard_resource,
    read_observatory_index_resource,
    read_observatory_recent_dossiers_resource,
    read_observatory_recent_field_libraries_resource,
    read_observatory_recent_storyboards_resource,
)
from phios.mcp.resources.status import read_system_status_resource
from phios.mcp.tools.ask import run_phi_ask
from phios.mcp.tools.observatory import (
    run_phi_library_summary,
    run_phi_observatory_summary,
    run_phi_recent_activity,
)
from phios.mcp.tools.pulse import run_phi_pulse_once
from phios.mcp.tools.status import run_phi_status


@dataclass(slots=True)
class McpSurfaceRegistry:
    """Simple registry metadata for tests/introspection and future client harnesses."""

    resources: tuple[str, ...]
    tools: tuple[str, ...]
    prompts: tuple[str, ...]


def mcp_surface_registry() -> McpSurfaceRegistry:
    return McpSurfaceRegistry(
        resources=(
            "phios://field/state",
            "phios://coherence/lt",
            "phios://system/status",
            "phios://history/recent_capsules",
            "phios://history/recent_sessions",
            "phios://history/recent_field_snapshots",
            "phios://observatory/index",
            "phios://observatory/dashboard",
            "phios://observatory/atlas_gallery",
            "phios://observatory/storyboards/recent",
            "phios://observatory/dossiers/recent",
            "phios://observatory/field_libraries/recent",
        ),
        tools=(
            "phi_status",
            "phi_ask",
            "phi_pulse_once",
            "phi_observatory_summary",
            "phi_recent_activity",
            "phi_library_summary",
        ),
        prompts=("field_guidance",),
    )


def phase1_registry() -> McpSurfaceRegistry:
    """Backward-compatible alias used by existing tests."""

    return mcp_surface_registry()


def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - exercised via server handlers
        raise RuntimeError(f"PhiOS MCP upstream call failed: {exc}") from exc


def create_mcp_server(adapter: PhiKernelCLIAdapter | None = None) -> Any:
    """Create and register the PhiOS stdio MCP server."""

    from mcp.server.fastmcp import FastMCP

    kernel_adapter = adapter or PhiKernelCLIAdapter()
    server = FastMCP("PhiOS")

    @server.resource("phios://field/state", mime_type="application/json")
    def resource_field_state() -> dict[str, object]:
        return _safe_call(read_field_state_resource, kernel_adapter)

    @server.resource("phios://coherence/lt", mime_type="application/json")
    def resource_coherence_lt() -> dict[str, object]:
        return _safe_call(read_coherence_lt_resource)

    @server.resource("phios://system/status", mime_type="application/json")
    def resource_system_status() -> dict[str, object]:
        return _safe_call(read_system_status_resource, kernel_adapter)

    @server.resource("phios://history/recent_capsules", mime_type="application/json")
    def resource_recent_capsules() -> dict[str, object]:
        return _safe_call(read_recent_capsules_resource, kernel_adapter)

    @server.resource("phios://history/recent_sessions", mime_type="application/json")
    def resource_recent_sessions() -> dict[str, object]:
        return _safe_call(read_recent_sessions_resource)

    @server.resource("phios://history/recent_field_snapshots", mime_type="application/json")
    def resource_recent_field_snapshots() -> dict[str, object]:
        return _safe_call(read_recent_field_snapshots_resource)

    @server.resource("phios://observatory/index", mime_type="application/json")
    def resource_observatory_index() -> dict[str, object]:
        return _safe_call(read_observatory_index_resource)

    @server.resource("phios://observatory/dashboard", mime_type="application/json")
    def resource_observatory_dashboard() -> dict[str, object]:
        return _safe_call(read_observatory_dashboard_resource)

    @server.resource("phios://observatory/atlas_gallery", mime_type="application/json")
    def resource_observatory_atlas_gallery() -> dict[str, object]:
        return _safe_call(read_observatory_atlas_gallery_resource)

    @server.resource("phios://observatory/storyboards/recent", mime_type="application/json")
    def resource_observatory_storyboards_recent() -> dict[str, object]:
        return _safe_call(read_observatory_recent_storyboards_resource)

    @server.resource("phios://observatory/dossiers/recent", mime_type="application/json")
    def resource_observatory_dossiers_recent() -> dict[str, object]:
        return _safe_call(read_observatory_recent_dossiers_resource)

    @server.resource("phios://observatory/field_libraries/recent", mime_type="application/json")
    def resource_observatory_field_libraries_recent() -> dict[str, object]:
        return _safe_call(read_observatory_recent_field_libraries_resource)

    @server.tool(name="phi_status")
    def tool_phi_status() -> dict[str, object]:
        return _safe_call(run_phi_status, kernel_adapter)

    @server.tool(name="phi_ask")
    def tool_phi_ask(prompt: str) -> dict[str, object]:
        return _safe_call(run_phi_ask, kernel_adapter, prompt)

    @server.tool(name="phi_pulse_once")
    def tool_phi_pulse_once(
        checkpoint: str | None = None,
        passphrase: str | None = None,
    ) -> dict[str, object]:
        return _safe_call(
            run_phi_pulse_once,
            kernel_adapter,
            checkpoint=checkpoint,
            passphrase=passphrase,
        )

    @server.tool(name="phi_observatory_summary")
    def tool_phi_observatory_summary() -> dict[str, object]:
        return _safe_call(run_phi_observatory_summary)

    @server.tool(name="phi_recent_activity")
    def tool_phi_recent_activity() -> dict[str, object]:
        return _safe_call(run_phi_recent_activity, kernel_adapter)

    @server.tool(name="phi_library_summary")
    def tool_phi_library_summary() -> dict[str, object]:
        return _safe_call(run_phi_library_summary)

    @server.prompt(name="field_guidance")
    def prompt_field_guidance() -> str:
        return _safe_call(build_field_guidance_prompt, kernel_adapter)

    return server


def main() -> None:
    """Run the PhiOS MCP server over stdio."""

    server = create_mcp_server()
    server.run(transport="stdio")


__all__ = ["create_mcp_server", "main", "phase1_registry", "mcp_surface_registry", "McpSurfaceRegistry"]
