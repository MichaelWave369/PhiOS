"""PhiOS MCP server (Phase 1).

This module provides a minimal stdio MCP server surface:
- resources: phios://field/state, phios://coherence/lt, phios://system/status
- tools: phi_status, phi_ask, phi_pulse_once
- prompt: field_guidance
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.prompts.field_guidance import build_field_guidance_prompt
from phios.mcp.resources.coherence_lt import read_coherence_lt_resource
from phios.mcp.resources.field_state import read_field_state_resource
from phios.mcp.resources.status import read_system_status_resource
from phios.mcp.tools.ask import run_phi_ask
from phios.mcp.tools.pulse import run_phi_pulse_once
from phios.mcp.tools.status import run_phi_status


@dataclass(slots=True)
class Phase1Registry:
    """Simple registry metadata for tests and introspection."""

    resources: tuple[str, ...]
    tools: tuple[str, ...]
    prompts: tuple[str, ...]


def phase1_registry() -> Phase1Registry:
    return Phase1Registry(
        resources=(
            "phios://field/state",
            "phios://coherence/lt",
            "phios://system/status",
        ),
        tools=("phi_status", "phi_ask", "phi_pulse_once"),
        prompts=("field_guidance",),
    )


def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - exercised via server handlers
        raise RuntimeError(f"PhiOS MCP upstream call failed: {exc}") from exc


def create_mcp_server(adapter: PhiKernelCLIAdapter | None = None) -> Any:
    """Create and register a Phase 1 stdio MCP server.

    Returns an instance of ``FastMCP`` from the official MCP SDK.
    """

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

    @server.prompt(name="field_guidance")
    def prompt_field_guidance() -> str:
        return _safe_call(build_field_guidance_prompt, kernel_adapter)

    return server


def main() -> None:
    """Run the PhiOS MCP server over stdio."""

    server = create_mcp_server()
    server.run(transport="stdio")


__all__ = ["create_mcp_server", "main", "phase1_registry", "Phase1Registry"]
