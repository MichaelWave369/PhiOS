from __future__ import annotations

import io
import json
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

from phios.core.brainc_client import BrainCClient, BrainCResponse, SYSTEM_PROMPT
from phios.desktop.launcher import PhiLauncher
from phios.desktop.notifications import PhiNotifier
from phios.desktop.wofi_css import WOFI_CSS
from phios.shell.phi_router import route_command


def test_brainc_ask_degrades_without_ollama(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    out = BrainCClient().ask("hello", stream=False)
    assert "BrainC unavailable" in out.answer


def test_brainc_response_schema_correct(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    resp = BrainCClient().ask("hello", stream=False)
    assert isinstance(resp, BrainCResponse)
    for f in ["answer", "model", "local", "inference_ms", "sovereignty_confirmed", "context_used"]:
        assert hasattr(resp, f)


def test_brainc_sovereignty_footer_always_present(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    resp = BrainCClient().ask("hello", stream=False)
    assert "No data left this machine." in resp.answer


def test_brainc_system_prompt_contains_hemavit():
    assert "Hemavit is the monk in Thailand" in SYSTEM_PROMPT


def test_brainc_system_prompt_contains_lt_formula():
    assert "L(t) = A_on · Ψb_total · G_score · C_score is the life viability score" in SYSTEM_PROMPT


def test_brainc_context_includes_lt_score(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    out, code = route_command(["ask", "--session"])
    assert code == 0
    assert "No data left this machine." in out


def test_brainc_never_raises_on_connection_error(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    resp = BrainCClient().ask("hello", stream=True)
    assert isinstance(resp.answer, str)


def test_phi_ask_streams_or_returns_string(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    f = io.StringIO()
    with redirect_stdout(f):
        out, code = route_command(["ask", "what is phi?"])
    assert code == 0
    assert isinstance(out, str)
    assert "No data left this machine." in out


def test_phi_ask_lt_returns_interpretation(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    out, code = route_command(["ask", "--lt"])
    assert code == 0
    assert "No data left this machine." in out


def test_phi_ask_next_returns_suggestion(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("x")))
    out, code = route_command(["ask", "--next"])
    assert code == 0
    assert "No data left this machine." in out


def test_launcher_generates_wofi_config(monkeypatch, tmp_path):
    launcher = PhiLauncher()
    launcher.wofi_dir = tmp_path / "wofi"
    path = launcher.generate_wofi_config()
    assert Path(path).exists()


def test_launcher_generates_wofi_css(monkeypatch, tmp_path):
    launcher = PhiLauncher()
    launcher.wofi_dir = tmp_path / "wofi"
    path = launcher.generate_wofi_css()
    assert Path(path).exists()


def test_launcher_css_contains_tiekat_colors():
    assert "#070A0F" in WOFI_CSS
    assert "#C9A84C" in WOFI_CSS
    assert "#A9B0C3" in WOFI_CSS


def test_launcher_phi_entries_include_core_commands():
    entries = PhiLauncher().generate_phi_entries()
    required = ["phi ask", "phi status", "phi coherence", "phi tbrc status", "phi sovereign export ./phi_snapshot.json", "phi wallpaper generate", "phi notify status"]
    for item in required:
        assert item in entries


def test_launcher_prompt_contains_lt_score():
    prompt = PhiLauncher().get_prompt_with_lt()
    assert prompt.startswith("φ ")
    assert "❯" in prompt


def test_launcher_degrades_without_wofi(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda *_: None)
    PhiLauncher().launch()
    out = capsys.readouterr().out
    assert "Wofi unavailable" in out


def test_notifier_respects_min_interval(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    assert notifier.notify("x", "a", "b") is True
    assert notifier.notify("x", "a", "b") is False


def test_notifier_never_raises_without_notify_send(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    ok = notifier.notify("x", "a", "b")
    assert ok is True


def test_resonance_notification_at_369(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    assert notifier.resonance_moment(0.9, force=True) is True


def test_sovereignty_on_notification_content(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    notifier.sovereignty_changed(True, force=True)
    assert "Enabled" in notifier.history[-1].title


def test_sovereignty_off_notification_content(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    notifier.sovereignty_changed(False, force=True)
    assert "Disabled" in notifier.history[-1].title


def test_coherence_alert_threshold_correct(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    assert notifier.coherence_alert(0.5, 0.05, force=True) is False
    assert notifier.coherence_alert(0.5, 0.2, force=True) is True


def test_session_rhythm_9_is_gold(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    notifier.session_rhythm(9, force=True)
    assert "Gold coherence" in notifier.history[-1].body


def test_notification_history_max_9(monkeypatch):
    notifier = PhiNotifier()
    monkeypatch.setattr("shutil.which", lambda *_: None)
    for i in range(15):
        notifier.notify(f"k{i}", "title", "body", force=True)
    assert len(notifier.history) == 9
