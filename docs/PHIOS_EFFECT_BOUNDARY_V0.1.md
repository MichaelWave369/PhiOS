# PhiOS Effect Boundary v0.1

## Status

Research-hardening candidate.

Schemas / policy surfaces:

- `phios.effect_boundary_policy.v0.1`
- Mandala `EffectBoundaryReceipt`
- hardened `phios.plan_action_binding.v0.7.1`

Primary rule:

```text
METHOD LABEL != ENVIRONMENTAL EFFECT
```

A capability named `read`, `GET`, `status`, or `inspect` is not assumed to be
effect-free.

## Purpose

The Effect Boundary adds an explicit environmental-effect contract before the existing
Spine permission gate.

It does **not** create a second authority system.

The execution sequence is:

```text
Capability declaration
        +
Executor declaration
        ↓
EffectBoundaryPolicy
        ↓
EffectBoundaryReceipt
        ↓
existing PermissionGate
        ↓
GateReceipt
        ↓
ActionReceipt
        ↓
Executor
```

Only a complete, matching effect contract reaches permission evaluation.

## v0.1 effect vocabulary

The bounded vocabulary is:

```text
none
local_state.read
local_state.change
filesystem.read
filesystem.change
process.spawn
network.request
external_state.read
external_state.change
ipc.request
display.observe
display.control
credential.read
control_plane.read
control_plane.change
unknown
```

`unknown` is representable for evidence and diagnosis, but it is not executable.

`none` cannot be combined with another effect.

## Active environmental effects

The v0.1 policy classifies the following as active:

```text
local_state.change
filesystem.change
process.spawn
network.request
external_state.change
ipc.request
display.control
control_plane.change
```

The classification is deliberately conservative.

In particular:

```text
network.request
```

is active even when the transport method is normally described as read-only. Sending a
request can produce remote logging, counters, cache updates, lazy initialization,
session changes, hooks, rate-limit state, or application-specific mutations.

A protocol verb is therefore not accepted as evidence that environmental state cannot
change.

## Dual declarations

Every executable Spine capability has two declarations:

### Capability contract

`Capability.effects` describes the effects the capability contract says are possible.

### Executor contract

`ExecutorRegistry.register(..., effects=...)` separately describes the effects the
registered implementation may produce.

The policy requires exact normalized equality.

Examples:

```text
Capability.effects = ("filesystem.change",)
Executor.effects   = ("filesystem.change",)
→ CLASSIFIED
```

```text
Capability.effects = ("external_state.read",)
Executor.effects   = ("external_state.change",)
→ BLOCKED
```

This is declaration consistency, not empirical proof that the declarations are
complete.

## Read-label laundering defense

The existing `Capability.risk` label remains descriptive.

If:

```text
risk = "read"
```

but the effect contract contains an active environmental effect, the policy blocks with:

```text
read_risk_label_conflicts_with_active_effects
```

The effect declaration wins over the semantic label.

## EffectBoundaryReceipt

The receipt records:

- capability ID;
- capability version;
- capability risk label;
- capability effect tuple;
- executor effect tuple;
- active effect subset;
- effect-contract match;
- classification completeness;
- read-label conflict status;
- effect-policy SHA-256;
- reason;
- zero action authority;
- zero execution authority.

The receipt appears before the ordinary ACTION gate and becomes its parent receipt.

Therefore the lineage is explicit:

```text
EffectBoundaryReceipt
        ↓
GateReceipt
        ↓
ActionReceipt
```

## Existing authority remains canonical

The Effect Boundary cannot grant permission.

A successful effect classification means only:

> PhiOS has a complete, internally consistent declaration of the environmental effects
> this capability/executor pair says it may produce.

The existing Spine `PermissionGate` still decides whether the capability's permissions
are granted.

The receipt itself fixes:

```text
action_authority = false
execution_authority = false
```

## Governed action binding

A new governed action binding snapshots the exact declared effect tuple in:

```text
phios.plan_action_binding.v0.7.1
```

That makes effects part of the executable-intent contract rather than transient metadata.

At execution handoff, PhiOS checks:

```text
bound effects
==
current capability effects
==
current executor effects
```

before the atomic binding claim is acquired.

A changed effect contract therefore cannot silently inherit an old binding.

## Direct Spine execution

The Effect Boundary also runs for direct `PhiOSSpine.run(...)` execution.

Missing, unknown, inconsistent, or read-label-laundered effects block before executor
entry.

This prevents the governed handoff from being the only protected route while leaving a
legacy direct path able to execute unclassified capabilities.

## Failure semantics

The effect boundary is fail closed.

Representative reasons include:

- `capability_effect_classification_missing`;
- `executor_effect_classification_missing`;
- `effect_classification_unknown`;
- `capability_executor_effect_contract_mismatch`;
- `read_risk_label_conflicts_with_active_effects`.

A blocked direct Spine execution is receipted as not executed.

A blocked governed handoff is held before binding consumption.

## Ledger analytics

`EffectBoundaryReceipt` is included in the closed Mandala receipt type catalog used by
the read-only Ledger snapshot mapper.

The projection keeps bounded effect metadata while continuing to exclude authority
internals that are outside the analytics policy.

## What v0.1 does not prove

This contract does not prove that a declared effect list is complete.

It cannot, by declaration alone, establish that:

- an implementation has no covert side effect;
- a remote GET never mutates state;
- an IPC request cannot trigger another actor;
- a supposedly bounded effect cannot propagate through an unobserved dependency;
- no hidden or delayed effect exists.

Those are observation-coverage questions.

The next P0 hardening seam is therefore:

```text
ObservationFrontier
```

which should bind negative claims to the surfaces that were actually observable,
instrumented, or tested.
