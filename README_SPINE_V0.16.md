# PhiOS Spine v0.16 - JSON Structural Predicates

Spine v0.16 adds bounded structural predicates above the v0.15 local HTTP JSON contract.

```text
loopback HTTP response
      ↓
strict JSON
      ↓
exact JSON pointer
      ↓
whitelisted structural predicate
      ↓
structural measurement only
      ↓
redacted semantic evidence
      ↓
RealityReceipt
```

Supported predicate families:

- non-empty string
- array length: eq / gte / lte
- object key count: eq / gte / lte

No raw pointed values are persisted, and v0.16 does not promote structural success into application health.

See `docs/PHIOS_SPINE_V0.16_JSON_STRUCTURAL_PREDICATES.md`.
