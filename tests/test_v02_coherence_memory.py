from __future__ import annotations

import json
import socket
from pathlib import Path

from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import SovereignSnapshot
from phios.core.tbrc_bridge import TBRCBridge
from phios.display.sparkline import BLOCKS, render_bar, render_sparkline, trajectory_arrow
from phios.shell import phi_commands
from phios.shell.phi_router import route_command
from phios.shell.phi_session import PhiSession


def test_coherence_live_renders_without_error(monkeypatch, capsys):
    session = PhiSession()
    monkeypatch.setattr(phi_commands.time, "sleep", lambda _: None)
    out = phi_commands.cmd_coherence_live(session, key_reader=lambda: "q", iterations=1)
    captured = capsys.readouterr().out
    assert out == ""
    assert "Live Coherence Monitor" in captured


def test_coherence_live_exits_on_ctrl_c(monkeypatch):
    session = PhiSession()
    monkeypatch.setattr(phi_commands.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    out = phi_commands.cmd_coherence_live(session, key_reader=lambda: None, iterations=1)
    assert out == ""


def test_sparkline_renders_correct_length():
    history = [0.1, 0.2, 0.3, 0.4]
    assert len(render_sparkline(history)) == len(history)


def test_sparkline_all_values_valid_blocks():
    history = [0.0, 0.25, 0.5, 0.75, 1.0]
    line = render_sparkline(history)
    assert all(ch in BLOCKS for ch in line)


def test_bar_render_correct_width():
    assert len(render_bar(0.5, width=20)) == 20


def test_bar_render_full_at_1_0():
    assert render_bar(1.0, width=10) == "█" * 10


def test_bar_render_empty_at_0_0():
    assert render_bar(0.0, width=10) == "░" * 10


def test_trajectory_arrow_all_states():
    assert trajectory_arrow("rising") == "↗"
    assert trajectory_arrow("falling") == "↘"
    assert trajectory_arrow("stable") == "→"
    assert trajectory_arrow("volatile") == "↕"


def test_resonance_moment_at_369_seconds(monkeypatch):
    session = PhiSession()
    seq = iter([0.0, 369.0])
    monkeypatch.setattr(phi_commands.time, "monotonic", lambda: next(seq))
    monkeypatch.setattr(phi_commands.time, "sleep", lambda _: None)
    phi_commands.cmd_coherence_live(session, key_reader=lambda: "q", iterations=1)
    assert session.resonance_moments_hit == 1


def test_resonance_countdown_correct():
    assert phi_commands._resonance_in(0) == 0
    assert phi_commands._resonance_in(1) == 368


def _session_payload() -> dict[str, object]:
    return {
        "history": [0.2, 0.4, 0.6],
        "duration_s": 12,
        "commands_run": 3,
        "resonance_moments_hit": 1,
        "trajectory": "rising",
    }


def test_snapshot_captures_all_fields():
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    for key in ["schema", "captured_at", "phios_version", "system", "coherence", "sovereignty", "session", "environment", "integrity", "operator_notes", "attribution", "declaration"]:
        assert key in snap


def test_snapshot_schema_correct():
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    assert snap["schema"] == "phios.v0.2.sovereign_snapshot"


def test_snapshot_hash_computed():
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    assert snap["integrity"]["content_hash"]


def test_snapshot_verify_valid(tmp_path):
    path = tmp_path / "a.json"
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    path.write_text(json.dumps(snap), encoding="utf-8")
    result = SovereignSnapshot().verify(str(path))
    assert result.ok is True


def test_snapshot_verify_detects_tamper(tmp_path):
    path = tmp_path / "a.json"
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    snap["coherence"]["lt_score"] = 0.0
    path.write_text(json.dumps(snap), encoding="utf-8")
    result = SovereignSnapshot().verify(str(path))
    assert result.ok is False


def test_snapshot_compare_schema_correct(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    sa = SovereignSnapshot().capture(compute_lt(), _session_payload())
    sb = SovereignSnapshot().capture(compute_lt(), {**_session_payload(), "trajectory": "falling"})
    a.write_text(json.dumps(sa), encoding="utf-8")
    b.write_text(json.dumps(sb), encoding="utf-8")
    out = SovereignSnapshot().compare(str(a), str(b))
    assert out["schema"] == "phios.v0.2.snapshot_compare"


def test_snapshot_annotate_additive_only(tmp_path):
    path = tmp_path / "a.json"
    snapper = SovereignSnapshot()
    snap = snapper.capture(compute_lt(), _session_payload())
    original = snap["integrity"]["content_hash"]
    path.write_text(json.dumps(snap), encoding="utf-8")
    snapper.annotate(str(path), "note")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["integrity"]["content_hash"] == original
    assert data["integrity"]["annotation_hash"]


def test_snapshot_hostname_anonymized():
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    assert snap["system"]["hostname"] != socket.gethostname()


def test_snapshot_includes_attribution():
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    assert snap["attribution"]["lab"] == "PHI369 Labs / Parallax"


def test_snapshot_includes_declaration():
    snap = SovereignSnapshot().capture(compute_lt(), _session_payload())
    assert "Sovereign. Coherent. Local. Free." in snap["declaration"]["line_1"]


def test_tbrc_bridge_degrades_when_not_installed(monkeypatch):
    monkeypatch.delenv("TBRC_PATH", raising=False)
    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    bridge = TBRCBridge()
    assert bridge.is_available() is False
    assert bridge.memory_stats()["available"] is False


def test_memory_status_degraded_message_shown(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    out, code = route_command(["memory", "status"])
    assert code == 0
    assert "TBRC bridge unavailable" in out


def test_archive_timeline_degraded_gracefully(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    out, code = route_command(["archive", "timeline"])
    assert code == 0
    assert "TBRC bridge unavailable" in out


def test_kg_stats_degraded_gracefully(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    out, code = route_command(["kg", "stats"])
    assert code == 0
    data = json.loads(out)
    assert data["available"] is False


def test_tbrc_bridge_lazy_import():
    source = Path("phios/core/tbrc_bridge.py").read_text(encoding="utf-8")
    assert "import tbrc" not in source


def test_phi_memory_search_returns_list(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    out, code = route_command(["memory", "search", "abc"])
    assert code == 0
    data = json.loads(out)
    assert isinstance(data, list)


def test_phi_archive_add_requires_title():
    out, code = route_command(["archive", "add"])
    assert code == 0
    assert out.startswith("Usage: archive add")
