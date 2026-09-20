# PhiOS Governed Execution Handoff v0.8

## Status

Governed Execution Handoff v0.8 connects a validated v0.7 action binding to the
existing PhiOS Spine execution path.

This is the first rung in the new core stack that may actually cause a side
effect, but it does so only by delegating to the already-existing Spine
authority path.

The core boundary is:

```text
BOUND ACTION
        ↓
execution-time revalidation
        ↓
existing Spine PermissionGate
        ↓
Mandala ACTION receipt
        ↓
bounded executor
```

v0.8 does not create a second permission system.

## Core rule

```text
BOUND ACTION
!=
EXECUTABLE NOW
```

A binding created earlier may be stale by the time execution is attempted.

v0.8 therefore revalidates, at execution time:

- the current immutable plan state;
- the v0.7 binding hash;
- plan ID and plan revision;
- transition index and exact source / target;
- canonical payload SHA-256;
- currently registered Spine capability;
- capability version;
- capability risk;
- requested permission tuple.

Only after those checks does the handoff delegate to `PhiOSSpine.run(...)`.

## Existing authority path remains canonical

The execution decision still belongs to the existing Spine:

```text
Capability
    ↓
PermissionGate
    ↓
GateReceipt
    ↓
ActionReceipt
    ↓
ExecutorRegistry
```

v0.8 does not interpret `permissions_requested` as granted authority.

The Spine may return:

- permission denied / not executed;
- allowed / succeeded;
- allowed / failed.

The governed handoff simply binds that runtime outcome back to the exact plan
and action-binding provenance.

## Implementation

The main implementation lives at:

```text
phios/core/governed_execution_handoff.py
```

Main public types:

- `ExecutionHandoffContractError`
- `ExecutionHandoffReceipt`
- `GovernedExecutionHandoff`

v0.8 also extends existing components with narrowly additive support:

- `GovernedActionBinder.validate_binding(...)`
- `GovernedActionBinder.payload_sha256(...)`
- `ExecutionProvenance` in `phios.spine.models`
- optional governed provenance on `ExecutionReceipt`
- governed binding replay checks in `RealityLedger`

## Exact current-plan scope

A v0.7 binding is executable only against the exact plan state it was created
for.

The handoff verifies:

```text
binding.plan_id
==
current_plan.plan_id

binding.plan_state_sha256
==
current_plan.state_sha256

binding.plan_revision
==
current_plan.revision
```

It then checks that the bound transition is still the exact adjacent edge in
the current path.

For example:

```text
plan path:
A -> B -> D

binding:
index 0
A -> B
```

cannot later be used against:

```text
A -> C -> D
```

or a newer plan revision with a different state hash.

## Capability drift protection

A binding snapshots the capability contract that existed when it was created:

- capability ID;
- version;
- risk;
- requested permissions.

At execution time, the current registered Spine capability must match that
snapshot exactly.

If a capability changed from:

```text
version 1.0
permissions = artifact.write
```

to:

```text
version 2.0
permissions = artifact.write, network.write
```

the old binding is held rather than silently inheriting the new capability
shape.

## Payload hash parity

v0.8 normalizes Spine payload hashing to the same canonical JSON form used by
v0.7:

```text
sort_keys = true
separators = (",", ":")
ensure_ascii = false
allow_nan = false
UTF-8
SHA-256
```

This closes a subtle Unicode mismatch where semantically identical payloads
could previously hash differently between the binding layer and Spine.

The runtime execution receipt must report the same input SHA-256 recorded in
the action binding.

## Governed execution provenance

A delegated Spine execution records:

```text
schema_version
plan_id
plan_state_sha256
plan_revision
transition_index
source_state_id
target_state_id
action_binding_sha256
```

inside the persisted `ExecutionReceipt`.

This provenance does not grant authority.

It tells the ledger which exact governed plan/binding produced the execution
attempt.

## Replay protection

v0.8 treats an action binding as a one-attempt side-effect token once the
executor is entered.

The rule is:

```text
permission denied
→ executor not entered
→ binding NOT consumed

permission allowed + executor succeeded
→ binding consumed

permission allowed + executor failed
→ binding consumed
```

The failure case is deliberately conservative.

An executor may fail after a partial external side effect. Blind retry would
risk duplicating that side effect.

## Atomic execution claim

Ledger history alone is not sufficient to prevent concurrent replay because two
processes could both perform:

```text
check not consumed
then execute
```

at nearly the same time.

v0.8 therefore creates an atomic per-binding claim using create-exclusive file
semantics before entering the Spine.

Only one claimant succeeds.

If permission is denied, the claim is released because the executor was never
entered.

If execution succeeds or fails, the claim remains consumed.

## Crash semantics

If a process acquires a binding claim and dies before a safe denied outcome can
release it, the claim remains.

That is intentionally fail-closed:

```text
uncertain execution state
→ do not auto-retry
```

v0.8 does not include an automatic stale-claim cleanup mechanism.

Any future claim recovery must be an explicit operator-governed contract that
can distinguish:

- definitely never executed;
- execution definitely completed;
- execution outcome uncertain.

## Outcomes

### HELD

Returned before execution when the binding is no longer safe to hand off.

Examples:

- stale plan;
- payload digest mismatch;
- missing capability;
- capability contract drift;
- binding already consumed;
- another process already owns the execution claim.

No Spine execution is started.

### DENIED

The binding and runtime state validated, but the existing Spine
`PermissionGate` denied the capability.

The executor was not entered.

The atomic binding claim is released, so the same exact binding may be retried
later if explicit Spine authority changes.

### SUCCEEDED

The Spine permission gate allowed the capability and the bounded executor
succeeded.

The binding is consumed.

### FAILED

The Spine permission gate allowed the capability and the executor raised an
error.

The binding is still consumed because a partial side effect cannot be ruled out.

## Handoff receipt

`ExecutionHandoffReceipt` binds the runtime outcome to:

- exact plan state;
- exact v0.7 binding SHA-256;
- transition index and edge;
- capability ID;
- payload digest;
- replay state;
- Spine execution receipt ID;
- permission status;
- execution status;
- gate receipt ID;
- action receipt ID;
- Mandala status;
- artifact path/hash when produced.

The handoff receipt itself retains:

```text
action_authority = false
execution_authority = false
```

Those fields mean the receipt itself cannot be reused as a grant.

Actual permission authority is represented by the Spine gate and action
receipts.

## Governance stack

```text
Geometric Reasoning v0.1
        ↓
Relational Field Geometry v0.2
        ↓
Dynamic Field State v0.3
        ↓
Field-Aware Routing v0.4
        ↓
Governed Replanning v0.5
        ↓
Governed Plan Adoption v0.6
        ↓
Governed Action Binding v0.7
        ↓
Governed Execution Handoff v0.8
        ↓
existing Spine PermissionGate
        ↓
Mandala ACTION gate
        ↓
bounded executor
        ↓
persisted execution evidence
```

## Tests

Focused coverage verifies:

- an exact valid binding executes through the existing Spine;
- execution provenance is persisted;
- permission denial does not consume a binding;
- a denied binding may later succeed after explicit permission changes;
- successful execution consumes the binding;
- replay after success is held;
- failed executor entry also consumes the binding;
- payload drift is held before execution;
- a binding for another valid plan is held;
- capability version/permission drift is held;
- Unicode payload hashes match across v0.7 and the Spine;
- existing direct Spine execution remains compatible.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```
