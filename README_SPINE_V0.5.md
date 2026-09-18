# PhiOS Spine v0.5 - SOMA Screen Region Acquisition

Spine v0.5 gives the North Gate its first explicit desktop screen-region acquisition path.

Screen capture is denied by default and requires the explicit grant:

`perception.screen.capture`

Selected region -> native capture -> local evidence -> PerceptionReceipt.

The first acuity recovery rung is also implemented: a failed native capture may reacquire the exact same region once by default. No OCR or model interpretation is performed.

See `docs/PHIOS_SPINE_V0.5_SCREEN_ACQUISITION.md`.
