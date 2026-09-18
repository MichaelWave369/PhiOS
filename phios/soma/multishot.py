from __future__ import annotations

from io import BytesIO
from typing import Protocol


class SharpnessScoreError(RuntimeError):
    pass


class FrameSharpnessScorer(Protocol):
    name: str

    def score(self, data: bytes) -> float:
        ...


class PillowEdgeSharpnessScorer:
    """Deterministic edge-energy heuristic used only for frame selection."""

    name = "pillow-edge-energy-v1"

    def score(self, data: bytes) -> float:
        try:
            from PIL import Image, ImageFilter, ImageStat
        except ImportError as exc:
            raise SharpnessScoreError(
                "Pillow sharpness scoring support is not installed"
            ) from exc

        try:
            image = Image.open(BytesIO(data)).convert("L")
            image.thumbnail((1024, 1024))
            edges = image.filter(ImageFilter.FIND_EDGES)
            mean = ImageStat.Stat(edges).mean[0]
        except Exception as exc:  # noqa: BLE001 - image decoder failures vary
            raise SharpnessScoreError("frame could not be scored") from exc

        return float(mean)
