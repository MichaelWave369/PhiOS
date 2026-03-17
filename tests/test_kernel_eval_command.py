from __future__ import annotations

import json

from phios.shell.phi_router import route_command


class StubAdapter:
    def runtime(self, *, prompt=None, adapter=None, mode=None):
        base = {
            "engine": "phik",
            "engine_version": "2.0",
            "substrate": "external",
            "substrate_version": "50",
            "adapter": adapter,
            "mode": mode,
            "evidence_level": "medium",
            "null_result": False,
            "debug": {},
        }
        if mode == "shadow":
            return {
                **base,
                "verdict": "hold",
                "recommendation": "wait",
                "coherence_score": 0.6,
                "stability_score": 0.7,
                "readiness_score": 0.65,
                "risk_score": 0.4,
            }
        return {
            **base,
            "verdict": "proceed",
            "recommendation": "continue",
            "coherence_score": 0.9,
            "stability_score": 0.85,
            "readiness_score": 0.8,
            "risk_score": 0.2,
        }


def test_eval_kernel_cli_json(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_commands.PhiKernelCLIAdapter", lambda: StubAdapter())

    out, code = route_command(["eval-kernel", "--compare", "legacy", "tiekat_v50", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["config"]["compare_mode"] is True
    assert data["summary"]["total_cases"] >= 1


def test_eval_kernel_cli_report_export(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_commands.PhiKernelCLIAdapter", lambda: StubAdapter())
    report_path = tmp_path / "kernel_report.json"

    out, code = route_command([
        "eval-kernel",
        "--compare",
        "legacy",
        "tiekat_v50",
        "--report",
        str(report_path),
        "--json",
    ])

    assert code == 0
    data = json.loads(out)
    assert data["report_path"] == str(report_path)
    assert report_path.exists()


def test_review_kernel_rollout_cli_json_and_markdown(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_commands.PhiKernelCLIAdapter", lambda: StubAdapter())

    route_command(["eval-kernel", "--compare", "legacy", "tiekat_v50", "--json"])
    md = tmp_path / "review.md"
    out, code = route_command([
        "review-kernel-rollout",
        "--adapter",
        "legacy",
        "--markdown",
        str(md),
        "--json",
    ])

    assert code == 0
    data = json.loads(out)
    assert data["review"]["status"] in {"ready", "caution", "hold"}
    assert data["markdown_path"] == str(md)
    assert md.exists()


def test_status_surface_includes_rollout_block(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_status_report",
        lambda *_: {
            "anchor_verification_state": "verified",
            "heart_state": "running",
            "field_action": "hold",
            "field_drift_band": "green",
            "capsule_count": 2,
            "kernel_runtime": {
                "enabled": True,
                "configured_adapter": "legacy",
                "shadow_adapter": "tiekat_v50",
                "compare_mode": True,
            },
            "kernel_rollout": {"recent_samples": 5, "review_status": "caution"},
        },
    )

    out, code = route_command(["status"])
    assert code == 0
    assert "Kernel runtime:" in out
    assert "Recent compare samples:" in out
    assert "Promotion readiness:" in out
