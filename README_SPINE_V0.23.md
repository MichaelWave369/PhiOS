# PhiOS Spine v0.23 - Temporal Envelope Mixed Contracts

Spine v0.23 constrains both adjacent cadence and the total first-to-last provider-start span.

```text
same mixed contract
      ↓
2-5 observations
      ↓
each adjacent start inside cadence MIN/MAX
      ↓
whole series inside span MIN/MAX
      ↓
future-feasible scheduling
      ↓
semantic + temporal evidence
      ↓
RealityReceipt
```

New authority:

`reality.local_http.timing.envelope`

Impossible cadence/span combinations are rejected before provider I/O.

The scheduler accounts for how much cadence capacity remains when choosing each next start, but provider overruns remain visible contradictions.

See `docs/PHIOS_SPINE_V0.23_TEMPORAL_ENVELOPE.md`.
