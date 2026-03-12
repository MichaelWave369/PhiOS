"""Thin PhiKernel CLI adapter for PhiOS Phase 1 integration.

PhiKernel is the source of truth for runtime state.
PhiOS consumes PhiKernel command interfaces and owns presentation/workflow composition.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence


class PhiKernelAdapterError(RuntimeError):
    """Base error for PhiKernel adapter failures."""


class PhiKernelUnavailableError(PhiKernelAdapterError):
    """Raised when the `phik` executable is unavailable."""


@dataclass(slots=True)
class PhiKernelCLIAdapter:
    executable: str = "phik"

    def is_available(self) -> bool:
        return shutil.which(self.executable) is not None

    def _run_json(self, args: Sequence[str]) -> dict[str, object]:
        if not self.is_available():
            raise PhiKernelUnavailableError(
                "PhiKernel CLI `phik` was not found. Install and initialize PhiKernel first."
            )

        cmd = [self.executable, *args, "--json"]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )
        except OSError as exc:
            raise PhiKernelAdapterError(f"Failed to execute {' '.join(cmd)}: {exc}") from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or f"exit code {proc.returncode}"
            raise PhiKernelAdapterError(f"PhiKernel command failed ({' '.join(cmd)}): {detail}")

        raw = (proc.stdout or "").strip()
        if not raw:
            return {}

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PhiKernelAdapterError(
                f"PhiKernel command returned invalid JSON ({' '.join(cmd)}): {exc.msg}"
            ) from exc
        if not isinstance(parsed, dict):
            raise PhiKernelAdapterError(
                f"PhiKernel command returned unexpected payload type ({type(parsed).__name__})."
            )
        return parsed

    def status(self) -> dict[str, object]:
        return self._run_json(["status"])

    def field(self) -> dict[str, object]:
        return self._run_json(["field"])

    def anchor_show(self) -> dict[str, object]:
        return self._run_json(["anchor", "show"])

    def capsule_list(self) -> dict[str, object]:
        return self._run_json(["capsule", "list"])

    def think(self, prompt: str) -> dict[str, object]:
        return self._run_json(["think", prompt])

    def ask(self, prompt: str) -> dict[str, object]:
        return self._run_json(["ask", prompt])

    def pulse_once(self, checkpoint: str | None = None, passphrase: str | None = None) -> dict[str, object]:
        args: list[str] = ["pulse", "once"]
        if checkpoint:
            args.extend(["--checkpoint", checkpoint])
        if passphrase:
            args.extend(["--passphrase", passphrase])
        return self._run_json(args)

    def init(
        self,
        *,
        passphrase: str,
        sovereign_name: str,
        user_label: str,
        resonant_label: str | None = None,
    ) -> dict[str, object]:
        args = [
            "init",
            "--passphrase",
            passphrase,
            "--sovereign-name",
            sovereign_name,
            "--user-label",
            user_label,
        ]
        if resonant_label:
            args.extend(["--resonant-label", resonant_label])
        return self._run_json(args)
