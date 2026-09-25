# PhiShell v0.14 — ΦDream / Symbol Lab

## Status

PhiShell visual rung for the merged PhiOS Curiosity Lane v0.1 and Curiosity Store v0.2.

## Purpose

ΦDream / Symbol Lab gives Curiosity a native top-level PhiOS workspace.

It is designed for:

- symbols
- metaphors
- questions
- hypotheses
- associations
- patterns
- dream fragments
- creative seeds

The interface intentionally allows ambiguity without confusing ambiguity with
verification.

## Runtime boundary

v0.14 is **session-local and unpersisted**.

The UI does not pretend that React state is the canonical Python Curiosity
Store. A governed local bridge will be required before session objects can be
persisted into `CuriosityStore`.

The visible boundary is:

```
SESSION LOCAL / UNPERSISTED
ZERO AUTHORITY
NO EXECUTE PATH
```

## Symbol Lab surfaces

### Capture palette

Each Curiosity kind gets an explicit capture mode and claim class.

### Constellation

Captured objects appear as session nodes. Parent relationships are visible and
selection drives the inspector.

### Thread inspector

The inspector exposes:

- kind
- claim class
- zero-authority status
- related seeds
- return pointers
- explicit handoff controls

### Related seeds

Relationship scoring is transparent and uses:

- shared tags
- meaningful lexical overlap
- direct parent/child lineage

Stop words and short lexical noise are excluded.

The related score is a navigation convenience, not a truth score.

### Return pointers

Operators can mark where to resume a thread later. In v0.14 these pointers are
session-local.

### Promotion proposals

The UI can create local proposal objects for:

- Research
- Build
- Ledger Review

Every proposal remains `proposal_only`.

There is no Execute target and no implicit admission by a destination lane.

## Navigation

Dream is now a first-class PhiShell destination alongside Research, Build,
Memory, Ledger, Governance, and Settings.

The PhiVessel Dream tab remains complementary: PhiVessel is the conversational
companion; Symbol Lab is the spatial curiosity workspace.

## Next rung

The next integration should be a governed same-origin bridge from PhiShell to
the Python Curiosity Store so that:

1. session artifacts can be offered for persistence,
2. the host validates the v0.1/v0.2 contracts,
3. filesystem mutation is explicit,
4. persisted hashes return to the UI,
5. browser state cannot silently rewrite append-only history.

Until then the Symbol Lab is intentionally honest about being ephemeral.
