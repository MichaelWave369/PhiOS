# PhiOS Field-Aware Routing v0.4

## Status

Field-Aware Routing v0.4 integrates the merged reasoning stack:

```text
v0.1 geometric reduction
v0.2 relational field geometry
v0.3 dynamic field state
        ↓
v0.4 exact-snapshot field-aware routing
```

The route remains advisory:

```text
recommended route
≠ execution authority
```

Every v0.4 receipt records `action_authority = false`.

## Purpose

v0.3 lets evidence, contradiction, failure history, and resource observations
change bounded advisory field values. v0.4 projects one exact validated field
snapshot into v0.2 route costs.

A route preferred at field state `F_t` may therefore differ from the route
preferred at `F_(t+1)`, while the governing law and hard constraints remain
unchanged.

## Implementation

The implementation lives at:

```text
phios/core/field_aware_routing.py
```

Main public types:

- `DynamicCostBinding`
- `DynamicBindingSnapshot`
- `FieldAwareRouteReceipt`
- `FieldAwareRouter`

v0.4 also exposes `DynamicField.validate_state(...)` so integration layers can
validate v0.3 snapshots before consuming their values.

## Dynamic cost binding

Each binding names:

- one dynamic field variable;
- one transition-susceptibility function;
- one non-negative scale.

The dynamic contribution is:

```text
dynamic_cost(x, y)
  = scale
  * live_field_value
  * transition_susceptibility(x, y)
```

This lets a live field reshape relative route costs without inventing new
transitions or changing static law.

## Hard constraints remain absolute

The evaluation order remains:

```text
hard constraint
      ↓
edge exists / edge does not exist
      ↓
only then compute soft cost
```

A forbidden edge is absent from the admissible graph. Dynamic cost cannot make
it cheap enough to return.

Thus:

```text
blocked
≠ expensive
```

## Exact snapshot binding

Before search, v0.4 validates the supplied v0.3 state against its immutable law.

The route receipt records:

- governing-law SHA-256;
- exact field-state SHA-256;
- field revision;
- each binding name and field variable;
- exact field value and scale used;
- underlying v0.2 path-receipt SHA-256;
- path IDs and total declared cost;
- zero action authority.

Past route receipts therefore remain bound to the field state that produced
them even after the live field advances.

## Routing claim scope

v0.4 records:

```text
optimality_scope =
least_declared_cost_over_observed_graph_at_exact_field_snapshot
```

The claim is limited to the supplied graph, hard constraints, static costs,
explicit dynamic bindings, exact field snapshot, base cost, and bounded search.

It is not a claim of universal or execution-level optimality.

## Non-negative cost contract

Dynamic bindings may reference only field variables whose governing minimum is
non-negative. Binding scale and transition susceptibility must also be
non-negative.

This preserves the non-negative path-cost contract used by v0.2.

Signed field variables require a future explicit transformation contract rather
than silent reinterpretation.

## Authority boundary

v0.4 may recommend a different route. It may not:

- execute that route;
- create or expand a grant;
- bypass hard transition constraints;
- rewrite the Dynamic Field law;
- alter Reality Gate verdicts;
- promote a model or adapter;
- mutate operator policy.

## Reasoning stack

```text
Geometric Reasoning v0.1
  reduce equivalent state
        ↓
Relational Field Geometry v0.2
  hard edges + soft path cost
        ↓
Dynamic Field State v0.3
  evolve bounded advisory state
        ↓
Field-Aware Routing v0.4
  exact field snapshot → route cost
        ↓
Reality Gate / exact verification
        ↓
separate explicit execution authority
```

## Tests

Focused coverage verifies:

- failure history can alter the preferred path;
- receipts bind the exact dynamic-field state SHA-256;
- hard constraints remain absolute;
- routing is deterministic for one exact snapshot;
- tampered field snapshots are rejected;
- unknown dynamic variables cannot be bound;
- negative-domain variables cannot directly enter v0.4 cost;
- negative transition susceptibility is rejected;
- route receipts retain zero action authority.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```


---

## Next rung

Field-Aware Routing v0.4 is stabilized by
[Governed Replanning v0.5](PHIOS_GOVERNED_REPLANNING_V0.5.md). v0.5 re-scores
the incumbent and fresh candidate under the same current field snapshot and
uses a fixed hysteresis policy to emit KEEP, REPLAN, or UNRESOLVED without
granting execution authority.
