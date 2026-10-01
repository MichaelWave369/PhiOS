"""Waybar sovereignty indicator JSON output."""

from __future__ import annotations

import json


def indicator_payload() -> dict[str, object]:
    return {
        "text": "UNVERIFIED",
        "tooltip": "Sovereignty: unverified\nLocal-first is a design goal, not an attested security state.",
        "class": "unverified",
        "percentage": 0,
    }


def main() -> int:
    print(json.dumps(indicator_payload()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
