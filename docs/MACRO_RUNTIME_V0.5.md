# Macro Runtime v0.5 — Governed DO Dispatcher

## Status

End-to-end bridge from a paused v0.4 MacroRunner DO instruction to the merged
v0.2 governed Spine execution path and back into an OperationResolution.

v0.5 closes the first complete automation loop without moving authority into
the runner or planner.

## Core boundary

```text
WORK PACKAGE != AUTHORITY
DISPATCHER != AUTHORITY BROKER
DISPATCH RECEIPT != EFFECT PROOF
OPERATION RESOLUTION != CAPABILITY GRANT
RUNNER RESUME != REAUTHORIZATION
```

The existing PhiOS authority path remains canonical.

## End-to-end path

```text
MacroDefinition
      ↓
MacroPlan
      ↓
MacroRunner
      ↓
WAITING_OPERATION
      ↓
OperationWorkPackage
      ↓
exact Operation
      ↓
exact PlanActionBinding
      ↓
exact MacroSpineBinding
      ↓
verified single-use ActionLease
      ↓
MacroSpineBridge
      ↓
GovernedLeasedExecutionHandoff
      ↓
PhiOS Spine
      ↓
Reality Ledger
      ↓
MacroSpineReceipt
      ↓
DoDispatchReceipt
      ↓
OperationResolution
      ↓
MacroRunner resumes
```

## OperationWorkPackage

The dispatcher may create a work package only when:

- the runner is exactly `WAITING_OPERATION`;
- the run state references the supplied MacroPlan hash;
- the runner cursor points to a DO instruction;
- the runner waiting boundary matches that DO;
- the supplied Operation exactly matches the planned operation identity,
  version, hash, adapter, action, and required capabilities.

The package binds:

- macro ID and version;
- exact MacroPlan hash;
- exact MacroRunState hash;
- instruction index and path;
- operation ID and version;
- operation hash;
- input hash;
- adapter ID;
- action;
- required capabilities.

It contains no credentials, ActionLease, authority grant, executor object, or
broad permission state.

All authority flags are false.

## Packaging is deterministic

For one exact:

```text
MacroPlan
MacroRunState
Operation
```

the generated work package and work-package SHA-256 are deterministic.

A changed runner state, plan, operation input, or operation contract produces a
different package or is rejected.

## Dispatch scope

`dispatch()` recomputes the expected work package from the current plan,
runner state, and Operation.

The supplied package must equal the recomputed package before any real
execution path is entered.

The dispatcher then builds a fresh `MacroSpineBinding` from the exact:

- macro identity;
- Operation;
- governed PlanState;
- PlanActionBinding;
- ActionLease.

The MacroSpineBridge performs its existing scope checks again.

This duplication is deliberate defense in depth, not a second authority
decision.

## Authority

The dispatcher never creates:

- PlanActionBinding grants;
- ActionLeases;
- authority epochs;
- approval evidence;
- permissions;
- execution authority.

Those are supplied from the existing governance system.

A work package cannot execute by itself.

## Dispatch receipt

v0.5 adds an append-only:

```text
macro-dispatch-receipts.jsonl
```

Each `DoDispatchReceipt` binds:

- macro identity;
- exact plan hash;
- exact paused run-state hash;
- instruction path;
- operation hash;
- work-package hash;
- MacroSpineBinding hash;
- MacroSpineReceipt hash;
- MacroSpine status and reason;
- underlying Spine receipt ID when present;
- mapped OperationResolution status.

All authority flags remain false.

`effect_performed` is also false.

The actual effect evidence remains in the underlying Spine / Mandala execution
receipts.

## Resolution mapping

The dispatcher maps MacroSpine outcomes conservatively:

```text
MacroSpine SUCCEEDED -> OperationResolution SUCCEEDED
MacroSpine FAILED    -> OperationResolution FAILED
all other outcomes   -> OperationResolution HELD
```

That means:

- consumed lease -> HELD;
- permission denial -> HELD;
- authority / scope hold -> HELD;
- outcome unknown -> HELD.

The dispatcher does not guess that an ambiguous outcome succeeded or failed.

## Runner resume

The emitted `OperationResolution` contains:

- exact instruction path;
- exact operation hash;
- mapped resolution status;
- `DoDispatchReceipt.receipt_sha256`.

The v0.4 MacroRunner therefore resumes only against evidence bound to the exact
DO instruction it was already waiting on.

A successful result advances the runner.

A held result leaves the run held.

A failed result makes the run failed.

## v0.5 acceptance gates

### DISPATCH-001 — exact zero-authority work package

Packaging a valid WAITING_OPERATION boundary produces a deterministic work
package bound to the plan, run state, instruction, and Operation with all
authority flags false.

### DISPATCH-002 — full success loop

A valid work package plus valid existing governed execution evidence must
produce:

```text
MacroSpineReceipt.status == SUCCEEDED
DoDispatchReceipt.resolution_status == SUCCEEDED
OperationResolution.status == SUCCEEDED
MacroRunner -> COMPLETED
```

The Reality Ledger must contain:

- normal Spine execution evidence;
- MacroSpineReceipt;
- DoDispatchReceipt.

### DISPATCH-003 — planned operation mismatch

An Operation whose hash or contract differs from the planned DO must be rejected
before real execution or dispatch receipting.

### DISPATCH-004 — consumed lease remains held

Reusing the same single-use ActionLease must produce:

```text
MacroSpineReceipt.status == HELD
reason == lease_consumed
OperationResolution.status == HELD
MacroRunner.status == HELD
```

No second real effect may be performed.

### DISPATCH-005 — only WAITING_OPERATION may dispatch

A READY, WAITING_APPROVAL, COMPLETED, HELD, FAILED, or otherwise non-operation
run state cannot be packaged for DO dispatch.

## Deliberate non-goals

v0.5 does not:

- obtain ActionLeases automatically;
- create action-binding grants;
- resolve approvals;
- schedule macros;
- dispatch CALL instructions;
- evaluate conditions;
- create real CHECKPOINT instructions;
- perform variable substitution;
- persist MacroRunState itself;
- retry failed operations;
- provide browser / shell / API / model adapters;
- learn repeated workflows;
- optimize macros.

## What is now complete

The first narrow governed automation path now exists end to end:

```text
describe
→ plan
→ run
→ pause
→ dispatch through existing authority
→ receipt
→ resume
```

The system can therefore distinguish:

```text
what should happen
what may happen
what did happen
what evidence says happened
what control flow may do next
```

without collapsing those concepts into one agent decision.

## Next rung

v0.6 should add **persistent MacroRun journals and resume receipts**.

The runner state is already deterministic, but it currently lives only as an
in-memory value supplied by the caller.

A safe persistence rung should append immutable run-state transitions to the
Reality Ledger and support reconstruction of the latest valid state without
allowing history rewriting.

Only after persistent resume is proven should schedules or triggers begin
starting unattended macro runs.
