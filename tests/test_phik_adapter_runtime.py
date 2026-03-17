from __future__ import annotations

import subprocess

from phios.adapters.phik import PhiKernelCLIAdapter


def test_runtime_command_builds_flags(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")
    captured = {}

    def fake_run(cmd, capture_output, text, check, shell):
        captured["cmd"] = cmd
        captured["shell"] = shell
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    adapter = PhiKernelCLIAdapter()
    adapter.runtime(prompt="p", adapter="legacy", mode="shadow")

    assert captured["cmd"] == [
        "phik",
        "runtime",
        "--prompt",
        "p",
        "--adapter",
        "legacy",
        "--mode",
        "shadow",
        "--json",
    ]
    assert captured["shell"] is False
