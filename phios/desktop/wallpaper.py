"""Sacred geometry wallpaper generation and application utilities."""

from __future__ import annotations

import math
import shutil
import time
from pathlib import Path

from phios.desktop.wayfire_config import PHI, PHIOS_COLORS
from phios.core.lt_engine import compute_lt


class SacredGeometryWallpaper:
    """Generate and optionally apply PhiOS wallpaper assets."""

    def generate(
        self,
        width: int = 1920,
        height: int = 1080,
        show_lt: bool = True,
        output_path: str = "~/.phi/wallpaper.png",
    ) -> str:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (width, height), PHIOS_COLORS["deep"])
            draw = ImageDraw.Draw(image, "RGBA")

            # radial-ish layers / overlays
            cx, cy = width // 2, height // 2
            for r in range(min(width, height) // 6, min(width, height) // 2, 40):
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(201, 168, 76, 35), width=1)

            for angle in range(0, 360, 30):
                x = cx + int(math.cos(math.radians(angle)) * (min(width, height) * 0.35))
                y = cy + int(math.sin(math.radians(angle)) * (min(width, height) * 0.35))
                draw.line((cx, cy, x, y), fill=(46, 168, 168, 50), width=1)

            spiral_steps = 34
            points: list[tuple[int, int]] = []
            radius = 5.0
            theta = 0.0
            for _ in range(spiral_steps):
                x = cx + int(radius * math.cos(theta))
                y = cy + int(radius * math.sin(theta))
                points.append((x, y))
                radius *= 1.05
                theta += math.pi / PHI
            if len(points) > 1:
                draw.line(points, fill=(201, 168, 76, 120), width=2)

            draw.text((cx - 8, cy - 10), "φ", fill=(232, 238, 245, 220))
            if show_lt:
                lt = float(compute_lt().get("lt", 0.5))
                draw.text((20, height - 40), f"L(t): {lt:.3f}", fill=(169, 176, 195, 220))

            image.save(path)
            return str(path)
        except Exception:
            # Pillow missing or draw failure fallback.
            path.write_text(f"PHIOS_SOLID_FALLBACK {PHIOS_COLORS['deep']}\n", encoding="utf-8")
            return str(path)

    def set_as_wallpaper(self, path: str) -> bool:
        target = Path(path).expanduser()
        if not target.exists():
            return False
        swaybg = shutil.which("swaybg")
        wbg = shutil.which("wbg")
        if swaybg:
            return bool(shutil.which("swaybg"))
        if wbg:
            return bool(shutil.which("wbg"))
        return False

    def regenerate_on_lt_change(self, threshold: float = 0.1, iterations: int | None = None) -> None:
        prev = float(compute_lt().get("lt", 0.5))
        loops = 0
        try:
            while True:
                loops += 1
                current = float(compute_lt().get("lt", 0.5))
                if abs(current - prev) > threshold:
                    self.generate(show_lt=True)
                    prev = current
                if iterations is not None and loops >= iterations:
                    return
                time.sleep(2)
        except KeyboardInterrupt:
            return
