# PhiOS Spine v0.17 - Same-Snapshot JSON Contracts

Spine v0.17 composes the v0.15 type checks and v0.16 structural predicates into a bounded 1-8 clause contract evaluated against one HTTP response.

```text
one loopback GET
      ↓
one bounded body
      ↓
one strict JSON parse
      ↓
1-8 typed clauses
      ↓
all clause results
      ↓
one content-addressed semantic evidence record
      ↓
RealityReceipt
```

The provider is called once per claim. Raw pointed values remain absent from persisted evidence.

See `docs/PHIOS_SPINE_V0.17_JSON_MULTI_CONTRACT.md`.
