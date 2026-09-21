# PhiOS Dynamic State Lifecycle v0.1

## Status

Research-hardening candidate.

Primary contracts:

```text
phios.dynamic_state_policy.v0.1
phios.dynamic_state_receipt.v0.1

DynamicStatePolicy
DynamicStateDecayRule
DynamicStateReceipt
DynamicStateEvaluation
DynamicStateController
```

Primary rule:

```text
VALID THEN
!=
VALID FOREVER
```

DynamicField state is advisory. It can reshape route costs but cannot grant action
authority. That advisory influence must also have a lifecycle.

A failure observed yesterday, a contradiction seen ten minutes ago, and a resource
pressure spike measured one second ago are not automatically equivalent present-tense
signals.

v0.1 adds a deterministic temporal envelope without rewriting the existing DynamicField
law or replacing the v0.4-v0.8 governed routing/action chain.

## Relationship to DynamicField v0.3

The existing DynamicField contract remains the source of truth for:

- variable names;
- hard numeric bounds;
- initial values;
- permitted external event kinds;
- maximum external-event deltas;
- immutable governing-law SHA-256;
- append-only event-chain state.

The lifecycle layer does not add a second field law.

Instead:

```text
DynamicFieldLaw
      ↓
DynamicFieldState
      ↓
DynamicStatePolicy
      ↓
DynamicStateReceipt
      ↓
effective DynamicFieldState
```

The effective state remains bound to the original immutable law.

## DynamicStatePolicy

A policy contains:

```text
policy_id
version
max_state_age_seconds

rules[]:
  field_variable
  grace_seconds
  attenuation_rate_per_second
```

The canonical policy payload is SHA-256 bound.

### Complete variable coverage

The policy must contain exactly one rule for every variable in the DynamicField law.

Unknown variables are rejected.

Missing variables are rejected.

This prevents a field value from accidentally becoming immortal merely because the
temporal policy forgot it existed.

### Zero attenuation

A rule may set:

```text
attenuation_rate_per_second = 0
```

That means the variable holds its source value during the valid temporal window.

It does **not** mean infinite lifetime. The state-wide maximum age still terminates the
snapshot.

## Explicit time boundary

Evaluation requires:

```text
activated_at_utc
observed_at_utc
```

Both must be timezone-aware ISO-8601 timestamps.

The controller performs no hidden wall-clock read.

Therefore deterministic replay can evaluate the exact same temporal boundary later.

An observation before activation is rejected.

### Current limitation

v0.1 does not authenticate the supplied activation time.

The receipt proves:

> given this declared activation time, this policy, this source state, and this
> observation time, PhiOS computed this lifecycle result.

It does not independently prove:

> the activation timestamp is a trustworthy physical-world timestamp.

That stronger property belongs in a future temporal-anchor evidence contract rather than
being quietly assumed here.

## Attenuation model

Each variable moves toward its immutable-law initial value after its grace window.

For age (t):

```text
elapsed_attenuation =
max(0, t - grace_seconds)

maximum_change =
attenuation_rate_per_second
× elapsed_attenuation
```

PhiOS then moves the source value toward the law initial value by at most that amount.

It never overshoots the baseline.

Example:

```text
law initial historical_failure = 0.0
source historical_failure      = 1.0
rate                            = 0.1 / second
grace                           = 0
age                             = 5 seconds

effective historical_failure   = 0.5
```

At ten seconds the effective value reaches:

```text
0.0
```

and stops there.

## Source-anchored rather than recursive decay

For one temporal anchor, attenuation is calculated from the original source field state.

It is not calculated by repeatedly applying percentages to prior lifecycle output.

This avoids path-dependent results such as:

```text
evaluate at 5s
then evaluate that result at 10s
!=
evaluate source directly at 10s
```

Lifecycle-generated output is therefore not allowed to establish its own new activation
anchor.

## No self-renewing lease

When attenuation changes a field value, the generated effective DynamicField state
appends a deterministic event ID:

```text
dynamic-state:<transition digest prefix>
```

If that lifecycle-generated state is immediately offered as a fresh source, the
controller rejects it.

A fresh external DynamicField event must occur first.

So this does not work:

```text
stale state
  ↓ decay
lifecycle state
  ↓ "activate again"
new lease
  ↓ "activate again"
immortal stale influence
```

A genuine new external field event may create a new source anchor because it represents
new information entering the field.

## State materialization

When attenuation changes one or more values, the controller materializes a valid new
`DynamicFieldState` revision.

