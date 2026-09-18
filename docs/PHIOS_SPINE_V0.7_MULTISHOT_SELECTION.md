# PhiOS Spine v0.7 - SOMA Multi-Shot Native Selection

Spine v0.7 adds bounded multi-shot screen acquisition and deterministic selection of the clearest valid native frame.

## Why multi-shot comes before deblur

When the same selected region can be observed more than once, selecting a clearer native observation preserves a stronger provenance boundary than modifying pixels immediately.

v0.7 therefore prefers:

```text
observe again -> preserve every frame -> score -> select native frame
```

before introducing any deblur or sharpening transform.

## Authority

Burst acquisition requires both:

- `perception.screen.capture`
- `perception.screen.multishot`

Repeated capture is a separate capability from one-time capture.

## Bounds

- frame_count is limited to 2 through 8
- every frame uses the same explicitly selected region
- per-frame pixel limits still apply
- the entire burst also has a total pixel budget
- capture failures do not trigger unbounded retries

## Evidence

Every non-empty returned frame is preserved in the content-addressed evidence store, including contract-invalid frames such as a dimension mismatch.

Invalid frames are not eligible for selection.

Identical byte-for-byte frames may resolve to the same content-addressed evidence object, while their frame records remain distinct by index.

## Selection metric

The default optional implementation uses a deterministic Pillow edge-energy heuristic.

It is a selection heuristic, not a truth score and not a semantic quality judgment.

The receipt records:

- every preserved burst evidence reference
- one record per requested frame
- the score for each valid frame
- the selection method
- the selected evidence reference

Ties are resolved deterministically in favor of the earliest valid frame.

## Partial bursts

If some requested frames fail but at least one valid frame remains, PhiOS can still select a native observation, but the PerceptionReceipt is DEGRADED and records `partial_burst`.

If no valid frame exists, no observation is fabricated.

## No fusion

v0.7 does not merge, average, interpolate, or synthesize frames.

The selected observation remains one of the original native captures.

## CLI

```bash
phi-spine \
  --allow perception.screen.capture \
  --allow perception.screen.multishot \
  perceive-screen-burst \
  --x 100 --y 100 --width 800 --height 600 \
  --frames 3
```

## Still excluded

No deblur, frame fusion, OCR, vision-model interpretation, or Reality Gate promotion is added in v0.7.
