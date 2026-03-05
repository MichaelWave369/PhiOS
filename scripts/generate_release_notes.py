#!/usr/bin/env python3
"""Generate release notes from CHANGELOG.md with fallback support."""

from __future__ import annotations

from pathlib import Path

from phios import __version__


def extract_section(version: str, changelog_text: str) -> str:
    lines = changelog_text.splitlines()
    header = f"## v{version} —"
    start = -1
    for idx, line in enumerate(lines):
        if line.startswith(header):
            start = idx
            break
    if start == -1:
        return f"PhiOS v{version} — Sovereign Computing Shell"

    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## ") and body and not line.startswith(header):
            break
        body.append(line)
    return "\n".join(body).strip() or f"PhiOS v{version} — Sovereign Computing Shell"


def generate_release_notes() -> str:
    text = Path("CHANGELOG.md").read_text(encoding="utf-8") if Path("CHANGELOG.md").exists() else ""
    return extract_section(str(__version__), text)


def main() -> int:
    notes = generate_release_notes()
    print("release_notes<<EOF")
    print(notes)
    print("EOF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
