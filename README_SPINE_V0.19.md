# PhiOS Spine v0.19 - Same-Snapshot Mixed JSON Contracts

Spine v0.19 composes the existing semantic verifier ladder into one bounded same-snapshot contract.

```text
one loopback GET
      ↓
one strict JSON document
      ↓
type clauses
structural clauses
scalar clauses
      ↓
conditional value-read authority
      ↓
one content-addressed evidence record
      ↓
RealityReceipt
```

A mixed contract supports 1-8 clauses.

Scalar clauses require `reality.local_http.semantic.value.read`. Type/structural-only mixed contracts do not.

Observed scalar values remain transient and are not persisted.

See `docs/PHIOS_SPINE_V0.19_JSON_MIXED_CONTRACT.md`.