The transition:

- preserves the exact field-law SHA-256;
- validates every effective variable remains inside the original law bounds;
- increments the field revision;
- appends a deterministic lifecycle transition ID;
- advances the existing event-chain SHA-256;
- keeps `action_authority = false`.

If no attenuation is due, the source field state is returned unchanged and no fake
revision is created.

This detail matters because normal floating-point normalization must not manufacture a
state transition when the temporal policy did nothing.

## Termination

The state has a hard maximum age.

At:

```text
age >= max_state_age_seconds
```

the result is:

```text
status = TERMINATED
state_consumable = false
effective_state = null
```

PhiOS does not replace the stale state with zero, the baseline, or a guessed safe value.

It stops treating that snapshot as consumable.

That distinction avoids:

```text
unknown because stale
→ silently converted into
known baseline state
```

## DynamicStateReceipt

The receipt binds:

```text
schema
status
reason

policy_id
policy_sha256
field_law_sha256

source_field_state_sha256
source_field_revision
anchor_event_id

activated_at_utc
observed_at_utc
age_seconds
max_state_age_seconds

effective_field_state_sha256
effective_field_revision

transition_id
transition_sha256

changes[]
state_consumable
terminated

governing_law_mutated = false

operational_authority = false
action_authority      = false
execution_authority   = false

receipt_sha256
```

Each change records:

```text
field_variable
before
baseline
grace_seconds
attenuation_rate_per_second
elapsed_attenuation_seconds
after
```

The receipt is validated again when the effective state is consumed.

## Status vocabulary

### ACTIVE

The state remains inside its temporal window and no configured variable has changed yet.

No new DynamicField revision is manufactured.

### ATTENUATED

At least one variable has moved toward its immutable-law initial value.

A new deterministic DynamicField state revision is materialized.

### TERMINATED

The maximum state age has been reached.

No effective field state is returned.

## Hardened field-aware routing

`FieldAwareRouter` retains its legacy lower-level API for compatibility.

A hardened router can instead be configured with:

```text
require_dynamic_state_receipt = true
dynamic_state_controller = <controller bound to the frozen policy>
```

Then:

- raw DynamicFieldState is rejected;
- only a valid consumable DynamicStateEvaluation is accepted;
- the receipt field-law hash must match the router DynamicField law;
- the configured controller recomputes the policy result from the exact source state and receipt times;
- terminated state fails before route search begins.

The existing FieldAwareRouteReceipt format remains unchanged.

This is deliberate.

The route receipt binds the exact effective field-state SHA-256. The DynamicStateReceipt
binds that same effective state back to:

```text
source state
+
policy
+
activation time
+
observation time
+
attenuation calculation
```

This preserves the established route/replan/adoption/action receipt formats instead of
forcing an unrelated migration through the rest of the authority chain.

## Governed replanning

`GovernedReplanner.assess(...)` now accepts:

```text
DynamicFieldState
or
DynamicStateEvaluation
```

When used with a hardened router, both incumbent-path reassessment and candidate routing
consume the same temporal evaluation.

This allows old failure pressure to weaken over time and eventually change the preferred
route without weakening hard transition constraints.

Example:

```text
failure observed
historical_failure = 1.0

early:
  route avoids failure-sensitive path

later:
  historical_failure attenuates toward 0.0
  alternate route may become cheaper again

expired:
  snapshot cannot route at all
```

## Security and governance properties

v0.1 is designed to prevent:

- stale advisory influence with no lifecycle;
- accidental immortal variables omitted from policy;
- lifecycle output renewing its own activation window;
- temporal termination being converted into a guessed baseline;
- raw unreceipted state entering an explicitly hardened router;
- another temporal policy being substituted at routing time;
- dynamic decay mutating the immutable field law;
- dynamic decay gaining action or execution authority.

## What v0.1 does not claim

This contract does not prove:

- activation timestamp authenticity;
- that the selected decay rates are scientifically optimal;
- that every variable should decay toward its initial value in every deployment;
- that historical evidence should be deleted;
- that an attenuated signal is false;
- that hard constraints may weaken with time;
- that legacy routers automatically inherit this policy.

The policy is deliberately explicit and replaceable.

## Design rule

The intended architecture is:

```text
history remains evidence
influence remains temporary
authority remains separate
```

A failure can remain permanently auditable while its routing pressure attenuates.

Human beings have spent several thousand years proving that remembering something and
letting it control every future decision are, in fact, different operations.
