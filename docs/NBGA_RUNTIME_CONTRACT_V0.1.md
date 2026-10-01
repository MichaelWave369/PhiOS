# NBG-A Public Runtime Contract v0.1

**Status:** experimental, additive, read-only boundary  
**Scope:** PhiOS consumption of normalized PhiKernel continuity and memory observations  
**Non-goal:** publication of PhiKernel or TIEKAT implementation internals

NBG-A is the working name for the Nested Bubble/Gear Architecture used by the A-TEAM
memory lifecycle:

- **Anchor** preserves continuity-critical invariants.
- **Triage** classifies incoming state without granting authority.
- **Episodic** represents bounded events and their evidence.
- **Abstract** exposes higher-order observables while retaining provenance.
- **Manifest** reconstructs usable working state from trusted continuity roots.

PhiOS consumes only the normalized boundary described here. Storage engines, graph
algorithms, decay rules, routing logic, model prompts, private state, and TIEKAT
implementation details remain behind the PhiKernel boundary.

## Contract invariants

1. **Identity is not the model.**
2. **An observable is not the internal state.**
3. **Capability is not authority.**
4. **A trusted memory retains a path to why it is trusted.**
5. **Public observations do not grant write, promotion, routing, or execution authority.**
6. **Unknown fields fail closed rather than silently widening the contract.**

v0.1 intentionally exposes no mutation operation. Anchor promotion, triage decisions,
decay, consolidation, manifest commits, and continuity-root updates remain internal and
governed. A later public mutation contract requires a separate reviewed rung.

## Memory Receipt

Schema:

`phikernel.nbga.memory-receipt.v1`

A Memory Receipt carries one normalized observable and enough public lineage to explain
how it was retrieved:

```json
{
  "schema_version": "phikernel.nbga.memory-receipt.v1",
  "bubble_id": "bubble:project:decision",
  "bubble_version": 3,
  "observable": "Normalized human-readable state",
  "trust_state": "verified",
  "confidence": 1.0,
  "evidence": ["event:123"],
  "gear_path": [
    {
      "gear_id": "gear:evidence",
      "transform": "evidence",
      "source": "bubble:project",
      "destination": "bubble:project:decision"
    }
  ],
  "event_head": "event:123",
  "provenance_root": "sha256:..."
}
```

### Bubble

At the public boundary, a Bubble is identified by `bubble_id` and `bubble_version`.
PhiOS receives its `observable`, not its private payload or internal state.

### Gear path

A Gear Hop is a directional, named transformation between two public Bubble identities:

```text
source --[transform / gear_id]--> destination
```

The public contract describes the path. It does not expose how PhiKernel implements the
transformation.

### Evidence and provenance

`evidence`, `event_head`, and `provenance_root` make retrieval proof-carrying.
They are references, not an authority grant. PhiOS may present or compare them but may
not infer permission to mutate PhiKernel state.

## Bubble Zero Status

Schema:

`phikernel.nbga.bubble-zero-status.v1`

Bubble Zero is exposed only as a minimal continuity projection:

```json
{
  "schema_version": "phikernel.nbga.bubble-zero-status.v1",
  "system_id": "phios",
  "epoch": 7,
  "verified": true,
  "governance_root": "sha256:...",
  "event_log_head": "sha256:...",
  "topology_root": "sha256:...",
  "anchor_root": "sha256:...",
  "commitment_root": "sha256:...",
  "last_checkpoint": "checkpoint:7"
}
```

This projection answers only:

- which continuity identity is being observed,
- which epoch is current,
- whether the exposed root set verified,
- and which normalized roots/checkpoint identify that state.

It does not expose secrets, raw state, internal payload references, capability grants,
or authority grants.

## Fail-closed fields

The PhiOS parser rejects public payloads containing known private/authority-bearing
fields such as `internal_state`, `raw_state`, `private_state`, `payload`,
`payload_ref`, `secret`, `authority`, `authority_grant`, or
`capability_grant`.

It also rejects unknown top-level fields. Contract growth therefore requires an explicit
schema revision instead of accidental widening.

## First acceptance target

The first end-to-end NBG-A acceptance experiment should use already-understood PhiOS
qualification evidence:

1. ingest a bounded compatibility/qualification episode,
2. expose a higher-order verified observable,
3. retain evidence and a directional Gear path,
4. restart the runtime,
5. recover Bubble Zero,
6. retrieve the observable again with the same provenance lineage.

The experiment is successful only if restart/reconstruction preserves the trusted
observable and its evidence path without making the model, vector index, or PhiOS
presentation layer authoritative.

## Rollout

v0.1 is intentionally additive:

```text
qualified PhiOS/Linux candidate
          |
          v
existing PhiKernel adapter
          |
          +--> existing runtime behavior (unchanged)
          |
          +--> NBG-A normalized parser (new, read-only)
```

No existing adapter is promoted, no routing default changes, and no release authority is
implied by this contract.
