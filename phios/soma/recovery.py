from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from .screen import CapturedFrame


class ScreenRecoveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class ScreenCrop:
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

    def validate_shape(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ScreenRecoveryError(
                "invalid_crop",
                "crop coordinates must be non-negative within native evidence",
            )
        if self.width <= 0 or self.height <= 0:
            raise ScreenRecoveryError(
                "invalid_crop",
                "crop width and height must be positive",
            )


@dataclass(frozen=True, kw_only=True)
class ScreenRecoveryFrames:
    cropped: CapturedFrame | None = None
    enlarged: CapturedFrame | None = None

    @property
    def final(self) -> CapturedFrame:
        if self.enlarged is not None:
            return self.enlarged
        if self.cropped is not None:
            return self.cropped
        raise ScreenRecoveryError("no_derived_frame", "recovery produced no derived frame")


class ScreenRecoveryProvider(Protocol):
    name: str

    def recover(
        self,
        data: bytes,
        *,
        crop: ScreenCrop | None,
        scale: int,
        max_output_pixels: int,
    ) -> ScreenRecoveryFrames:
        ...


class PillowScreenRecoveryProvider:
    """Deterministic crop and nearest-neighbor enlargement for PNG evidence."""

    name = "pillow-native-recovery"

    @staticmethod
    def _encode_png(image: object) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")  # type: ignore[attr-defined]
        return output.getvalue()

    def recover(
        self,
        data: bytes,
        *,
        crop: ScreenCrop | None,
        scale: int,
        max_output_pixels: int,
    ) -> ScreenRecoveryFrames:
        if crop is None and scale == 1:
            raise ScreenRecoveryError(
                "no_recovery_requested",
                "request a tight crop, enlargement, or both",
            )
        if scale < 1 or scale > 4:
            raise ScreenRecoveryError(
                "invalid_scale",
                "native enlargement scale must be between 1 and 4",
            )
        if max_output_pixels <= 0:
            raise ScreenRecoveryError(
                "invalid_pixel_budget",
                "max_output_pixels must be positive",
            )

        try:
            from PIL import Image
        except ImportError as exc:
            raise ScreenRecoveryError(
                "backend_unavailable",
                "Pillow recovery support is not installed",
            ) from exc

        try:
            image = Image.open(BytesIO(data))
            image.load()
        except Exception as exc:  # noqa: BLE001 - Pillow decode errors vary
            raise ScreenRecoveryError(
                "recovery_decode_failed",
                "native screen evidence could not be decoded as an image",
            ) from exc

        working = image
        cropped_frame: CapturedFrame | None = None
        enlarged_frame: CapturedFrame | None = None

        if crop is not None:
            crop.validate_shape()
            if crop.x + crop.width > image.width or crop.y + crop.height > image.height:
                raise ScreenRecoveryError(
                    "crop_out_of_bounds",
                    "tight crop exceeds the native evidence bounds",
                )
            working = image.crop(
                (
                    crop.x,
                    crop.y,
                    crop.x + crop.width,
                    crop.y + crop.height,
                )
            )
            cropped_frame = CapturedFrame(
                data=self._encode_png(working),
                width=working.width,
                height=working.height,
                backend=self.name,
            )

        if scale > 1:
            output_width = working.width * scale
            output_height = working.height * scale
            if output_width * output_height > max_output_pixels:
                raise ScreenRecoveryError(
                    "output_too_large",
                    f"derived image exceeds max_output_pixels={max_output_pixels}",
                )
            enlarged = working.resize(
                (output_width, output_height),
                resample=Image.Resampling.NEAREST,
            )
            enlarged_frame = CapturedFrame(
                data=self._encode_png(enlarged),
                width=enlarged.width,
                height=enlarged.height,
                backend=self.name,
            )

        return ScreenRecoveryFrames(
            cropped=cropped_frame,
            enlarged=enlarged_frame,
        )
