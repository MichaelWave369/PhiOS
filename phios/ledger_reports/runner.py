from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from phios.apps.sandbox import (
    BuildSandboxPolicy,
    BubblewrapSandboxRunner,
    SandboxBackendIdentity,
)

DEFAULT_REPORT_SANDBOX_POLICY = BuildSandboxPolicy(
    network_mode="deny",
    wall_clock_seconds=30,
    cpu_seconds=20,
    address_space_bytes=1024 * 1024 * 1024,
    max_open_files=128,
    max_file_size_bytes=256 * 1024 * 1024,
)


@dataclass(frozen=True, kw_only=True)
class WorkerRun:
    backend_identity: SandboxBackendIdentity
    sandbox_policy_sha256: str
    stdout: str
    stderr: str


class LedgerWorkerRunner:
    """Linux-only report worker launcher. There is intentionally no host fallback."""

    def __init__(self, policy: BuildSandboxPolicy | None = None) -> None:
        self.policy = policy or DEFAULT_REPORT_SANDBOX_POLICY

    def run_build(self, workspace: Path) -> WorkerRun:
        return self._run(
            workspace,
            (
                "-m",
                "phios.ledger_reports.worker",
                "build",
                "--request",
                "request.json",
                "--output",
                "projection.duckdb",
            ),
        )

    def run_query(self, workspace: Path) -> WorkerRun:
        return self._run(
            workspace,
            (
                "-m",
                "phios.ledger_reports.worker",
                "query",
                "--request",
                "request.json",
                "--database",
                "projection.duckdb",
                "--output",
                "result.json",
            ),
        )

    def _run(self, workspace: Path, argv_tail: tuple[str, ...]) -> WorkerRun:
        if platform.system() != "Linux":
            raise RuntimeError("Ledger report worker isolation is qualified only on Linux")

        root = workspace.expanduser().resolve(strict=True)
        runtime_parent = Path(__file__).resolve().parents[2]
        if not (runtime_parent / "phios").is_dir():
            raise RuntimeError("PhiOS runtime package root could not be resolved")

        runner = BubblewrapSandboxRunner(
            self.policy,
            extra_read_only_binds=((runtime_parent, "/phios/runtime"),),
            extra_environment={"PYTHONPATH": "/phios/runtime"},
        )
        backend = runner.preflight()
        command = runner.command_for(
            executable_path=sys.executable,
            argv_tail=argv_tail,
            source_root=root,
            cwd=root,
        )
        try:
            result = subprocess.run(
                command,
                cwd=root,
                env={"PATH": os.environ.get("PATH", "")},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=self.policy.wall_clock_seconds + 5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Ledger report worker execution failed") from exc

        stdout = result.stdout.decode("utf-8", errors="replace")[:8192]
        stderr = result.stderr.decode("utf-8", errors="replace")[:8192]
        if result.returncode != 0:
            raise RuntimeError(
                f"Ledger report worker returned nonzero ({result.returncode}): {stderr}"
            )
        return WorkerRun(
            backend_identity=backend,
            sandbox_policy_sha256=self.policy.sha256(),
            stdout=stdout,
            stderr=stderr,
        )
