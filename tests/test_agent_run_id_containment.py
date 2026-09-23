from __future__ import annotations

import json
from pathlib import Path

from phios.mcp.resources.agents import (
    read_agent_run_events_resource,
    read_agent_run_resource,
)
from phios.mcp.tools.agents import run_phi_agent_status, run_phi_kill_agent
from phios.services.agent_dispatch import (
    cancel_agent_run,
    dispatch_agentception_run,
    evaluate_agent_run_reflex,
    get_agent_run_status,
    list_agent_runs,
    persist_dispatch_storyboard,
    stream_agent_run_events,
)


def test_invalid_run_id_cannot_escape_agent_runs_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    outside = tmp_path / ".phios" / "victim.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text('{"secret":"unchanged"}', encoding="utf-8")

    malicious = "../../victim"

    status = get_agent_run_status(malicious)
    cancelled = cancel_agent_run(malicious)
    events = stream_agent_run_events(malicious)

    assert status == {
        "ok": False,
        "run_id": malicious,
        "error": "invalid_run_id",
    }
    assert cancelled == {
        "ok": False,
        "run_id": malicious,
        "error": "invalid_run_id",
    }
    assert events == []
    assert outside.read_text(encoding="utf-8") == '{"secret":"unchanged"}'


def test_invalid_run_id_does_not_create_agent_run_storage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert get_agent_run_status("../escape")["error"] == "invalid_run_id"
    assert stream_agent_run_events("run_nothex") == []

    assert not (tmp_path / ".phios" / "agents" / "runs").exists()


def test_mcp_surfaces_report_invalid_run_id_explicitly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "agent_kill")

    status = run_phi_agent_status(run_id="../escape")
    kill = run_phi_kill_agent(run_id="../escape")
    resource = read_agent_run_resource("../escape")
    events = read_agent_run_events_resource("../escape")

    assert status["ok"] is False
    assert status["error_code"] == "INVALID_RUN_ID"
    assert kill["ok"] is False
    assert kill["error_code"] == "INVALID_RUN_ID"
    assert resource["found"] is False
    assert resource["run"] is None
    assert events["events"] == []
    assert events["count"] == 0


def test_reflex_evaluation_rejects_invalid_run_id_before_path_use(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = evaluate_agent_run_reflex(
        run_id="../../victim",
        dispatch_outcome="completed",
        observer_label="test",
        evidence_sha256="a" * 64,
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_RUN_ID"
    assert not (tmp_path / ".phios" / "agents" / "runs").exists()


def test_storyboard_rejects_noncanonical_run_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = persist_dispatch_storyboard(
        run={"run_id": "../storyboard-escape"},
        plan={},
        events=[],
    )

    assert result["ok"] is False
    assert result["error_code"] == "INVALID_RUN_ID"
    assert not (tmp_path / ".phios" / "journal").exists()


def test_valid_generated_run_id_still_round_trips(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    run = dispatch_agentception_run(
        task="contained",
        context={},
        plan={"source": "test", "plan_steps": []},
        stream=False,
    )
    run_id = str(run["run_id"])

    assert run_id.startswith("run_")
    assert len(run_id) == 16

    status = get_agent_run_status(run_id)
    assert status["run_id"] == run_id

    cancelled = cancel_agent_run(run_id)
    assert cancelled["ok"] is True


def test_list_agent_runs_ignores_noncanonical_or_mismatched_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runs_dir = tmp_path / ".phios" / "agents" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    (runs_dir / "run_bad.json").write_text(
        json.dumps({"run_id": "run_bad", "created_at": "z"}),
        encoding="utf-8",
    )
    (runs_dir / "run_aaaaaaaaaaaa.json").write_text(
        json.dumps({"run_id": "run_bbbbbbbbbbbb", "created_at": "z"}),
        encoding="utf-8",
    )

    assert list_agent_runs(active_only=False) == []
