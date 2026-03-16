"""Phase 1-8 MCP interface layer for PhiOS.

This package exposes existing PhiOS/PhiKernel-backed read and action surfaces via MCP.
PhiKernel remains source of truth for runtime state.
"""

from .server import create_mcp_server

__all__ = ["create_mcp_server"]
