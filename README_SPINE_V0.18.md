# PhiOS Spine v0.18 - Bounded JSON Scalar Predicates

Spine v0.18 adds privacy-minimized Boolean and numeric value predicates above the v0.17 same-snapshot structural contract line.

```text
bounded loopback response
        ↓
strict JSON
        ↓
exact JSON pointer
        ↓
explicit scalar value-read grant
        ↓
whitelisted Boolean / numeric predicate
        ↓
comparison outcome only
        ↓
RealityReceipt
```

Supported families:

- Boolean true / false;
- integer eq / gte / lte;
- number eq / gte / lte.

The observed scalar is inspected transiently and is not persisted in semantic evidence.

See `docs/PHIOS_SPINE_V0.18_JSON_SCALAR_PREDICATES.md`.
