"""Prompt helpers."""

from __future__ import annotations

from phios.display.colors import colorize_phi


def build_prompt() -> str:
    return colorize_phi("φ> ")
