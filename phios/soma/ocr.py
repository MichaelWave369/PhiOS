from __future__ import annotations

import math
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_+\-]{1,64}$")


class OcrEngineError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class OcrSpec:
    language: str = "eng"
    page_segmentation_mode: int = 6
    max_pixels: int = 16_777_216

    def to_dict(self) -> dict[str, str | int]:
        return {
            "language": self.language,
            "page_segmentation_mode": self.page_segmentation_mode,
            "max_pixels": self.max_pixels,
        }

    def validate(self) -> None:
        if not _LANGUAGE_PATTERN.fullmatch(self.language):
            raise OcrEngineError(
                "invalid_ocr_language",
                "OCR language must use only letters, numbers, _, +, or -",
            )
        if not 3 <= self.page_segmentation_mode <= 13:
            raise OcrEngineError(
                "invalid_page_segmentation_mode",
                "OCR page segmentation mode must be between 3 and 13",
            )
        if self.max_pixels <= 0:
            raise OcrEngineError(
                "invalid_pixel_budget",
                "OCR max_pixels must be positive",
            )


@dataclass(frozen=True, kw_only=True)
class OcrEngineResult:
    text: str
    confidences: tuple[float, ...]
    engine: str
    engine_version: str | None
    width: int
    height: int


class OcrProvider(Protocol):
    name: str

    def read(self, data: bytes, *, spec: OcrSpec) -> OcrEngineResult:
        ...


class TesseractOcrProvider:
    """Local OCR adapter. Output is interpretation, never source truth."""

    name = "tesseract-local"

    @staticmethod
    def _line_text(data: dict[str, list[object]]) -> str:
        raw_text = list(data.get("text", []))
        blocks = list(data.get("block_num", []))
        paragraphs = list(data.get("par_num", []))
        lines = list(data.get("line_num", []))

        groups: list[tuple[tuple[object, object, object], list[str]]] = []
        current_key: tuple[object, object, object] | None = None
        current_words: list[str] = []

        for index, raw in enumerate(raw_text):
            word = str(raw).strip()
            if not word:
                continue
            key = (
                blocks[index] if index < len(blocks) else 0,
                paragraphs[index] if index < len(paragraphs) else 0,
                lines[index] if index < len(lines) else index,
            )
            if current_key is not None and key != current_key:
                groups.append((current_key, current_words))
                current_words = []
            current_key = key
            current_words.append(word)

        if current_key is not None and current_words:
            groups.append((current_key, current_words))

        return "\n".join(" ".join(words) for _, words in groups)

    @staticmethod
    def _confidences(data: dict[str, list[object]]) -> tuple[float, ...]:
        values: list[float] = []
        for raw in list(data.get("conf", [])):
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value) and 0.0 <= value <= 100.0:
                values.append(value)
        return tuple(values)

    def read(self, data: bytes, *, spec: OcrSpec) -> OcrEngineResult:
        spec.validate()

        try:
            from PIL import Image
            import pytesseract
        except ImportError as exc:
            raise OcrEngineError(
                "ocr_engine_unavailable",
                "Pillow and pytesseract are required for local OCR",
            ) from exc

        try:
            image = Image.open(BytesIO(data))
            image.load()
        except Exception as exc:  # noqa: BLE001 - image decoder failures vary
            raise OcrEngineError(
                "ocr_decode_failed",
                "OCR source evidence could not be decoded as an image",
            ) from exc

        if image.width * image.height > spec.max_pixels:
            raise OcrEngineError(
                "ocr_input_too_large",
                f"OCR source exceeds max_pixels={spec.max_pixels}",
            )

        config = f"--psm {spec.page_segmentation_mode}"
        try:
            result = pytesseract.image_to_data(
                image,
                lang=spec.language,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
            version = str(pytesseract.get_tesseract_version())
        except Exception as exc:  # noqa: BLE001 - external executable errors vary
            raise OcrEngineError(
                "ocr_engine_failed",
                "Tesseract could not interpret the source evidence",
            ) from exc

        return OcrEngineResult(
            text=self._line_text(result),
            confidences=self._confidences(result),
            engine="tesseract",
            engine_version=version,
            width=image.width,
            height=image.height,
        )
