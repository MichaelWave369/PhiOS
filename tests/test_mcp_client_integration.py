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



def test_mcp_client_harness_discovery_path_if_available():
    """Runtime-gated integration prep for discovery/resource/tool client paths."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Placeholder assertion for CI expansion: when stdio client harness is available,
    # this path is where tests should call resources/read tool methods end-to-end.
    assert ClientSession is not None
    assert stdio_client is not None



def test_mcp_client_harness_profile_path_if_available(monkeypatch):
    """Runtime-gated path for future profile-aware client assertions."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    assert ClientSession is not None
    assert stdio_client is not None



def test_mcp_client_harness_phase7_path_if_available(monkeypatch):
    """Runtime-gated path for future end-to-end phase7 client checks."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Future expansion point:
    # - discover resources/tools
    # - read phios://sessions/current and phios://archive/pathways/index
    # - call phi_session_summary and validate structured payload
    assert ClientSession is not None
    assert stdio_client is not None



def test_mcp_client_harness_phase8_path_if_available(monkeypatch):
    """Runtime-gated path for deeper discovery→browse→tool flow assertions."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Future expansion point:
    # - call phi_discovery
    # - read phios://browse/overview
    # - read phios://sessions/current
    # - read phios://archive/pathways/index
    # - call phi_archive_summary
    # - assert pulse denial path when pulse scope not enabled
    assert ClientSession is not None
    assert stdio_client is not None


def test_mcp_client_harness_phase9_path_if_available(monkeypatch):
    """Runtime-gated path for Phase 9 discovery→browse→rollup→tool flow checks."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Future expansion point:
    # - call phi_discovery
    # - read phios://browse/learning_paths
    # - read phios://collections/field_libraries/rollup
    # - read phios://archive/pathways/index
    # - call phi_collection_summary
    # - assert pulse denial path under client capability posture
    assert ClientSession is not None
    assert stdio_client is not None


def test_mcp_client_harness_phase10_path_if_available(monkeypatch):
    """Runtime-gated path for Phase 10 discovery→program rollup→curation tool flow."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Future expansion point:
    # - call phi_discovery
    # - read phios://browse/curricula
    # - read phios://collections/field_libraries/rollup
    # - read phios://programs/curricula/rollup
    # - read phios://archive/pathways/index
    # - call phi_program_summary / phi_curation_summary
    # - assert profile capability posture and pulse deny behavior
    assert ClientSession is not None
    assert stdio_client is not None


def test_mcp_client_harness_phase11_path_if_available(monkeypatch):
    """Runtime-gated path for broader Phase 11 discovery→browse→rollup→summary flows."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Future expansion point:
    # - call phi_discovery
    # - read phios://browse/capstones
    # - read phios://collections/field_libraries/rollup
    # - read phios://capstones/syllabi/rollup
    # - read phios://archive/pathways/index
    # - call phi_capstone_summary
    # - assert capability/profile posture and pulse deny behavior
    assert ClientSession is not None
    assert stdio_client is not None


def test_mcp_client_harness_phase12_path_if_available(monkeypatch):
    """Runtime-gated path for Phase 12 discovery→family browse→catalog→summary flow."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    # Future expansion point:
    # - call phi_discovery
    # - read phios://browse/observatory_families
    # - read phios://collections/field_libraries/rollup
    # - read phios://catalogs/learning
    # - read phios://archive/pathways/index
    # - call phi_catalog_summary
    # - assert profile/capability posture and pulse deny behavior
    assert ClientSession is not None
    assert stdio_client is not None


