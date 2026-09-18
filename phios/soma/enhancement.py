from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol


class ScreenEnhancementError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class ScreenEnhancementSpec:
    method: str = "unsharp_mask"
    radius: float = 1.5
    percent: int = 150
    threshold: int = 3
    max_pixels: int = 16_777_216

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "method": self.method,
            "radius": self.radius,
            "percent": self.percent,
            "threshold": self.threshold,
            "max_pixels": self.max_pixels,
        }

    def validate(self) -> None:
        if self.method != "unsharp_mask":
            raise ScreenEnhancementError(
                "unsupported_enhancement_method",
                "only unsharp_mask is supported in v0.8",
            )
        if not 0.1 <= self.radius <= 5.0:
            raise ScreenEnhancementError(
                "invalid_radius",
                "unsharp radius must be between 0.1 and 5.0",
            )
        if not 1 <= self.percent <= 500:
            raise ScreenEnhancementError(
                "invalid_percent",
                "unsharp percent must be between 1 and 500",
            )
        if not 0 <= self.threshold <= 255:
            raise ScreenEnhancementError(
                "invalid_threshold",
                "unsharp threshold must be between 0 and 255",
            )
        if self.max_pixels <= 0:
            raise ScreenEnhancementError(
                "invalid_pixel_budget",
                "max_pixels must be positive",
            )


@dataclass(frozen=True, kw_only=True)
class EnhancedFrame:
    data: bytes
    input_width: int
    input_height: int
    output_width: int
    output_height: int
    backend: str
    media_type: str = "image/png"
    suffix: str = ".png"


class ScreenEnhancementProvider(Protocol):
    name: str

    def enhance(self, data: bytes, *, spec: ScreenEnhancementSpec) -> EnhancedFrame:
        ...


class PillowUnsharpMaskProvider:
    """Bounded deterministic sharpening. This is not lost-information recovery."""

    name = "pillow-unsharp-mask-v1"

    def enhance(self, data: bytes, *, spec: ScreenEnhancementSpec) -> EnhancedFrame:
        spec.validate()

        try:
            import PIL
            from PIL import Image, ImageFilter
        except ImportError as exc:
            raise ScreenEnhancementError(
                "backend_unavailable",
                "Pillow enhancement support is not installed",
            ) from exc

        try:
            image = Image.open(BytesIO(data))
            image.load()
        except Exception as exc:  # noqa: BLE001 - decoder failures vary
            raise ScreenEnhancementError(
                "enhancement_decode_failed",
                "source evidence could not be decoded as an image",
            ) from exc

        if image.width * image.height > spec.max_pixels:
            raise ScreenEnhancementError(
                "input_too_large",
                f"input image exceeds max_pixels={spec.max_pixels}",
            )

        enhanced = image.filter(
            ImageFilter.UnsharpMask(
                radius=spec.radius,
                percent=spec.percent,
                threshold=spec.threshold,
            )
        )
        output = BytesIO()
        enhanced.save(output, format="PNG")
        return EnhancedFrame(
            data=output.getvalue(),
            input_width=image.width,
            input_height=image.height,
            output_width=enhanced.width,
            output_height=enhanced.height,
            backend=f"{self.name}/Pillow-{PIL.__version__}",
        )
