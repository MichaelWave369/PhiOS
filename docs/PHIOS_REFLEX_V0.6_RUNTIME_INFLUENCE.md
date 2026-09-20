# PhiReflex v0.6 — Governed Runtime Routing Influence

## Status

PhiReflex v0.6 is the first PhiReflex rung allowed to create **live routing
influence**.

That authority is deliberately narrow.

The central rule is:

```text
routing influence authority
!=
action authority
!=
execution authority
```

v0.6 may emit one bounded signal into one declared planner-context surface.
It cannot authorize tools, execute actions, bypass CAPS, or bypass the Spine.

## Preconditions

Runtime activation requires:

1. an exact valid v0.5 `ReflexInfluencePolicyState`;
2. an explicit `ReflexActivationRequest`;
3. an exact externally issued `ReflexActivationGrant`.

The activation request declares:

- provider;
- exact model identities;
- routing surface;
- allowed signal dimensions;
- influence weight.

The grant binds:

- exact v0.5 policy-state SHA-256;
- exact current activation-state SHA-256, or null for first activation;
- exact activation-request SHA-256;
- authority-source label;
- `ACTIVATE` or `HOLD` disposition.

No matching grant means no activation.

## Declared routing surface

v0.6 supports one live surface:

```text
agentception.planner_context.v0.6
```

The emitted signal may be attached only as:

```text
context.reflex_influence
```

Ordinary dispatch without an explicit signal is unchanged.

The task text, planner identity, tool grants, and execution permissions are not
rewritten by v0.6.

## Bounded deterministic blending

The runtime computes a deterministic local baseline and an approved provider
decision.

For every approved dimension:

```text
blended = (1 - w) * baseline + w * candidate
```

where:

```text
0 < w <= adopted policy max_influence_weight
```

The result is rounded deterministically and receipted.

v0.6 does not allow the provider to choose its own weight.

## Supported dimensions

The adopted policy and activation request may allow a subset of:

```text
role
risk
system2
verification
```

Only those dimensions appear in the live routing signal.

For example, a policy allowing only:

```text
role
system2
```

cannot inject:

```text
risk
verification
```

even if the provider returns them.

## Activation state

Successful activation creates an immutable
`ReflexActivationState` containing:

- activation ID;
- revision;
- exact v0.5 policy-state SHA-256;
- provider;
- exact model identities;
- routing surface;
- allowed dimensions;
- influence weight;
- consecutive provider-error count;
- parent activation-state SHA-256;
- activation-grant SHA-256;
- routing authority state;
- deterministic state SHA-256.

An active state explicitly carries:

```text
routing_influence_active = true
routing_influence_authority = true
promotion_authority = false
action_authority = false
execution_authority = false
```

This is the first PhiReflex state that carries positive routing authority.

That authority is scoped only to the declared routing surface.

## Provider/model revalidation

Every runtime evaluation checks the actual provider decision against the
activated state.

If the provider identity changes:

```text
provider_identity_drift
→ immediate rollback
```

If the model identity changes:

```text
provider_model_drift
→ immediate rollback
```

A calibrated and adopted model cannot silently be replaced by another model
under the same provider name.

## Provider failure behavior

A provider failure never causes the system to invent a signal.

The fallback is:

```text
no Reflex influence signal
→ ordinary dispatch path
```

The existing planner path therefore remains the deterministic fallback.

### Provider unavailable

If the adopted policy says:

```text
rollback_on_provider_unavailable = true
```

one unavailable-provider event immediately collapses routing influence.

If that flag is false, the runtime falls back without influence and increments
the consecutive error counter.

### Provider errors

Generic provider errors increment:

```text
consecutive_provider_errors
```

When the count reaches the adopted policy limit:

```text
routing influence collapses
```

A successful provider evaluation resets the consecutive-error count.

## Operator kill switch

Privilege collapse does not require an expansion grant.

The operator/runtime may call the v0.6 deactivation path with a reason:

```text
active
→ DEACTIVATED
→ routing_influence_active = false
```

This follows the broader PhiOS principle:

```text
privilege expansion requires authority
privilege collapse may be immediate
```

The kill switch does not alter the adopted v0.5 policy itself.

It only deactivates the current runtime state.

## Runtime routing signal

A successful runtime evaluation emits a deterministic
`ReflexRoutingInfluenceSignal`.

The signal binds:

- activation-state SHA-256;
- policy-state SHA-256;
- routing surface;
- provider;
- exact model;
- influence weight;
- allowed dimensions;
- blended probabilities;
- routing influence authority;
- zero action authority;
- zero execution authority;
- signal SHA-256.

The signal itself cannot authorize anything outside its planner-context surface.

## Planner integration

`build_dispatch_context(...)` now accepts an optional typed v0.6 signal.

Without one:

```text
context
→ unchanged ordinary dispatch
```

With one:

```text
context
+ validated reflex_influence block
→ planner
```

The remote AgentCeption planner sees the signal only when a caller explicitly
supplies a valid active signal.

There is no automatic boot-time Jev activation and no hidden environment flag
that turns influence on.

## Interaction with v0.2 shadow mode

v0.2 exists to measure predictions that did not influence the planner.

Once v0.6 live influence is attached to planner context, that specific dispatch
is no longer an independent v0.2 shadow experiment.

The existing v0.2 contamination firewall therefore remains useful: a planner
context already containing Reflex influence is not valid shadow-calibration
input.

## Receipts

v0.6 emits separate deterministic receipts for:

- activation;
- runtime influence/fallback/rollback;
- deactivation.

Runtime statuses include:

```text
INFLUENCED
FALLBACK
ROLLED_BACK
INACTIVE
```

Activation statuses include:

```text
ACTIVATED
HELD
DEACTIVATED
INACTIVE
```

## Authority boundary

Even while v0.6 is live:

```text
routing_influence_authority = true
action_authority = false
execution_authority = false
promotion_authority = false
```

Therefore v0.6 cannot:

- grant a capability;
- authorize a tool;
- execute a tool;
- bypass CAPS;
- bypass the Spine PermissionGate;
- adopt a plan;
- create plan-execution authority;
- promote the provider to wider scope;
- increase its own influence weight;
- add new dimensions;
- change provider/model scope.

## Tests

v0.6 tests verify:

- exact activation grant enables only scoped routing authority;
- missing activation authority remains held;
- activation weight cannot exceed v0.5 policy;
- deterministic blend math;
- unapproved dimensions remain absent;
- signal attachment changes only the declared planner surface;
- ordinary planner context remains unchanged without a signal;
- remote planner receives live influence only when explicitly attached;
- provider unavailability can roll back immediately;
- repeated provider errors fall back then roll back at threshold;
- provider model drift forces immediate rollback;
- operator deactivation requires no expansion grant;
- activation-state tampering is rejected;
- all live signals retain zero action/execution authority.

## Next rung

The next safe rung should focus on **runtime persistence and operator control**,
not broader influence.

A future v0.7 could add:

- persistent activation-state storage;
- explicit external grant ingestion;
- startup state restoration;
- operator status/deactivate commands;
- runtime receipt ledger;
- crash-safe rollback;
- activation expiration or lease semantics.

Only after that operational control plane is proven should PhiReflex gain
additional routing surfaces.
