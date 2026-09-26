# Macro Runtime v0.2 — Spine + Reality Ledger Bridge

## Status

Governed integration rung for the Macro Runtime v0.1 reference core.

v0.2 connects one LIVE macro operation to the existing PhiOS execution spine.
It does not create a new permission system and it does not allow the Macro
Runtime reference grants to authorize real effects.

## Boundary

```text
MACRO INTENT != AUTHORITY
MACRO BINDING != AUTHORITY
ACTIONLEASE != EXECUTION AUTHORITY
MACRO RECEIPT != PROOF OF CORRECTNESS
```

The existing PhiOS authority path remains canonical.

```text
Macro Operation
      ↓
MacroSpineBinding
      ↓
PlanActionBinding
      ↓
verified single-use ActionLease
      ↓
GovernedLeasedExecutionHandoff
      ↓
PhiOS Spine
      ↓
Reality Ledger
```

## Why a bridge instead of a second executor

Macro Runtime v0.1 intentionally used a deterministic in-memory adapter and a
small reference grant model to prove execution invariants.

Those reference grants are not promoted into real PhiOS action authority.

v0.2 delegates real execution to the existing governed Spine so one system
continues to own:

- permission evaluation;
- effect-boundary evaluation;
- plan/action binding validation;
- ActionLease verification;
- authority-epoch validation;
- single-use lease claiming;
- binding consumption;
- executor entry;
- outcome-unknown handling;
- execution provenance;
- Reality Ledger recording.

## MacroSpineBinding

`MacroSpineBinding` is a zero-authority provenance object binding one macro
operation to one exact PhiOS execution scope.

It records:

- macro ID and version;
- operation ID and version;
- operation hash;
- plan ID and state hash;
- action-binding hash;
- capability ID;
- payload hash;
- ActionLease hash.

All authority flags are permanently false.

Before execution, the bridge requires:

```text
operation.adapter_id == "phios.spine"
operation.action == binding.capability_id
operation.required_capabilities == binding.permissions_requested
hash(operation.inputs) == binding.payload_sha256
hash(supplied_payload) == binding.payload_sha256
macro_binding == current exact execution scope
```

Any mismatch fails before the governed handoff is entered.

## LIVE only

The v0.2 bridge accepts only `ExecutionMode.LIVE`.

This is deliberate.

The deterministic v0.1 runtime remains the conformance target for DRY_RUN and
REPLAY. v0.2 does not pretend that arbitrary real PhiOS executors have
side-effect-free simulation or deterministic replay semantics.

Those modes require a later adapter contract.

## ActionLease behavior

The bridge does not interpret an ActionLease as execution authority.

It passes the exact lease and verification evidence into
`GovernedLeasedExecutionHandoff`.

The existing handoff still verifies current authority state, lease scope,
consumption state, capability contract, effect boundary, permissions, and
executor behavior.

A consumed lease produces `HELD` and is not re-executed.

## Macro Reality Ledger receipt

v0.2 adds an append-only:

```text
ledger/macro-receipts.jsonl
```

Each `MacroSpineReceipt` records:

- macro identity;
- macro operation hash;
- macro-Spine binding hash;
- action-binding hash;
- ActionLease hash;
- leased-handoff receipt hash;
- underlying Spine receipt ID, when execution reached the Spine;
- underlying Spine execution status;
- lease-consumption status;
- replay-blocked status;
- receipt hash.

The macro receipt carries no authority and does not independently claim that an
effect occurred.

The underlying Spine and Mandala receipts remain the execution evidence.

## v0.2 acceptance gates

### MSPINE-001 — governed success

A correctly bound macro operation with a valid current ActionLease:

```text
MacroSpineReceipt.status == SUCCEEDED
lease_consumed == true
spine_execution_status == succeeded
spine_receipt_id != null
```

The normal Spine receipt must retain the exact action-binding and ActionLease
provenance.

### MSPINE-002 — single-use replay block

Attempting the same execution again with the consumed ActionLease:

```text
status == HELD
reason == lease_consumed
replay_blocked == true
spine_receipt_id == null
```

Both the successful attempt and held attempt remain visible in the macro
receipt ledger.

### MSPINE-003 — exact-scope mismatch

If the macro operation inputs differ from the bound execution payload, the
bridge must fail before Spine execution.

Required outcome:

```text
spine execution receipts == 0
macro execution receipts == 0
effect == not attempted
```

## Deliberate non-goals

v0.2 does not add:

- macro graphs;
- loops;
- conditions;
- schedules;
- triggers;
- filesystem adapters;
- browser adapters;
- shell adapters;
- API adapters;
- model adapters;
- automatic retries;
- external rollback;
- real-world dry-run simulation;
- automatic macro learning;
- higher-order optimization.

Those remain blocked until this bridge stays green.

## Next rung

After v0.2 is merged and green, v0.3 can introduce a zero-authority
`MacroDefinition` and deterministic graph planner with a very small primitive
set:

```text
DO
IF
LOOP
FOREACH
CALL
CHECKPOINT
APPROVE
```

The graph planner may describe work.

It must not grant the authority required to perform that work.
