# PhiOS Spine v0.2 — Mandala Contract Layer

Spine v0.2 implements the first backend contracts from the **PhiOS Mandala Master Architecture v0.1** while preserving the green v0.1 execution path.

## Canonical semantics

The implementation freezes:

- four gates: `PERCEPTION`, `DELIBERATION`, `ACTION`, `MEMORY`
- eight statuses: `ACCEPTED`, `REJECTED`, `QUARANTINED`, `DEGRADED`, `BLOCKED`, `ABORTED`, `DISPUTED`, `UNKNOWN`
- a minimal frozen `PhiCoreState`
- `MandalaPacket`
- the receipt family
- an append-oriented Mandala receipt ledger

The contract version is:

```text
phios.mandala.v0.1
```

## MandalaPacket

The packet implements the master architecture fields:

```text
packet_id
parent_id
task_id
gate
origin
payload_digest
authority
evidence_refs
claims
allowed_destinations
resource_budget
contract_version
```

The transport object may also carry the in-process payload, but the stable envelope identifies that payload by its canonical SHA-256 digest.

Authority is explicit in the packet as an `AuthorityContext` containing both the authority ceiling and the active grants. It is never inferred from the requested capability.

## Receipt family

The package defines:

- `GateReceipt`
- `RouteReceipt`
- `PerceptionReceipt`
- `RealityReceipt`
- `ActionReceipt`
- `MemoryPromotionReceipt`
- `AbortReceipt`

Only GateReceipt and ActionReceipt are wired into the v0.1 execution path in this release. AbortReceipt is emitted on terminal executor failure. The other receipt types are frozen contracts for later gates.

## v0.1 compatibility bridge

The original `ExecutionReceipt` remains intact for callers that already consume it. v0.2 adds links:

```text
packet_id
gate_receipt_id
action_receipt_id
mandala_status
```

Typed Mandala receipts are stored separately at:

```text
<state-root>/ledger/mandala-receipts.jsonl
```

The legacy receipt stream remains:

```text
<state-root>/ledger/receipts.jsonl
```

This avoids pretending migration is free. Consumers can move to typed receipts deliberately.

## First real South Gate transaction

`commons.text_artifact` now performs:

```text
PhiVessel plan
    ↓
MandalaPacket(ACTION)
    ↓
GateReceipt
    ↓
explicit grant check
    ↓
ActionReceipt
    ↓
bounded executor
    ↓
content-addressed artifact
```

A denied permission produces a BLOCKED GateReceipt and BLOCKED ActionReceipt and no artifact. The runtime does not try another tool as a shortcut.

## Acceptance coverage

v0.2 directly advances:

- **MA-001** — Phi Core authority is held in a frozen state object; collaborators cannot mutate it in place.
- **MA-005** — the existing external side effect now produces an ActionReceipt tied to explicit grants.
- **MA-007** — denial is represented as BLOCKED and executor failure as ABORTED; neither becomes success because text or fallback output exists.

This is not yet full Mandala acceptance. Perception provenance, route-role receipts, memory promotion, replay, and desktop reconstruction remain future phases.

## CLI

```bash
phi-spine status
phi-spine mandala-ledger --limit 20
```

The status command exposes the contract version, task id, four gates, and frozen status vocabulary.

## Architectural rule

The Mandala layer is contracts first. It does not add a visual mandala, autonomous routing, broader filesystem authority, network authority, or background execution.
