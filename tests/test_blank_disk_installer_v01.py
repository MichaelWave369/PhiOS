from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

FILE = Path(__file__).resolve().parents[1] / "packaging/linux/installer/install.py"
spec = importlib.util.spec_from_file_location("phios_blank_disk_installer", FILE)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def _disk(**changes: Any) -> dict[str, Any]:
    return {"path": "/dev/vda", "type": "disk", "ro": False, "size": 32 * 1024**3,
            "serial": "test-only-disposable-disk", "model": "Virtual disk", "maj:min": "252:0",
            "mountpoints": [None], "fstype": None, "pttype": None, **changes}


@pytest.mark.parametrize("changes,busy,signatures", [
    ({"children": [{"path": "/dev/vda1"}]}, False, []),
    ({"mountpoints": ["/"]}, False, []),
    ({}, True, []),
    ({}, False, [{"type": "gpt"}]),
    ({"fstype": "btrfs"}, False, []),
    ({"type": "loop"}, False, []),
    ({"ro": True}, False, []),
    ({"serial": None}, False, []),
    ({"serial": "control\x1bsequence"}, False, []),
    ({"path": "/dev/disk/by-id/a"}, False, []),
    ({"size": 8 * 1024**3}, False, []),
])
def test_unsafe_targets_are_refused(changes: dict[str, Any], busy: bool, signatures: list[Any]) -> None:
    with pytest.raises(ValueError):
        installer.validate_inventory(_disk(**changes), signatures, busy=busy)


def test_confirmation_binds_exact_identity_source_account_and_layout() -> None:
    identity = installer.validate_inventory(_disk(), [], busy=False)
    plan, phrase = installer.confirmation(identity, "a" * 40, "operator", "phios")
    assert phrase.startswith("INSTALL /dev/vda ")
    for changed in [{**identity, "serial_or_wwn": "replaced"}, {**identity, "size_bytes": 64 * 1024**3}]:
        assert installer.confirmation(changed, "a" * 40, "operator", "phios")[1] != phrase
    assert installer.confirmation(identity, "b" * 40, "operator", "phios")[1] != phrase
    assert installer.confirmation(identity, "a" * 40, "someone", "phios")[1] != phrase
    serial_plan, serial_phrase = installer.confirmation(identity, 'a'*40, 'operator', 'phios', serial_console=True)
    assert serial_phrase != phrase and serial_plan['serial_console_password_login'] is True
    assert plan['serial_console_password_login'] is False
    assert plan["encrypted"] is False and plan["firmware_variables_changed"] is False
    assert plan["release_ready"] is False


def test_signature_free_hidden_data_is_still_refused_without_writes(tmp_path: Path) -> None:
    disk = tmp_path / "read-only-test-image"
    data = bytes(1024**2) + b"important unsigned data" + bytes(1024**2)
    disk.write_bytes(data)
    with pytest.raises(ValueError, match="not fully zeroed"):
        installer.verify_zeroed(str(disk), len(data))
    assert disk.read_bytes() == data
    disk.write_bytes(bytes(len(data)))
    installer.verify_zeroed(str(disk), len(data))
    with pytest.raises(ValueError, match="size changed"):
        installer.verify_zeroed(str(disk), len(data) + 1)


def test_changed_disk_after_confirmation_never_reaches_write_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = installer.validate_inventory(_disk(), [], busy=False)
    plan, _ = installer.confirmation(identity, "a" * 40, "operator", "phios")
    monkeypatch.setattr(installer, "inventory", lambda _: {**identity, "serial_or_wwn": "changed"})
    monkeypatch.setattr(installer, "run", lambda *args, **kwargs: pytest.fail(f"unexpected command {args}"))
    monkeypatch.setattr(installer.tempfile, "mkdtemp", lambda **kwargs: pytest.fail("unexpected writes"))
    with pytest.raises(ValueError, match="changed after review"):
        installer.apply(plan, "synthetic-test-password")


def test_rejected_confirmation_never_calls_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.sfs"
    source.touch()
    identity_file = tmp_path / "source-commit"
    identity_file.write_text("a" * 40)
    monkeypatch.setattr(installer, "SOURCE", source)
    monkeypatch.setattr(installer, "IDENTITY", identity_file)
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda p: True if str(p) == "/sys/firmware/efi" else original_is_dir(p))
    monkeypatch.setattr(installer.shutil, "which", lambda *args, **kwargs: "/usr/bin/unused")
    monkeypatch.setattr(installer, "inventory", lambda _: installer.validate_inventory(_disk(), [], busy=False))
    monkeypatch.setattr(installer, "verify_zeroed", lambda *args: None)
    monkeypatch.setattr(installer.getpass, "getpass", lambda _: "synthetic-test-password")
    monkeypatch.setattr(installer.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(installer.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(installer.sys, "argv", ["phios-install", "--disk", "/dev/vda", "--username", "operator"])
    monkeypatch.setattr("builtins.input", lambda _: "cancel")
    monkeypatch.setattr(installer, "apply", lambda *args: pytest.fail("disk install must not begin"))
    assert installer.main() == 1
    assert "confirmation did not match" in capsys.readouterr().err


def test_generated_file_replaces_absolute_source_symlink_without_following_it(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("preserve")
    root = tmp_path / "target"
    (root / "etc").mkdir(parents=True)
    (root / "etc/os-release").symlink_to(unrelated)
    installer.write(root, "etc/os-release", "ID=phios\n")
    assert unrelated.read_text() == "preserve"
    assert not (root / "etc/os-release").is_symlink()
    assert (root / "etc/os-release").read_text() == "ID=phios\n"


@pytest.mark.parametrize("username,hostname", [("root", "phios"), ("phios", "phios"),
                                               ("operator;id", "phios"), ("operator", "host\nname")])
def test_account_inputs_cannot_select_live_accounts_or_inject_commands(username: str, hostname: str) -> None:
    with pytest.raises(ValueError):
        installer.validate_account(username, hostname)
