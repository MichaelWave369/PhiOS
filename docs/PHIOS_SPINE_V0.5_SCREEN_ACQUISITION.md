# PhiOS Spine v0.5 - SOMA Screen Region Acquisition

Spine v0.5 adds explicit desktop screen-region acquisition to the SOMA North Gate.

## Privacy and authority rule

Screen capture is denied by default.

The Phi Core authority envelope must contain the explicit grant:

`perception.screen.capture`

The operator must also specify the region to acquire.

This establishes the rule:

> Visibility is not permission to observe.

## Transaction

```text
explicit capture grant
        +
selected region
        ↓
MandalaPacket(PERCEPTION)
        ↓
North Gate policy
        ↓
native screen capture
        ↓
content-addressed evidence
        ↓
PerceptionReceipt
```

No OCR, vision model, semantic interpretation, or action authority is created by the capture.

## Acuity recovery

v0.5 implements the first recovery rung:

1. native capture
2. reacquire the exact same region after a capture failure

If the first capture succeeds, acuity is `native`.

If reacquisition is required and succeeds, acuity is `recovered` and the receipt records `reacquire_same_region`.

If all capture attempts fail, the PerceptionReceipt is `DEGRADED` with acuity `unavailable`. PhiOS does not fabricate an observation.

## Capture contract

- width and height must be positive
- capture area is bounded by `max_pixels`
- reacquire attempts are bounded from 0 to 2
- accepted native frames must be PNG
- returned dimensions must match the requested region
- malformed or mismatched frames are quarantined if native bytes exist
- evidence remains local in the content-addressed evidence store

Negative x/y coordinates are allowed because multi-monitor desktops may place a display left of or above the primary display.

## Backend

The default live backend is Pillow ImageGrab and is optional.

Install screen support with:

```bash
pip install -e '.[screen]'
```

The provider is lazy-loaded. If the backend or operating-system capture facility is unavailable, the attempt is receipted as unavailable rather than crashing the perception contract.

## CLI

```bash
phi-spine \
  --allow perception.screen.capture \
  perceive-screen \
  --x 100 --y 100 --width 800 --height 600
```

## Deliberate exclusions

v0.5 does not add:

- OCR
- native enlargement
- deblur
- multi-shot fusion
- model-based image interpretation
- automatic full-desktop capture
- background capture
- continuous monitoring

Those stages can be layered on later only after native provenance and authority remain intact.
