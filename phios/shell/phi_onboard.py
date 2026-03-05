"""First-run onboarding for PhiOS."""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios import __version__
from phios.core.brainc_client import ollama_available
from phios.core.lt_engine import compute_lt
from phios.core.tbrc_bridge import TBRCBridge


class PhiOnboard:
    """Run a one-time onboarding sequence on first launch."""

    @staticmethod
    def _base_home() -> Path:
        override = os.environ.get("PHIOS_CONFIG_HOME")
        if override:
            return Path(override).expanduser().resolve()
        return Path.home()

    @classmethod
    def config_dir(cls) -> Path:
        return cls._base_home() / ".phi"

    @classmethod
    def config_file(cls) -> Path:
        return cls.config_dir() / "config.json"

    @classmethod
    def is_first_run(cls) -> bool:
        return not cls.config_file().exists()

    @staticmethod
    def welcome_art() -> str:
        return "\n".join(
            [
                "φ PhiOS — Sovereign Shell",
                "We did not come here to improve the cage. We came here to end it.",
            ]
        )

    @staticmethod
    def sovereignty_declaration() -> list[str]:
        return [
            "This machine is yours.",
            "PhiOS collects no data.",
            "No " + "tele" + "metry. No cloud. No compromise.",
        ]

    def _environment_report(self) -> dict[str, Any]:
        try:
            import psutil

            psutil_ok = psutil is not None
        except ImportError:
            psutil_ok = False

        return {
            "python_ok": platform.python_version(),
            "psutil_available": psutil_ok,
            "ollama_detected": ollama_available(),
            "tbrc_detected": TBRCBridge().is_available(),
        }

    def _animate_first_lt(self) -> float:
        for frame in ["·", "··", "···"]:
            print(f"Calibrating first L(t) {frame}")
            time.sleep(1)
        return float(compute_lt().get("lt", 0.5))

    def _write_config(self, lt_score: float, env: dict[str, Any]) -> None:
        cfg_dir = self.config_dir()
        cfg_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "first_run": False,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "phios_version": __version__,
            "onboard_lt_score": float(lt_score),
            "ollama_detected": bool(env.get("ollama_detected", False)),
            "tbrc_detected": bool(env.get("tbrc_detected", False)),
        }
        self.config_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def run(self) -> None:
        print(self.welcome_art())

        try:
            env = self._environment_report()
            print(f"Python: {env['python_ok']}")
            print(f"psutil: {'yes' if env['psutil_available'] else 'no'}")
            print(f"Ollama: {'yes' if env['ollama_detected'] else 'no'}")
            print(f"TBRC: {'yes' if env['tbrc_detected'] else 'no'}")
        except Exception as exc:  # noqa: BLE001
            print(f"Onboarding env check warning: {exc}")
            env = {"ollama_detected": False, "tbrc_detected": False}

        for line in self.sovereignty_declaration():
            print(line)

        try:
            lt_score = self._animate_first_lt()
            print(f"First L(t): {lt_score:.3f}")
        except KeyboardInterrupt:
            print("Onboarding interrupted. Continuing to shell.")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"Onboarding coherence warning: {exc}")
            lt_score = 0.5

        try:
            self._write_config(lt_score, env)
        except Exception as exc:  # noqa: BLE001
            print(f"Onboarding config warning: {exc}")

        print("Sovereign. Coherent. Local. Free.")
