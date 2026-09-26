# Macro Runtime v0.3 — Macro Definition + Deterministic Graph Planner

## Status

Zero-authority structured automation language and deterministic planner.

v0.3 describes automation control flow. It does not execute that control flow
and it does not grant any permission required by the described work.

## Core boundary

```text
MACRO DEFINITION != AUTHORITY
MACRO PLAN != AUTHORITY
APPROVE STEP != APPROVAL
CHECKPOINT STEP != CHECKPOINT RECEIPT
CALL STEP != CALLEE AUTHORITY
PLANNING != EXECUTION
```

Real LIVE effects still require the v0.2 path:

```text
planned DO
   ↓
Operation
   ↓
MacroSpineBinding
   ↓
PlanActionBinding
   ↓
verified ActionLease
   ↓
GovernedLeasedExecutionHandoff
   ↓
PhiOS Spine
   ↓
Reality Ledger
```

## Why a structured graph

v0.3 deliberately does not expose arbitrary goto edges.

Macros are represented as nested structured blocks. That preserves familiar
automation primitives while removing unbounded user-defined control-flow cycles
from the first graph contract.

The supported source primitives are:

```text
DO
IF
LOOP
FOREACH
CALL
CHECKPOINT
APPROVE
```

The planner compiles them into canonical control-flow instructions such as:

```text
DO
IF_BEGIN
ELSE
IF_END
LOOP_BEGIN
LOOP_END
FOREACH_BEGIN
FOREACH_END
CALL
CHECKPOINT
APPROVE
```

## DO

`DoStep` embeds one exact Macro Runtime `Operation`.

The plan pins:

- operation ID;
- operation version;
- operation hash;
- adapter ID;
- action;
- required capabilities.

Planning a DO step does not authorize the operation.

Changing its inputs changes its operation hash, definition hash, and plan hash.

## IF

`IfStep` references a `condition_id`.

v0.3 does not evaluate conditions.

Both branches are retained in the deterministic plan:

```text
IF_BEGIN
  then ...
ELSE
  else ...
IF_END
```

The later execution layer will require a governed condition evaluator before
choosing a branch.

## LOOP

`LoopStep` requires:

- a non-empty loop ID;
- a non-empty body;
- an explicit `max_iterations`;
- `1 <= max_iterations <= 10000`.

No unbounded loop exists in the v0.3 contract.

The planner does not unroll the loop. It records the explicit bound.

## FOREACH

`ForEachStep` requires:

- an item name;
- a collection reference;
- a non-empty body;
- an explicit `max_items`;
- `1 <= max_items <= 10000`.

The collection is not read by the planner.

The bound remains part of the plan so the later runner cannot silently turn an
apparently small workflow into an unlimited traversal.

## CALL

`CallStep` pins:

- callee macro ID;
- callee macro version;
- canonical arguments;
- argument SHA-256.

v0.3 does not resolve or execute the callee and does not inherit authority from
either caller or callee.

Recursive call execution is therefore not introduced in this rung.

## CHECKPOINT

`CheckpointStep` is a declarative checkpoint request.

It does not itself prove that runtime state is restorable.

A future runner must map the request to the v0.1/v0.2 rollback semantics and
record the actual checkpoint evidence.

## APPROVE

`ApproveStep` declares an authority barrier.

It contains:

- barrier ID;
- sorted unique required capability names;
- human-readable reason.

Its compiled instruction explicitly records:

```text
grants_authority = false
```

The later runner must stop at the barrier unless the relevant PhiOS authority
path produces the required current grants / leases.

The step itself can never satisfy the barrier.

## MacroDefinition

A `MacroDefinition` contains:

- macro ID;
- macro version;
- sorted unique parameter names;
- structured steps;
- zero authority flags;
- deterministic definition SHA-256.

A definition is declarative source material only.

## MacroPlan

`MacroGraphPlanner` validates and compiles a definition into a `MacroPlan`.

Every instruction contains:

- deterministic instruction index;
- deterministic structural path;
- opcode;
- canonical payload;
- source-step SHA-256;
- zero authority flags.

The plan itself contains:

- macro ID and version;
- source definition SHA-256;
- compiled instructions;
- deterministic plan SHA-256;
- zero authority flags.

There are no timestamps, UUIDs, random values, or environment observations in
the planning hash.

Identical definitions therefore produce identical plans.

## Structural limits

v0.3 applies explicit parser/planner bounds:

```text
MAX_NESTING_DEPTH = 32
MAX_STATIC_STEPS = 4096
MAX_LOOP_ITERATIONS = 10000
MAX_FOREACH_ITEMS = 10000
```

These are contract safety limits, not claims that workflows near the limit are
cheap or desirable to execute.

## v0.3 acceptance gates

### GRAPH-001 — deterministic planning

Identical MacroDefinitions must produce identical:

- definition SHA-256;
- instruction sequence;
- plan SHA-256.

### GRAPH-002 — primitive compilation

A representative structured macro must compile the expected opcodes in stable
order.

### GRAPH-003 — zero authority

MacroDefinition, MacroPlan, every PlanInstruction, and APPROVE instructions must
carry zero authority.

### GRAPH-004 — operation pinning

Changing a DO operation changes the operation hash and plan hash.

### GRAPH-005 — bounded LOOP

A LOOP with no positive finite bound is rejected.

### GRAPH-006 — bounded FOREACH

A FOREACH exceeding the contract item bound is rejected.

### GRAPH-007 — canonical CALL arguments

Equivalent argument objects with different dictionary insertion order produce
the same macro and plan hashes.

### GRAPH-008 — non-empty workflow

An empty macro definition is rejected.

## Deliberate non-goals

v0.3 does not execute plans.

It does not yet implement:

- condition evaluation;
- loop counters at runtime;
- collection resolution;
- nested CALL execution;
- approval acquisition;
- runtime checkpoint creation;
- graph pause/resume;
- graph receipts;
- schedules or triggers;
- browser/shell/API/model adapters;
- macro learning;
- higher-order optimization.

## Next rung

v0.4 should introduce the **Macro Runner state machine** over a compiled
MacroPlan.

The runner should initially support only deterministic control mechanics and
pause rather than improvise whenever external information or authority is
missing.

A useful first runtime status set is:

```text
READY
RUNNING
WAITING_CONDITION
WAITING_APPROVAL
WAITING_CALLEE
CHECKPOINTING
COMPLETED
HELD
FAILED
ABORTED
```

The runner may advance the plan.

It must never convert a plan into authority.
