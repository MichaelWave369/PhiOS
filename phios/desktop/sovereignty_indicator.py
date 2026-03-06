"""Waybar sovereignty indicator JSON output."""

from __future__ import annotations

import json


def indicator_payload() -> dict[str, object]:
    return {
        "text": "SOV ON",
        "tooltip": "Sovereignty: ON\nMode: local-first",
        "class": "coherent",
        "percentage": 100,
    }


def main() -> int:
    print(json.dumps(indicator_payload()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
