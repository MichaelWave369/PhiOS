from __future__ import annotations

from pathlib import Path

from phios.core import lt_engine
from phios.core.tbrc_bridge import TBRCBridge
from phios.shell.phi_commands import cmd_research
from phios.shell.phi_dashboard import PhiDashboard


def test_tbrc_bridge_full_status_schema() -> None:
    status = TBRCBridge().full_status()
    expected = {
        "available",
        "version",
        "active_session",
        "memory_entries",
        "kg_nodes",
        "archive_entries",
        "phb_connected",
        "phb_sensor_count",
        "last_session_lt",
        "brainc_tbrc_available",
    }
    assert expected.issubset(status.keys())


def test_tbrc_bridge_degrades_all_methods() -> None:
    bridge = TBRCBridge()
    assert bridge.get_active_session() is None
    assert bridge.get_session_lt() is None
    assert bridge.search_memory("x") == []
    assert bridge.find_concept("x") == []
    assert bridge.get_archive_timeline() == []


def test_tbrc_session_lt_returns_none_when_inactive() -> None:
    assert TBRCBridge().get_session_lt() is None


def test_tbrc_start_requires_operator_confirmed() -> None:
    result = TBRCBridge().start_quick_session()
    assert result["started"] is False


def test_tbrc_stop_requires_operator_confirmed() -> None:
    result = TBRCBridge().stop_active_session()
    assert result["stopped"] is False


def test_tbrc_archive_add_requires_confirmed() -> None:
    result = TBRCBridge().add_archive_milestone("t", "n", "s")
    assert result["added"] is False


def test_tbrc_phb_status_schema_correct() -> None:
    status = TBRCBridge().get_phb_status()
    assert "available" in status


def test_tbrc_phb_contribution_zero_when_disconnected() -> None:
    assert TBRCBridge().get_phb_lt_contribution() == 0.0


def test_lt_blends_tbrc_when_session_active(monkeypatch) -> None:
    class FakeBridge:
        def get_phb_lt_contribution(self):
            return 0.0

        def get_session_lt(self):
            return 1.0

    monkeypatch.setattr("phios.core.tbrc_bridge.TBRCBridge", lambda: FakeBridge())
    monkeypatch.setattr(lt_engine, "_compute_system_components", lambda: (0.2, 0.9, 0.2))
    data = lt_engine.compute_lt()
    assert data["blended_lt"] >= data["system_lt"]
    assert data["lt"] >= data["system_lt"]


def test_lt_blend_never_reduces_system_lt(monkeypatch) -> None:
    class FakeBridge:
        def get_phb_lt_contribution(self):
            return 0.0

        def get_session_lt(self):
            return 0.0

    monkeypatch.setattr("phios.core.tbrc_bridge.TBRCBridge", lambda: FakeBridge())
    monkeypatch.setattr(lt_engine, "_compute_system_components", lambda: (0.9, 0.1, 0.9))
    data = lt_engine.compute_lt()
    assert data["lt"] >= data["system_lt"]


def test_kg_summary_schema_correct() -> None:
    data = TBRCBridge().get_kg_summary()
    assert "available" in data


def test_memory_search_returns_list() -> None:
    assert isinstance(TBRCBridge().search_memory("phi"), list)


def test_snapshot_memorize_tags_correct() -> None:
    out = TBRCBridge().memorize_phi_snapshot({"lt": 0.7})
    assert isinstance(out, dict)


def test_phi_research_status_renders() -> None:
    out = cmd_research(["status"])
    assert out


def test_phi_research_compose_requires_confirmation() -> None:
    out = cmd_research(["compose"])
    assert "Confirmation required" in out or "TBRC bridge unavailable" in out


def test_phi_research_start_requires_yes_flag() -> None:
    out = cmd_research(["start"])
    assert "--yes" in out


def test_phi_research_stop_requires_yes_flag() -> None:
    out = cmd_research(["stop"])
    assert "--yes" in out


def test_phi_research_session_schema_correct() -> None:
    out = cmd_research(["session"])
    assert "active_session" in out or "TBRC bridge unavailable" in out


def test_phi_research_phb_status_degrades() -> None:
    out = cmd_research(["phb", "status"])
    assert out


def test_phi_research_memory_search_works() -> None:
    out = cmd_research(["memory", "search", "x"])
    assert out.startswith("[")


def test_phi_research_archive_timeline_works() -> None:
    out = cmd_research(["archive", "timeline"])
    assert out.startswith("[")


def test_phi_research_kg_find_works() -> None:
    out = cmd_research(["kg", "find", "concept"])
    assert out.startswith("[")


def test_dashboard_renders_without_error() -> None:
    text = PhiDashboard().render(now_s=1)
    assert "PhiOS Living Dashboard" in text


def test_dashboard_renders_without_tbrc(monkeypatch) -> None:
    monkeypatch.setattr(TBRCBridge, "full_status", lambda self: {"available": False, "memory_entries": 0, "active_session": None})
    text = PhiDashboard().render(now_s=2)
    assert "Research" in text


def test_dashboard_renders_without_phb(monkeypatch) -> None:
    monkeypatch.setattr(TBRCBridge, "get_phb_status", lambda self: {"available": False, "connected": False, "sensor_count": 0})
    text = PhiDashboard().render(now_s=3)
    assert "Hardware" in text


def test_dashboard_renders_without_brainc(monkeypatch) -> None:
    monkeypatch.setattr("phios.shell.phi_dashboard.ollama_available", lambda: False)
    text = PhiDashboard().render(now_s=4)
    assert "BrainC:no" in text


def test_dashboard_coherence_panel_has_all_components() -> None:
    text = PhiDashboard().render(now_s=5)
    for token in ("L(t)", "psi_b", "G:", "C:", "trajectory"):
        assert token in text


def test_dashboard_research_panel_shows_no_session(monkeypatch) -> None:
    monkeypatch.setattr(TBRCBridge, "full_status", lambda self: {"active_session": None, "memory_entries": 0})
    text = PhiDashboard().render(now_s=6)
    assert "session: none" in text


def test_dashboard_archive_strip_max_3_entries(monkeypatch) -> None:
    entries = [{"title": f"t{i}"} for i in range(6)]
    monkeypatch.setattr(TBRCBridge, "get_archive_timeline", lambda self, limit=3: entries)
    text = PhiDashboard().render(now_s=7)
    assert "t0" in text and "t1" in text and "t2" in text
    assert "t3" not in text


def test_dashboard_rhythm_bar_correct_at_369() -> None:
    text = PhiDashboard().render(now_s=369)
    assert "next-9:00s" in text


def test_dashboard_never_raises_on_render(monkeypatch) -> None:
    monkeypatch.setattr("phios.shell.phi_dashboard.compute_lt", lambda: {"lt": 0.5, "components": {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5}})
    assert PhiDashboard().render(now_s=8)


def test_dashboard_snapshot_wires_to_tbrc(monkeypatch, tmp_path) -> None:
    dashboard = PhiDashboard()
    called = {"ok": False}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TBRCBridge, "is_available", lambda self: True)

    def _memorize(self, snapshot):
        called["ok"] = True
        return {"available": True}

    monkeypatch.setattr(TBRCBridge, "memorize_phi_snapshot", _memorize)
    out = dashboard.handle_snapshot()
    assert called["ok"] is True
    assert Path(out["snapshot"]).exists()
