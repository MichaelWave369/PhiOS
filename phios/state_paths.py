"""Packaged Linux state location, with explicit legacy compatibility."""
from __future__ import annotations

import os
from pathlib import Path


def configured_state_root() -> Path:
    value = os.environ.get("PHIOS_STATE_ROOT")
    if value is None:
        return Path.home() / ".phios"
    path = Path(value).expanduser()
    if not value.strip() or not path.is_absolute() or path == Path(path.anchor):
        raise ValueError("PHIOS_STATE_ROOT must be an explicit absolute state directory")
    return path


def memory_config_path() -> Path:
    if "PHIOS_STATE_ROOT" not in os.environ:
        return Path.home() / ".phios/memory/config.json"
    value = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))).expanduser()
    if not value.is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be absolute")
    return value / "phios/memory.json"
