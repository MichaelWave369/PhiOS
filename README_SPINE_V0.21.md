# PhiOS Spine v0.21 - Timed Mixed Observations

Spine v0.21 adds explicit minimum temporal spacing to bounded repeated mixed-contract verification.

```text
same mixed contract
      ↓
2-5 observations
      ↓
minimum 0.05-10 second monotonic start spacing
      ↓
per-sample evidence
      ↓
timing + semantic series evidence
      ↓
RealityReceipt
```

New authority:

`reality.local_http.timing.wait`

Spacing is measured between provider invocation starts using a monotonic clock.

Wall-clock capture timestamps are provenance only and do not prove the spacing contract.

A supported timed series still does not establish continuous service health between observations.

See `docs/PHIOS_SPINE_V0.21_TIMED_MIXED_OBSERVATION.md`.
