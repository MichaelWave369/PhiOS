# PhiOS Spine v0.9 - OCR Interpretation

Spine v0.9 adds the first symbolic interpretation layer to SOMA.

```text
pixels -> OCR engine -> OcrReceipt -> derived text evidence
```

OCR requires:

`perception.ocr.read`

The output text is stored separately from the source image and is explicitly labeled as interpretation, not truth.

See `docs/PHIOS_SPINE_V0.9_OCR_INTERPRETATION.md`.
