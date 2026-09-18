# PhiOS Spine v0.6 - SOMA Acuity Recovery

Spine v0.6 separates screen-image recovery from live screen acquisition.

The native screenshot remains immutable evidence. Recovery produces new content-addressed evidence objects linked back to the native source.

## Recovery authority

Reading and transforming preserved screen evidence requires the explicit grant:

`perception.screen.recover`

This is separate from the live capture grant:

`perception.screen.capture`

A system that can capture a screen is not automatically authorized to revisit sensitive historical screen evidence later.

## Recovery chain

```text
native evidence
    ↓
tight crop
    ↓
derived evidence
    ↓
native enlargement
    ↓
derived evidence
```

Every stage has its own SHA-256 evidence reference.

The native evidence is never overwritten.

## Tight crop

A crop uses coordinates relative to the preserved native image, not desktop coordinates.

The crop must have positive dimensions and remain inside the decoded native image.

## Native enlargement

Native enlargement is deterministic nearest-neighbor pixel replication.

It does not use a generative model, super-resolution model, hallucinated pixels, or semantic fill.

Scale is limited to 1 through 4 and the output pixel count is bounded.

## Authority and epistemics

Recovery can improve inspectability.

It cannot improve authority.

The PerceptionReceipt therefore records:

- the original native evidence reference
- every derived evidence reference
- the final observation evidence reference
- the exact derivation chain
- the recovery backend
- the recovery steps
- limitations stating that derived evidence does not replace native evidence

## Failure behavior

Missing grants and invalid parameters are BLOCKED.

Malformed native image evidence or backend failures are QUARANTINED.

No failed recovery creates a derived observation.

## CLI

Crop only:

```bash
phi-spine \
  --allow perception.screen.recover \
  recover-screen \
  --evidence-ref evidence:sha256:<digest> \
  --crop-x 40 --crop-y 20 --crop-width 320 --crop-height 180
```

Crop and enlarge:

```bash
phi-spine \
  --allow perception.screen.recover \
  recover-screen \
  --evidence-ref evidence:sha256:<digest> \
  --crop-x 40 --crop-y 20 --crop-width 320 --crop-height 180 \
  --scale 2
```

## Still excluded

No OCR, deblur, multi-shot fusion, vision-model interpretation, or Reality Gate promotion is added in v0.6.
