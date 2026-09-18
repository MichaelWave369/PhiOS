# PhiOS Spine v0.8 - Deterministic Screen Sharpening

Spine v0.8 adds the first pixel-changing SOMA image enhancement.

It is deliberately called **sharpening**, not truth recovery and not guaranteed deblurring.

## Authority

Enhancement requires the explicit grant:

`perception.screen.enhance`

This is separate from live capture, multi-shot capture, and crop/enlargement recovery.

## Transformation

v0.8 supports one method:

`unsharp_mask`

The optional Pillow provider applies a bounded unsharp-mask transform and emits a new PNG evidence object.

The source evidence is never overwritten.

## Parameters

- radius: 0.1 through 5.0
- percent: 1 through 500
- threshold: 0 through 255
- max_pixels: positive bounded input pixel budget

The output must retain the source dimensions.

## Evidence chain

```text
source evidence
      ↓
deterministic unsharp mask
      ↓
derived evidence
```

The PerceptionReceipt records:

- input_evidence_ref
- enhancement_method
- enhancement_parameters
- enhancement_backend
- derived_evidence_refs
- observation_evidence_ref
- derivation_chain

## Epistemic boundary

Sharpening can increase local edge contrast.

It does **not** prove that newly visible-looking edge structure represents lost source information.

Receipts therefore carry explicit limitations:

- derived_observation_not_truth
- enhancement_may_amplify_artifacts
- enhancement_does_not_recover_lost_information
- derived_evidence_never_replaces_source
- enhancement_does_not_increase_authority
- no_semantic_interpretation

## Provider reproducibility

The live provider records the Pillow version in the successful enhancement backend string.

The algorithm and parameters are deterministic for a fixed implementation environment, but byte-identical replay across different image-library versions is not claimed.

The output SHA-256 remains the authoritative record of what was actually produced.

## Failure behavior

Invalid parameters and oversized inputs are BLOCKED.

Decode/backend failures are QUARANTINED.

If a provider returns output that violates the enhancement contract, such as changed dimensions, the returned bytes may be preserved as quarantined derived evidence but are not promoted as an observation.

## CLI

```bash
phi-spine \
  --allow perception.screen.enhance \
  enhance-screen \
  --evidence-ref evidence:sha256:<digest> \
  --radius 1.5 \
  --percent 150 \
  --threshold 3
```

## Still excluded

No learned deblur model, super-resolution, frame fusion, OCR, vision-model interpretation, or Reality Gate promotion is added in v0.8.
