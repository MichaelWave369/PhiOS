# PhiOS Spine v0.7 - SOMA Multi-Shot Native Selection

Spine v0.7 captures a bounded burst of the same explicitly selected screen region, preserves every non-empty native frame, scores valid frames with a deterministic sharpness heuristic, and selects the best native observation.

It requires both:

`perception.screen.capture`

and:

`perception.screen.multishot`

No frames are fused and no pixels are invented.

See `docs/PHIOS_SPINE_V0.7_MULTISHOT_SELECTION.md`.
