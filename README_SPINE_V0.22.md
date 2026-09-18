# PhiOS Spine v0.22 - Cadenced Mixed Observations

Spine v0.22 adds an explicit monotonic cadence window around bounded mixed-contract observations.

```text
same mixed contract
      ↓
2-5 observations
      ↓
MIN <= provider-start interval <= MAX
      ↓
per-sample semantic + cadence evidence
      ↓
aggregate cadence series evidence
      ↓
RealityReceipt
```

New authority:

`reality.local_http.timing.cadence`

v0.22 preserves v0.21 minimum-only timing as a separate frozen claim kind.

Provider overruns can produce cadence contradictions even when every semantic clause matches.

See `docs/PHIOS_SPINE_V0.22_CADENCED_MIXED_OBSERVATION.md`.
