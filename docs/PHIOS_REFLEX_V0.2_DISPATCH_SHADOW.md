# PhiReflex v0.2 — Dispatch Shadow Integration

## Status

PhiReflex v0.2 attaches the provider-neutral System-One layer to the real PhiOS
dispatch path in **strict shadow mode**.

The central rule is:

```text
observe dispatch
!=
influence dispatch
```

A PhiReflex result must not enter the planner context or operational plan before
planning occurs.

## Operational seam

PhiOS dispatch currently flows through:

```text
shell dispatch command
        ↓
build_dispatch_context(...)
        ↓
run_agentception_plan(...)
        ↓
dispatch_agentception_run(...)
```

v0.2 observes that flow **after** `run_agentception_plan(...)` returns.

That ordering is deliberate.

The planner receives the same operational context it would receive when
PhiReflex is disabled.

## CLI

Enable dispatch shadow observation explicitly:

```bash
phi dispatch "build the adapter" --dry-run --reflex-shadow
```

For a live dispatch:

```bash
phi dispatch "build the adapter" --reflex-shadow
```

The flag is opt-in. PhiOS does not silently introduce external Jev calls into
ordinary dispatch.

## What v0.2 records

`DispatchShadowReceipt` binds the PhiReflex observation to:

- canonical task SHA-256;
- canonical operational context SHA-256;
- canonical operational plan SHA-256;
- the full nested `ReflexShadowReceipt`;
- explicit `planner_influenced_by_reflex = false`;
- explicit context contamination flag;
- explicit plan contamination flag;
- zero action authority;
- zero execution authority.

This lets later evaluation compare a Reflex prediction to the exact dispatch
artifacts it observed.

## Contamination firewall

v0.2 fails closed if the operational planner context or generated plan already
contains PhiReflex/Jev material.

The purpose is not to ban those fields forever.

The purpose is to preserve the validity of the **shadow-mode experiment**.

If Reflex information enters planner input, then a later agreement between
Reflex and the plan is no longer independent evidence.

## Planner isolation

The dispatch shadow receipt is not inserted into:

```text
context
plan
remote planner payload
remote dispatch payload
```

For dry runs, it is returned beside those objects:

```json
{
  "context": { "...": "operational planner input" },
  "plan": { "...": "operational planner output" },
  "reflex_shadow": { "...": "separate observation" }
}
```

For live runs, it is persisted locally under:

```text
shadow_observations.phireflex_v0_2
```

The existing remote AgentCeption dispatch payload remains:

```text
task
context
plan
stream
```

with no Reflex material added.

## Storyboard persistence

The local dispatch storyboard includes the shadow observation so future review
can correlate:

- field state at dispatch;
- operational plan;
- dispatch events;
- PhiReflex prediction;
- later outcome.

This is evidence collection, not routing control.

## Side-effect signal

PhiReflex receives:

```text
tool_intent = true
```

for dispatch observation.

For dry-run dispatch:

```text
external_side_effect = false
```

For live dispatch:

```text
external_side_effect = true
```

This allows the Reflex risk model to distinguish planning from actual agent
dispatch without granting any additional authority.

## Jev behavior

When `--reflex-shadow` is enabled, v0.2 configures Jev as the optional shadow
provider.

If Jev is unavailable, unconfigured, or errors:

- local rules still produce the baseline;
- the operational dispatch path continues unchanged;
- the shadow receipt records `unavailable` or `error`.

The planner does not fail because Jev failed.

## Authority boundary

v0.2 cannot:

- select a planner;
- select a model;
- alter dispatch graph order;
- grant agent-dispatch authority;
- bypass `CAP_AGENT_DISPATCH`;
- change coherence gates;
- change the generated plan;
- authorize tools;
- authorize execution.

A Reflex result is still advisory information only.

## Why hashes matter

Suppose a later system reports:

```text
PhiReflex predicted builder / elevated risk
and the dispatch succeeded
```

Without artifact binding, that statement is weak.

v0.2 records the exact:

```text
context SHA
plan SHA
Reflex receipt SHA
```

so later evaluation can prove which prediction belonged to which operational
dispatch.

## Tests

v0.2 tests verify:

- a dispatch shadow receipt binds exact context and plan hashes;
- changing the plan changes the shadow receipt;
- Reflex material in planner context is rejected;
- Reflex material in operational plan is rejected;
- live-dispatch side-effect signaling reaches the baseline risk decision;
- local dispatch records may persist shadow observations separately;
- operational `context` stays free of Reflex material;
- operational `plan` stays free of Reflex material;
- `dispatch --dry-run --reflex-shadow` works without a TypeSafe key;
- every shadow receipt retains zero action and execution authority.

## Next step

The next useful rung is not automatic routing influence.

It is **outcome evaluation**:

```text
shadow prediction
        +
actual dispatch result
        ↓
calibration / usefulness receipt
```

Only after sufficient observed evidence should PhiOS consider a separately
governed contract that allows Reflex signals to influence routing.


---

## Next rung

PhiReflex v0.2 is followed by
[PhiReflex v0.3 Shadow Outcome Calibration](PHIOS_REFLEX_V0.3_OUTCOME_CALIBRATION.md).
v0.3 binds explicit post-run observations to the exact v0.2 shadow receipt and
scores only dimensions with real labels. Dispatch success/failure remains
outcome provenance, not implicit prediction ground truth.
