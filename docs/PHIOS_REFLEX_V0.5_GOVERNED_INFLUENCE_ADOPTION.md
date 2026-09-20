# PhiReflex v0.5 — Governed Influence Adoption

## Status

PhiReflex v0.5 introduces the governance boundary between:

```text
REVIEW_ELIGIBLE
```

and:

```text
an adopted Reflex influence policy
```

The central rule is:

```text
REVIEW_ELIGIBLE
!=
PROMOTED

ADOPTED INFLUENCE POLICY
!=
ACTIVE ROUTING INFLUENCE
```

v0.5 may create an immutable influence-policy state, but that state remains
runtime-inactive.

## Inputs

v0.5 consumes:

- one exact v0.4 readiness receipt;
- one requested disposition;
- one requested influence scope;
- one exact externally issued `ReflexInfluenceGrant`;
- optionally, the current immutable v0.5 influence-policy state.

The readiness receipt must validate exactly and must have:

```text
status = REVIEW_ELIGIBLE
```

before adoption is even considered.

## External grant scope

A `ReflexInfluenceGrant` binds:

- grant ID;
- authority-source label;
- exact v0.4 readiness receipt SHA-256;
- exact current influence-policy state SHA-256, or null for first adoption;
- candidate provider;
- allowed signal dimensions;
- maximum influence weight;
- rollback-on-provider-unavailable policy;
- maximum consecutive provider errors;
- requested disposition.

A grant for one readiness receipt cannot authorize another.

A grant for one current policy revision cannot overwrite a newer revision.

A grant for:

```text
role + system2
weight <= 0.20
```

cannot authorize:

```text
role + risk + system2
weight <= 0.50
```

## Supported dimensions

The v0.5 influence-policy contract can scope:

```text
role
risk
system2
verification
```

The dimensions are normalized and must be unique.

The state records permission to consider those signals in a future activation
layer.

It does not currently feed those signals into dispatch.

## Maximum influence weight

The policy records an explicit:

```text
max_influence_weight
```

in the range:

```text
0 < weight <= 1
```

v0.5 does not define the runtime blending equation.

The value is a ceiling for a future activation/integration contract.

That future layer must define exactly how the weight applies and must not infer
new semantics from this number.

## Rollback posture

The adopted policy also records:

- whether provider unavailability requires rollback;
- maximum consecutive provider errors before rollback is required.

These are policy inputs for a later runtime activation layer.

v0.5 itself does not count provider failures or perform rollback.

## Immutable policy state

An adopted `ReflexInfluencePolicyState` records:

- policy ID;
- monotonic revision;
- exact readiness receipt SHA-256;
- candidate provider;
- exact candidate model identities from the readiness receipt;
- allowed dimensions;
- maximum influence weight;
- rollback-on-unavailability setting;
- maximum consecutive provider errors;
- parent policy SHA-256;
- runtime-inactive authority flags;
- deterministic state SHA-256.

Updates create a new immutable state revision.

## Candidate model binding

v0.5 snapshots the candidate model identities from the exact v0.4 readiness
receipt.

For example:

```text
provider = jev
models = ("jev-test",)
```

A future runtime activation contract must revalidate that the provider/model
being used matches the adopted policy.

Provider name alone is not enough.

## Outcomes

### ADOPTED

Requires:

- valid v0.4 receipt;
- `REVIEW_ELIGIBLE`;
- exact matching external grant;
- requested disposition `ADOPT`.

Creates a new immutable policy state.

### REJECTED

Requires an exact matching grant with disposition `REJECT`.

No new policy state is created.

### HELD

Returned when:

- readiness is not `REVIEW_ELIGIBLE`;
- grant is missing;
- readiness scope mismatches;
- current-policy scope mismatches;
- provider mismatches;
- dimension scope mismatches;
- influence-weight scope mismatches;
- rollback scope mismatches;
- error-limit scope mismatches;
- disposition scope mismatches;
- disposition is an explicitly authorized `HOLD`.

## Stale-policy protection

When an influence policy already exists, a new grant must bind its exact
`state_sha256`.

Therefore:

```text
grant for revision 0
+
current revision 1
=
HELD
```

An older approval cannot overwrite a newer policy state.

## Tamper detection

v0.5 validates:

- v0.4 readiness receipt hash;
- v0.4 zero-authority flags;
- readiness status;
- source calibration receipt digests;
- candidate model list;
- current v0.5 policy-state hash;
- all scope inputs.

Tampered readiness evidence or policy state is rejected as malformed rather
than converted to `HELD`.

## Authority boundary

Every adopted v0.5 policy state retains:

```text
routing_influence_active = false
runtime_activation_authority = false
promotion_authority = false
action_authority = false
execution_authority = false
```

Every adoption receipt retains the same boundary.

Therefore v0.5 cannot:

- alter dispatch behavior;
- change Crane Fly / agent routing;
- inject Jev probabilities into planner context;
- activate an influence weight;
- promote Jev;
- grant tools;
- grant execution;
- bypass CAPS;
- bypass Spine permissions.

The grant authorizes **policy adoption only**.

## Why there is no one-command self-grant

v0.5 exposes a typed grant contract but intentionally does not add a shell
shortcut that silently creates the grant and consumes it in the same operation.

A future operator/governance surface may issue a
`ReflexInfluenceGrant`, but grant issuance and grant consumption should remain
separate auditable steps.

This mirrors the broader PhiOS rule:

```text
capability
!=
authority
```

## Tests

v0.5 tests verify:

- exact `REVIEW_ELIGIBLE` receipt + exact grant adopts an inactive policy;
- missing authority returns `HELD`;
- non-review-eligible evidence cannot be adopted;
- dimension-scope mismatch returns `HELD`;
- authorized rejection creates no policy;
- stale current-policy scope is rejected;
- exact current-policy scope allows a new immutable revision;
- tampered readiness receipts are rejected;
- tampered policy states are rejected;
- adopted state carries zero runtime/promotion/action/execution authority.

## Next rung

The next safe rung is **runtime influence activation**, not direct unrestricted
routing.

A future v0.6 should require:

- exact adopted v0.5 policy state;
- exact provider/model identity;
- an explicit activation grant;
- a declared routing surface;
- a defined blending equation;
- hard maximum influence weight;
- deterministic fallback;
- provider-unavailable rollback;
- consecutive-error rollback;
- runtime receipts;
- easy operator deactivation.

Only that layer should be allowed to set:

```text
routing_influence_active = true
```

and even then it must not gain action or execution authority.