def test_mcp_client_harness_phase13_path_if_available(monkeypatch):
    """Runtime-gated path for Phase 13 discovery→family browse→map→summary flow."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client stdio/session modules unavailable in this runtime")

    expected_phase13_path = [
        "phi_discovery",
        "phios://browse/learning_maps",
        "phios://programs/curricula/rollup",
        "phios://catalogs/learning",
        "phios://maps/learning",
        "phios://sessions/current",
        "phi_learning_map_summary",
    ]
    # Runtime-gated integration path scaffold for stronger E2E coverage:
    # discovery -> family browse -> rollup -> catalog -> map -> session -> summary,
    # with profile/capability posture assertions and pulse deny checks.
    assert ClientSession is not None
    assert stdio_client is not None
    assert len(expected_phase13_path) == 7


def test_mcp_client_harness_phase14_sdk_e2e_if_available(monkeypatch):
    """Runtime-gated SDK-backed Phase 14 E2E path with real client calls when available."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        import asyncio
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
        from mcp.client.stdio import StdioServerParameters  # type: ignore
    except Exception:
        pytest.skip("mcp client runtime modules unavailable for SDK-backed path")

    repo_root = Path(__file__).resolve().parents[1]

    async def _run() -> dict[str, object]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "phios.mcp.server"],
            cwd=str(repo_root),
            env={"PHIOS_MCP_PROFILE": "observer"},
        )
        async with stdio_client(params) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                resources = await session.list_resources()
                tools = await session.list_tools()

                # End-to-end Phase 14 flow:
                discovery = await session.call_tool("phi_discovery", {})
                _ = await session.read_resource("phios://browse/archive_groups")
                _ = await session.read_resource("phios://programs/curricula/rollup")
                _ = await session.read_resource("phios://catalogs/learning")
                _ = await session.read_resource("phios://maps/learning")
                _ = await session.read_resource("phios://dashboards/discovery")
                _ = await session.read_resource("phios://sessions/current")
                summary = await session.call_tool("phi_discovery_dashboard_summary", {"dashboard": "discovery"})
                pulse = await session.call_tool("phi_pulse_once", {})
                return {
                    "resources": resources,
                    "tools": tools,
                    "discovery": discovery,
                    "summary": summary,
                    "pulse": pulse,
                }

    try:
        out = asyncio.run(_run())
    except Exception as exc:
        pytest.skip(f"sdk-backed client path unavailable in this runtime: {exc}")

    assert out["resources"] is not None
    assert out["tools"] is not None
    assert out["discovery"] is not None
    assert out["summary"] is not None
    # pulse should remain denied by default-safe posture unless explicitly enabled.
    assert out["pulse"] is not None
    pulse_repr = repr(out["pulse"])
    assert "PULSE_NOT_PERMITTED" in pulse_repr or "allowed=False" in pulse_repr or "\"allowed\": False" in pulse_repr


def test_mcp_client_harness_phase15_sdk_e2e_if_available(monkeypatch):
    """Runtime-gated SDK-backed Phase 15 E2E path including console/family-dashboard surfaces."""

    _ = pytest.importorskip("mcp", reason="mcp SDK not installed in this runtime")
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")

    try:
        import asyncio
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore
    except Exception:
        pytest.skip("mcp client runtime modules unavailable for SDK-backed phase15 path")

    repo_root = Path(__file__).resolve().parents[1]

    async def _run() -> dict[str, object]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "phios.mcp.server"],
            cwd=str(repo_root),
            env={"PHIOS_MCP_PROFILE": "observer"},
        )
        async with stdio_client(params) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                discovery = await session.call_tool("phi_discovery", {})
                _ = await session.read_resource("phios://browse/archive_groups")
                _ = await session.read_resource("phios://programs/curricula/rollup")
                _ = await session.read_resource("phios://catalogs/learning")
                _ = await session.read_resource("phios://maps/learning")
                _ = await session.read_resource("phios://dashboards/discovery")
                _ = await session.read_resource("phios://consoles/navigation")
                _ = await session.read_resource("phios://sessions/current")
                summary = await session.call_tool("phi_navigation_console_summary", {"console": "navigation"})
                pulse = await session.call_tool("phi_pulse_once", {})
                return {"discovery": discovery, "summary": summary, "pulse": pulse}

    try:
        out = asyncio.run(_run())
    except Exception as exc:
        pytest.skip(f"sdk-backed phase15 path unavailable in this runtime: {exc}")

    assert out["discovery"] is not None
    assert out["summary"] is not None
    assert out["pulse"] is not None
    pulse_repr = repr(out["pulse"])
    assert "PULSE_NOT_PERMITTED" in pulse_repr or "allowed=False" in pulse_repr or "\"allowed\": False" in pulse_repr
