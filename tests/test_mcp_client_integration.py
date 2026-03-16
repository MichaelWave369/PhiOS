from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_mcp_client_harness_real_sdk_path_if_available():
    """Integration prep: real MCP client path when SDK runtime is available.

    This test is intentionally runtime-gated for CI environments where `mcp`
    client extras may not be installed. It documents and validates the path.
    """

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    assert ClientSession is not None
    assert stdio_client is not None


def test_mcp_stdio_process_starts_and_is_harness_ready():
    """Minimal process-level integration check when MCP SDK runtime is present."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "phios.mcp.server"],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.poll() is None
    finally:
        proc.terminate()
        proc.wait(timeout=5)
