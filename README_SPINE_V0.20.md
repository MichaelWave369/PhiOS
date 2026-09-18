# PhiOS Spine v0.20 - Bounded Repeated Mixed Observations

Spine v0.20 adds bounded repetition around the v0.19 mixed contract.

```text
same mixed contract
      ↓
2-5 discrete local observations
      ↓
one receipt per successful observation
      ↓
one aggregate series evidence record
      ↓
RealityReceipt
```

New authority:

`reality.local_http.repeat.read`

Repeated samples have no enforced minimum interval in v0.20 and do not establish continuous service health.

Scalar clauses retain the separate value-read authority and raw scalar values remain transient.

See `docs/PHIOS_SPINE_V0.20_REPEATED_MIXED_OBSERVATION.md`.
