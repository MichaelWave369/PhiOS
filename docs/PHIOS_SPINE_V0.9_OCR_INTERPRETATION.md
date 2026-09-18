# PhiOS Spine v0.9 - OCR Interpretation Layer

Spine v0.9 introduces the first symbolic interpretation layer in SOMA.

Until v0.9, the North Gate acquired or transformed observations without attempting to assign textual meaning to pixels.

OCR crosses that boundary deliberately.

## Epistemic boundary

```text
image evidence
      ↓
OCR engine
      ↓
symbolic interpretation
      ↓
OcrReceipt
      ↓
derived text evidence
```

The OCR output is not treated as native evidence and is not treated as truth.

It is an engine-produced interpretation linked to the exact image evidence that was read.

## Separate receipt

v0.9 introduces `OcrReceipt` instead of overloading `PerceptionReceipt`.

The distinction is intentional:

- `PerceptionReceipt` records acquisition and image/text transformations.
- `OcrReceipt` records symbolic text inferred from image evidence.

## Authority

OCR requires the explicit grant:

`perception.ocr.read`

The grant is separate from screen capture, multi-shot capture, recovery, and sharpening.

Permission to possess image evidence is not automatically permission to extract text from it.

## Output evidence

When OCR returns non-empty text, PhiOS stores the exact OCR output as a separate content-addressed `.txt` evidence object.

The OcrReceipt links:

- source_evidence_ref
- output_evidence_ref
- engine
- engine_version
- language
- page segmentation mode
- text SHA-256
- character count
- token count
- confidence summary

The source image is unchanged.

## Confidence

OCR confidence is recorded as engine metadata.

It is explicitly **not** represented as probability that the text is true.

The receipt records mean, minimum, maximum, and count for valid confidence values when available.

Text without confidence metadata is DEGRADED rather than silently treated as fully evidenced.

## Empty interpretation

If the OCR engine returns no text:

- status = DEGRADED
- no text evidence object is created
- limitation = `no_text_detected`

PhiOS does not invent missing characters.

## Default local engine

The optional live adapter uses local Tesseract through `pytesseract`.

Install OCR support with:

```bash
pip install -e '.[ocr]'
```

The Tesseract executable itself must also be installed on the host.

v0.9 accepts PNG evidence only.

## CLI

```bash
phi-spine \
  --allow perception.ocr.read \
  ocr-screen \
  --evidence-ref evidence:sha256:<digest> \
  --language eng \
  --psm 6
```

The CLI prints the OCR text because the operator explicitly requested an OCR operation. Python result serialization hides the text by default unless `include_text=True` is requested.

## Limitations frozen into every successful OCR receipt

- ocr_output_is_interpretation
- ocr_text_not_truth
- confidence_is_engine_metadata_not_probability_of_truth
- source_evidence_unchanged
- ocr_does_not_increase_authority
- no_reality_gate_promotion

## Still excluded

OCR output is not automatically:

- accepted as fact
- promoted to memory
- used for actions
- reconciled against other evidence
- passed by the Reality Gate

Those are later contracts.
