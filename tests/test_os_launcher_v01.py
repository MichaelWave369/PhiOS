from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "packaging/linux/session/phios-launcher"
WAYFIRE = REPO / "packaging/linux/session/wayfire.ini"
PKGBUILD = REPO / "packaging/arch/phishell/PKGBUILD"


def test_wayfire_uses_packaged_launcher_wrapper() -> None:
    config = WAYFIRE.read_text(encoding="utf-8")
    assert "binding_launcher = <super> KEY_SPACE" in config
    assert "command_launcher = phios-launcher" in config
    assert "command_launcher = wofi --show drun" not in config


def test_launcher_starts_drun_with_explicit_prompt_and_no_seed_search(tmp_path: Path) -> None:
    fake = tmp_path / "wofi"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    argv = json.loads(result.stdout)
    assert argv == ["--show", "drun", "--prompt", "Applications"]
    assert "--search" not in argv


def test_package_installs_launcher_and_advances_revision() -> None:
    package = PKGBUILD.read_text(encoding="utf-8")
    assert "pkgver=0.16.0" in package
    assert "pkgrel=5" in package
    assert (
        'install -Dm755 packaging/linux/session/phios-launcher '
        '"$pkgdir/usr/bin/phios-launcher"'
    ) in package
