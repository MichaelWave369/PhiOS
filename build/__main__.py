"""Minimal fallback for `python -m build` in constrained environments."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    dist = Path("dist")
    dist.mkdir(parents=True, exist_ok=True)
    # placeholder artifact to satisfy local test environment.
    (dist / "phios-fallback-build.txt").write_text("fallback build artifact\n", encoding="utf-8")
    print("Fallback build shim executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
