# PhiOS Governed Action Binding v0.7

## Status

Governed Action Binding v0.7 bridges an adopted PhiOS plan to the existing
authority-aware Spine **without executing anything**.

The important distinction is:

```text
plan edge
!=
executable capability
```

v0.6 gives PhiOS an immutable incumbent plan made of path/state identifiers.
The Spine executes registered capabilities with payloads and permission
requirements.

v0.7 creates the explicit binding between those two domains.

## Core rule

```text
ADOPTED PLAN
does not imply
BOUND ACTION

BOUND ACTION
does not imply
PERMISSION GRANTED

PERMISSION GRANTED
does not imply
SUCCESSFUL EXECUTION
```

Each boundary remains separately typed and receipted.

## Existing execution authority remains canonical

PhiOS already has an execution spine with:

- `Capability`;
- `CapabilityRegistry`;
- `PermissionGate`;
- `MandalaPacket`;
- `GateReceipt`;
- `ActionReceipt`;
- bounded executors.

v0.7 does not replace or duplicate those mechanisms.

Instead, it binds one adopted-plan transition to one existing Spine
`Capability` definition and one payload SHA-256.

The Spine remains responsible for deciding whether the capability's requested
permissions are actually granted.

## Implementation

The implementation lives at:

```text
phios/core/governed_action_binding.py
```

Main public types:

- `ActionBindingGrant`
- `PlanActionBinding`
- `ActionBindingReceipt`
- `GovernedActionBinder`

v0.7 also exposes:

```text
GovernedPlanAdoptionGate.validate_plan_state(...)
```

so downstream governance layers can verify an incumbent plan without mutating
it.

## Binding scope

An `ActionBindingGrant` binds:

- grant ID;
- authority-source label;
- exact plan ID;
- exact plan-state SHA-256;
- exact transition index;
- exact source state ID;
- exact target state ID;
- exact Spine capability ID;
- exact canonical payload SHA-256.

All of those values must match.

A grant for:

```text
plan P revision/hash H
edge A -> B
capability commons.text_artifact
payload hash X
```

cannot authorize a binding for:

```text
edge B -> D
another plan hash
another capability
or payload hash Y
```

## Payload handling

The binder hashes the supplied payload using deterministic canonical JSON:

```text
sort_keys = true
separators = (",", ":")
UTF-8
SHA-256
```

The resulting `PlanActionBinding` stores the payload digest, not a copy of the
payload itself.

That keeps the governance receipt focused on identity and provenance instead of
persisting arbitrary action data or secrets.

A future execution handoff must supply a payload whose digest matches this
binding.

## Capability binding

The binder consumes the existing Spine `Capability` type.

The binding records:

- capability ID;
- capability version;
- declared risk;
- requested permissions.

These requested permissions are descriptive, not grants.

For example:

```text
permissions_requested = ("artifact.write",)
```

means:

> this capability requires artifact.write

It does **not** mean:

> artifact.write has been granted

The existing Spine `PermissionGate` remains the authority checkpoint.

## Outcomes

v0.7 emits:

### BOUND

Returned only when:

- the plan state validates;
- the requested transition exists in that plan;
- the capability definition is structurally valid;
- the payload is canonical JSON;
- a binding grant is present;
- every grant scope field matches exactly.

A `PlanActionBinding` is created.

### HELD

Returned when binding authority is absent or the grant scope does not match.

Examples:

- wrong plan-state hash;
- wrong transition;
- wrong source/target;
- wrong capability;
- wrong payload digest.

No binding is created.

## Plan-edge validity

A transition index must identify an actual adjacent pair in the plan path.

For:

```text
A -> B -> D
```

valid indices are:

```text
0 = A -> B
1 = B -> D
```

Index 2 is not an edge and is rejected as malformed contract input.

## Tamper detection

Before any binding attempt, v0.7 validates the complete v0.6 `PlanState`
hash.

A caller cannot edit:

- path IDs;
- revision;
- source route receipt;
- source replan receipt;
- parent plan hash;
- authority flags;

and still reuse the old plan-state digest.

## Authority boundary

Every successful binding and binding receipt retains:

```text
action_authority = false
execution_authority = false
```

This may look pedantic, because it is. It is also the entire reason the layers
remain composable without accidental privilege escalation.

v0.7 cannot:

- grant a Spine permission;
- evaluate `PermissionGate`;
- create a Mandala action approval;
- execute a capability;
- invoke a tool;
- launch a process;
- claim that a side effect occurred.

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
 plan edge -> capability + payload hash
        ↓
existing Spine PermissionGate
        ↓
Mandala ACTION gate / executor
```

The next execution integration should consume a validated v0.7 binding and then
delegate permission evaluation and side effects to the existing Spine rather
than bypassing it.

## Tests

Focused coverage verifies:

- exact scoped authority produces a binding;
- missing authority returns `HELD`;
- payload scope mismatch returns `HELD`;
- capability scope mismatch returns `HELD`;
- plan-state scope mismatch returns `HELD`;
- invalid transition indices are rejected;
- tampered plan states are rejected;
- non-JSON payloads are rejected;
- bindings and receipts are deterministic;
- requested permissions are copied from the Spine capability;
- bindings retain zero action and execution authority.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```
