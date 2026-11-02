"""External disposable PhiOS installed-guest ThinkTank HOLD observer.

Injected only by the QEMU test harness after a normal password login.
No network requests, service start, disk writes, install or authority mint.
This file is not included in the normal image.
"""
import json as _tt_json
import os as _tt_os
import re as _tt_re
import shutil as _tt_shutil
from pathlib import Path as _TtPath
from phios.apps.desktop_catalog import snapshot_desktop_catalog as _tt_snapshot

def observe_thinktank_held_guest(source: str, phase: int) -> None:
    app_id = "phios.thinktank-web"
    assert _tt_os.getuid() == 1000 and _tt_os.geteuid() == 1000
    assert _TtPath("/usr/share/phios/source-commit").read_text().strip() == source
    assert _TtPath("/sys/firmware/efi").is_dir()
    assert not _TtPath("/run/archiso/bootmnt").exists()
    assert "archisobasedir" not in _TtPath("/proc/cmdline").read_text()
    interfaces = sorted(p.name for p in _TtPath("/sys/class/net").iterdir())
    # QEMU itself also uses -nic none. This is an observation of the
    # specific guest's visible interfaces, not a general network sandbox.
    assert interfaces == ["lo"], "unexpected guest network interface"
    assert _tt_shutil.which("phi-app") is not None, "governed app CLI unavailable"
    home = _TtPath.home()
    desktop_root = home / ".local/share/phios/desktop-apps"
    applications_root = home / ".local/share/applications"
    install_root = home / ".phios/apps/installed"
    # A malformed/unreadable candidate app directory is *not* an acceptable
    # "no ready app" state. Refuse unknown partial installation.
    assert not (desktop_root / app_id).exists()
    assert not (desktop_root / app_id).is_symlink()
    assert not (install_root / app_id).exists()
    assert not (install_root / app_id).is_symlink()
    entry = applications_root / ("phios-" + app_id + ".desktop")
    assert not entry.exists() and not entry.is_symlink()
    catalog = _tt_snapshot(
        desktop_root=desktop_root,
        applications_root=applications_root,
        install_root=install_root,
    )
    assert not catalog.root_issues, "malformed desktop catalog root"
    assert not any(item.app_id == app_id for item in catalog.items), (
        "unexpected ThinkTank catalog entry"
    )
    boot_id = _TtPath("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-", "")
    assert _tt_re.fullmatch(r"[a-f0-9]{32}", boot_id)
    # This is strictly a negative, installed-VM preflight. A successful
    # observation never implies app installed, browser launch or licensing.
    print("PHIOS_THINKTANK_GUEST_HELD:" + _tt_json.dumps({
        "schema": "phios.thinktank_guest_hold_boot.v0.1",
        "source_commit": source,
        "boot_id": boot_id,
        "phase": phase,
        "uid": 1000,
        "guest_interface_names": interfaces,
        "guest_login_observed": True,
        "app_platform_cli_observed": True,
        "no_thinktank_install_or_desktop_grant_observed": True,
        "status": "HOLD_FOR_OPERATOR_REVIEW",
        "app_installed": False,
        "app_launch_verified": False,
        "app_rollback_verified": False,
        "guest_network_policy_attested": False,
        "redistribution_approved": False,
        "production_qualified": False,
        "external_done": False
    }, sort_keys=True), flush=True)
