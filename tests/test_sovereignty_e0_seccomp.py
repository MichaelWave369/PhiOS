"""Executable Linux x86_64 E0 smoke test; not PhiOS-wide security certification.

Compiles a tiny C harness with host cc, starts a child under a real kernel
seccomp filter, and requires observable errno denial for direct socket creation.
The trusted parent passes a Unix socketpair endpoint before filtering, so the
child can still exchange the proof using read/write without creating sockets.

A PASS proves only the enumerated denials under this exact launch. It does not
prove absence of arbitrary egress, correct network namespaces, browser policy,
gateway authentication, or a complete OS.
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments" / "sovereignty_e0" / "e0_probe.c"


@pytest.mark.skipif(
    sys.platform != "linux" or platform.machine() != "x86_64",
    reason="E0 kernel experiment is supported only on Linux x86_64",
)
def test_sovereignty_e0_raw_socket_denial_and_preopened_ipc(tmp_path: Path) -> None:
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("C compiler unavailable; no kernel result claimed")

    binary = tmp_path / "phios_e0_probe"
    compile_result = subprocess.run(
        [
            cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            str(SOURCE), "-o", str(binary)
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    execution = subprocess.run(
        [str(binary)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert execution.returncode == 0, (
        "E0 did not pass. This may be a filtered/unsupported CI host. "
        f"stdout={execution.stdout!r}; stderr={execution.stderr!r}"
    )
    receipt = json.loads(execution.stdout)
    assert receipt == {
        "schema": "PHIOS_SOVEREIGNTY_E0_V1",
        "platform": "linux_x86_64",
        "scope": "single_process_syscall_denials_and_preopened_uds",
        "kernel_seccomp_installed": True,
        "raw_ipv4_socket_denied": True,
        "raw_ipv6_socket_denied": True,
        "new_uds_socket_denied": True,
        "preopened_uds_ipc_passed": True,
        "independent_packet_capture_performed": False,
        "inherited_ip_fd_escape_tested": False,
        "full_os_network_isolation_verified": False,
        "status": "PASS",
    }
