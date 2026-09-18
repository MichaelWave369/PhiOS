# PhiOS Spine v0.8 - Deterministic Screen Sharpening

Spine v0.8 adds the first pixel-changing SOMA recovery derivative.

It uses bounded deterministic unsharp masking and requires:

`perception.screen.enhance`

The source evidence is never replaced. The sharpened output becomes a new evidence object with its own hash and explicit derivation chain.

This is **not** presented as recovery of lost information.

See `docs/PHIOS_SPINE_V0.8_DERIVED_SHARPENING.md`.
