# PhiOS Spine v0.24 - Numeric Transition Contracts

Spine v0.24 adds bounded cross-snapshot numeric transition verification.

```text
2-5 observations
      ↓
transient numeric extraction
      ↓
adjacent pair comparison
      ↓
increase / equal / decrease relation
      ↓
predicate outcomes
      ↓
RealityReceipt
```

New authority:

`reality.local_http.semantic.transition.read`

Observed numeric values remain transient. Persisted evidence records the derived relation and predicate result, not the values or deltas.

v0.24 intentionally adds no timing semantics.

See `docs/PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md`.
