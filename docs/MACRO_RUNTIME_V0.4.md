# Macro Runtime v0.4 — Pause-Capable Macro Runner

## Status

Deterministic control-flow runner over the merged v0.3 MacroPlan format.

v0.4 advances plan state. It does not execute real effects and it does not grant
authority.

## Core boundary

```text
RUNNING != EXECUTING EFFECTS
WAITING_OPERATION != OPERATION AUTHORITY
WAITING_APPROVAL != APPROVAL
APPROVAL RESOLUTION != EXECUTION AUTHORITY
CHECKPOINT REQUEST != RESTORABLE CHECKPOINT
CALL RESOLUTION != CALLEE AUTHORITY
CONDITION EVIDENCE != POLICY
RUNNER STATE != REALITY PROOF
```

Real effects still require the v0.2 path:

```text
Macro Runner
   ↓ WAITING_OPERATION
external governed operation execution
   ↓
MacroSpineBridge
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
   ↓
OperationResolution
   ↓
Macro Runner resumes
```

## Runner statuses

v0.4 defines:

```text
READY
RUNNING
WAITING_OPERATION
WAITING_CONDITION
WAITING_APPROVAL
WAITING_CALLEE
CHECKPOINTING
WAITING_COLLECTION
COMPLETED
HELD
FAILED
ABORTED
```

`RUNNING` is the active transition concept. Returned snapshots are normally a
pause, terminal, or ready state because `advance()` proceeds until it reaches
an unresolved boundary.

## Deterministic state

`MacroRunState` contains:

- macro ID and version;
- exact plan SHA-256;
- instruction cursor;
- runner status and reason;
- bounded loop counters;
- bounded foreach indices;
- runtime variables;
- current waiting boundary;
- last instruction path;
- transition count;
- zero authority flags;
- deterministic state SHA-256.

There are no UUIDs or timestamps in the runner state hash.

The same plan plus the same supplied resolutions therefore produces the same
runner state.

## DO

A `DO` instruction never executes inside the v0.4 runner.

Without matching external execution evidence:

```text
status = WAITING_OPERATION
cursor = current DO
```

The runner resumes only when it receives an `OperationResolution` bound to:

- the exact instruction path;
- the exact planned operation hash;
- an external receipt SHA-256;
- a terminal resolution status.

Possible outcomes:

```text
SUCCEEDED -> advance
HELD      -> runner HELD
FAILED    -> runner FAILED
```

The resolution is evidence supplied to the control-flow engine. It is not a
capability grant.

## IF

`IF_BEGIN` requires a `ConditionResolution` containing:

- condition ID;
- Boolean value;
- evidence reference SHA-256.

If no result exists:

```text
WAITING_CONDITION
```

The runner selects exactly one planned branch.

It does not evaluate the condition itself.

## LOOP

A planned LOOP executes its body exactly up to the `max_iterations` bound
already frozen into the v0.3 plan.

The runner stores iteration count keyed to the source-step hash.

No runtime input can increase the compiled loop bound.

## FOREACH

`FOREACH_BEGIN` requires a `CollectionResolution` containing:

- collection reference;
- canonical item tuple;
- evidence reference SHA-256.

Without one:

```text
WAITING_COLLECTION
```

If the supplied collection exceeds the planned `max_items`:

```text
HELD
reason = collection_bound_exceeded
```

During each iteration, the current item is exposed in runner variables under
the planned item name.

v0.4 does not yet perform parameter substitution into DO operations.

## APPROVE

`APPROVE` is a pause barrier.

Without an `ApprovalResolution`:

```text
WAITING_APPROVAL
```

A resolution must exactly match:

- barrier ID;
- required capability set;
- external evidence SHA-256.

An approved barrier only allows control flow to move to the next instruction.

It does not alter any runner authority flag.

All remain:

```text
operational_authority = false
action_authority = false
execution_authority = false
```

A later DO still requires the real PhiOS authority and ActionLease path.

## CALL

`CALL` pauses at:

```text
WAITING_CALLEE
```

until an external `CallResolution` matches:

- instruction path;
- callee macro ID;
- callee version;
- argument SHA-256.

v0.4 does not recursively execute child macros.

## CHECKPOINT

`CHECKPOINT` enters:

```text
CHECKPOINTING
```

until an external `CheckpointResolution` exists for the exact instruction
path and label.

The runner does not claim that checkpoint data is restorable.

Actual checkpoint creation and rollback evidence still belong to the runtime
that owns the affected state.

## HELD versus FAILED

`HELD` means control cannot currently proceed without violating the declared
contract.

Examples:

- operation resolution scope mismatch;
- collection bound exceeded;
- approval denied;
- callee held;
- checkpoint held;
- per-advance transition budget exhausted.

`FAILED` means supplied external execution evidence reports a failed
operation, call, or checkpoint.

HELD is resumable.

FAILED and ABORTED are terminal in v0.4.

## Transition budget

Each `advance()` call has a hard transition budget.

Default and maximum:

```text
MAX_ADVANCE_TRANSITIONS = 50000
```

This is separate from the v0.3 loop and collection bounds.

It prevents one resume call from consuming unbounded interpreter work even
when the plan itself is valid.

## v0.4 acceptance gates

### RUNNER-001 — DO pause

A DO with no matching operation receipt pauses at `WAITING_OPERATION`.

### RUNNER-002 — operation pinning

An OperationResolution with the wrong operation hash produces `HELD` and does
not advance the cursor.

### RUNNER-003 — IF false branch

Missing condition evidence pauses. A false condition selects only the compiled
else branch.

### RUNNER-004 — IF true branch

A true condition executes the then control path and skips the else path.

### RUNNER-005 — bounded LOOP

A loop executes exactly its compiled maximum iteration count.

### RUNNER-006 — FOREACH bound

An unresolved collection pauses. A collection larger than `max_items` is held.

### RUNNER-007 — bounded FOREACH completion

A valid collection iterates to completion and removes the temporary item
variable after traversal.

### RUNNER-008 — approval remains zero-authority

Passing an APPROVE barrier advances control flow but grants no authority.

### RUNNER-009 — approval denial

A denied approval resolution produces `HELD`.

### RUNNER-010 — callee failure

A failed child-call resolution makes the run `FAILED`.

### RUNNER-011 — deterministic runner state

Same plan and same inputs produce identical state and state hash.

### RUNNER-012 — stale-plan rejection

A run state cannot resume against a different plan hash.

### RUNNER-013 — explicit abort

Abort is terminal and carries zero authority.

## Deliberate non-goals

v0.4 does not yet:

- execute DO operations;
- automatically call MacroSpineBridge;
- create or verify ActionLeases;
- resolve conditions;
- acquire approvals;
- recursively run child macros;
- create real checkpoints;
- persist MacroRunState to the Reality Ledger;
- substitute FOREACH / parameter values into operations;
- schedule or trigger macros;
- retry failed operations;
- run browser, shell, API, or model adapters;
- learn macros from observation;
- optimize workflows.

## Next rung

v0.5 should introduce the **Governed DO Dispatcher**.

The dispatcher should turn a `WAITING_OPERATION` boundary into an explicit
work package that can be bound to the existing v0.2 MacroSpineBridge.

The runner should not receive raw credentials, broad permissions, or generic
executor access.

A safe initial path is:

```text
WAITING_OPERATION
      ↓
OperationWorkPackage
      ↓
exact PlanActionBinding
      ↓
exact MacroSpineBinding
      ↓
verified ActionLease
      ↓
MacroSpineBridge
      ↓
MacroSpineReceipt
      ↓
OperationResolution
      ↓
runner resume
```
