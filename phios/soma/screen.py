from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol


class ScreenCaptureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class ScreenRegion:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    def validate(self, *, max_pixels: int) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ScreenCaptureError(
                "invalid_region",
                "screen region width and height must be positive",
            )
        if max_pixels <= 0:
            raise ScreenCaptureError("invalid_pixel_budget", "max_pixels must be positive")
        if self.width * self.height > max_pixels:
            raise ScreenCaptureError(
                "region_too_large",
                f"screen region exceeds max_pixels={max_pixels}",
            )


@dataclass(frozen=True, kw_only=True)
class CapturedFrame:
    data: bytes
    width: int
    height: int
    backend: str
    media_type: str = "image/png"
    suffix: str = ".png"


class ScreenCaptureProvider(Protocol):
    name: str

    def capture(self, region: ScreenRegion) -> CapturedFrame:
        ...


class PillowScreenCaptureProvider:
    """Optional real desktop capture backend using Pillow ImageGrab."""

    name = "pillow-imagegrab"

    def capture(self, region: ScreenRegion) -> CapturedFrame:
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise ScreenCaptureError(
                "backend_unavailable",
                "Pillow screen capture support is not installed",
            ) from exc

        bbox = (
            region.x,
            region.y,
            region.x + region.width,
            region.y + region.height,
        )
        try:
            image = ImageGrab.grab(bbox=bbox)
        except Exception as exc:  # noqa: BLE001 - OS capture backends vary
            raise ScreenCaptureError(
                "capture_failed",
                "screen capture backend could not acquire the selected region",
            ) from exc

        output = BytesIO()
        image.save(output, format="PNG")
        return CapturedFrame(
            data=output.getvalue(),
            width=image.width,
            height=image.height,
            backend=self.name,
        )
