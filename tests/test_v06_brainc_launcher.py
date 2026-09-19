from __future__ import annotations

import io
import json
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

from phios.apps.desktop_catalog import (
    DesktopCatalogIssue,
    DesktopCatalogItem,
    DesktopCatalogSnapshot,
)
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
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_ask_report",
        lambda *_: {
            "coach": "SovereignCoach",
            "field_action": "maintain",
            "field_band": "green",
            "safety_posture": "safe",
            "route_reason": "local",
            "body": "Operator guidance.",
            "next_actions": ["phi status"],
        },
    )
    f = io.StringIO()
    with redirect_stdout(f):
        out, code = route_command(["ask", "what is phi?"])
    assert code == 0
    assert isinstance(out, str)
    assert "Operator guidance." in out


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



def _launcher_catalog_snapshot(tmp_path: Path) -> DesktopCatalogSnapshot:
    ready_bundle = (tmp_path / "bundle with spaces").absolute()
    blocked_bundle = (tmp_path / "blocked").absolute()
    ready = DesktopCatalogItem(
        catalog_key="phi.ready/0123456789abcdef",
        bundle_path=str(ready_bundle),
        app_id="phi.ready",
        app_version="1.0.0",
        desktop_name="Ready App",
        desktop_icon="phios-app",
        desktop_entry_path=str((tmp_path / "phi-ready.desktop").absolute()),
        desktop_app_plan_sha256="1" * 64,
        desktop_launch_grant_sha256="2" * 64,
        grant_status="enabled",
        identity_verified=True,
        persistent_launch_grant_present=True,
        icon_asset_state="metadata_only",
        status="ready",
        issues=(),
    )
    blocked = DesktopCatalogItem(
        catalog_key="phi.blocked/fedcba9876543210",
        bundle_path=str(blocked_bundle),
        app_id="phi.blocked",
        app_version="1.0.0",
        desktop_name="Blocked App",
        desktop_icon="phios-app",
        desktop_entry_path=str((tmp_path / "phi-blocked.desktop").absolute()),
        desktop_app_plan_sha256="3" * 64,
        desktop_launch_grant_sha256="4" * 64,
        grant_status="enabled",
        identity_verified=True,
        persistent_launch_grant_present=True,
        icon_asset_state="metadata_only",
        status="blocked",
        issues=(DesktopCatalogIssue(code="installed_app_drift"),),
    )
    return DesktopCatalogSnapshot(
        desktop_root=str((tmp_path / "desktop").absolute()),
        applications_root=str((tmp_path / "applications").absolute()),
        install_root=str((tmp_path / "installed").absolute()),
        root_issues=(),
        items=(blocked, ready),
        item_count=2,
        ready_count=1,
        blocked_count=1,
    )


def test_launcher_catalog_adds_only_ready_governed_apps(monkeypatch, tmp_path):
    snapshot = _launcher_catalog_snapshot(tmp_path)
    monkeypatch.setattr(
        "phios.desktop.launcher.snapshot_desktop_catalog",
        lambda **_: snapshot,
    )

    actions = PhiLauncher().generate_governed_app_actions()

    assert len(actions) == 1
    assert actions[0].label == "Ready App · phi.ready 1.0.0"
    assert actions[0].argv == (
        "phi-app",
        "launch-desktop-bundle",
        str((tmp_path / "bundle with spaces").absolute()),
    )


def test_launcher_catalog_failure_degrades_to_builtin_actions(monkeypatch):
    def fail_catalog(**_kwargs):
        raise ValueError("catalog unavailable")

    monkeypatch.setattr(
        "phios.desktop.launcher.snapshot_desktop_catalog",
        fail_catalog,
    )

    launcher = PhiLauncher()
    assert launcher.generate_governed_app_actions() == []
    assert "phi status" in launcher.generate_phi_entries()


def test_launcher_uses_exact_argv_for_governed_app(monkeypatch, tmp_path):
    snapshot = _launcher_catalog_snapshot(tmp_path)
    monkeypatch.setattr(
        "phios.desktop.launcher.snapshot_desktop_catalog",
        lambda **_: snapshot,
    )
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    calls = []

    class Result:
        def __init__(self, stdout: str = "") -> None:
            self.stdout = stdout

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == "wofi":
            return Result("Ready App · phi.ready 1.0.0\n")
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    launcher = PhiLauncher()
    launcher.wofi_dir = tmp_path / "wofi"
    launcher.launch()

    assert calls[-1][0] == [
        "phi-app",
        "launch-desktop-bundle",
        str((tmp_path / "bundle with spaces").absolute()),
    ]
