# PhiOS Relational Field Geometry v0.2

## Status

Relational Field Geometry v0.2 extends the merged Geometric Reasoning v0.1
foundation from state-space reduction into **advisory path geometry**.

v0.1 asks:

```text
which states are equivalent?
which regions are forbidden?
which targets are incompatible with conserved structure?
```

v0.2 adds:

```text
which transitions are admissible?
how costly is each admissible transition under the declared field?
which observed path has the least declared cost?
```

The layer remains non-authoritative:

```text
low cost
≠ permission

admissible under this field
≠ approved for execution

recommended path
≠ action authority
```

Every receipt records:

```text
action_authority = false
```

---

## Core separation

v0.2 deliberately separates **hard boundaries** from **soft geometry**.

### Hard transition constraints

Hard constraints decide whether an edge exists in the admissible graph.

Examples may include:

- explicit operator authority;
- immutable governance rules;
- required provenance;
- safety interlocks;
- conserved invariants;
- lifecycle preconditions.

If a hard constraint fails:

```text
transition = blocked
total_cost = null
```

No collection of soft advantages may compensate for that failure.

Formally, for transition `x -> y`:

```text
C_hard(x, y) = false
=> edge(x, y) does not exist in the admissible graph
```

This is how PhiOS preserves:

```text
capability ≠ authority
```

inside a field-based planner.

### Soft field geometry

Soft fields shape the cost of edges that already passed every hard gate.

Examples may include:

- resource pressure;
- uncertainty change;
- contradiction burden;
- provenance distance;
- latency;
- historical failure penalty;
- memory locality;
- model-switch cost.

A low soft cost never creates an edge that a hard gate removed.

---

## Implementation

The implementation lives at:

```text
phios/core/relational_field.py
```

Main public types:

- `FieldAxisSpec`
- `RelationCostSpec`
- `TransitionConstraintSpec`
- `AxisChange`
- `RelationCost`
- `TransitionReceipt`
- `FieldPathReceipt`
- `RelationalField`

---

## State fields

A state field is a scalar measurement:

```text
f_i(x)
```

with non-negative weight:

```text
w_i >= 0
```

The transition contribution is:

```text
w_i * |f_i(y) - f_i(x)|
```

This gives PhiOS a simple first metric over state change.

v0.2 does not claim every field is naturally symmetric. Directional or
relationship-specific quantities belong in pairwise relation costs instead.

---

## Pairwise relation costs

A pairwise relation cost directly evaluates:

```text
r_j(x, y) >= 0
```

with weight:

```text
v_j >= 0
```

Its contribution is:

```text
v_j * r_j(x, y)
```

This supports costs that cannot be described as simple changes of one scalar
state field.

For example, a domain could define directional costs for:

- crossing a provenance boundary;
- switching computational substrate;
- moving data between memory regions;
- choosing a historically unreliable transformation;
- changing model/tool families.

These costs remain advisory measurements.

---

## Transition cost

For an admissible transition, v0.2 computes:

```text
cost(x, y)
  = base_cost
  + sum_i w_i * |f_i(y) - f_i(x)|
  + sum_j v_j * r_j(x, y)
```

All components must be finite and non-negative.

That restriction is deliberate. It keeps bounded least-cost search compatible
with Dijkstra-style exploration and prevents negative cycles from turning
"preferred path" into a small mathematical prank with large operational
consequences.

---

## Least-declared-cost path

`RelationalField.least_cost_path(...)` performs bounded deterministic search
over transitions supplied by a domain-specific expansion function.

The result may be:

- `found`
- `exhausted_over_observed_graph`
- `limit_reached`

When found, the receipt records:

```text
optimality_scope = least_declared_cost_over_observed_graph
```

That scope is intentionally narrow.

It means least cost according to:

- the supplied state expansion;
- the declared hard constraints;
- the declared soft axes;
- the declared pairwise relation costs;
- the supplied non-negative base cost;
- the explored graph exposed by the caller.

It does **not** mean:

- globally optimal under every possible model;
- physically optimal;
- morally optimal;
- execution-approved;
- safe outside the supplied contract.

PhiOS is many things, but v0.2 is not allowed to discover ethics by adding
floats together.

---

## Determinism

v0.2 makes path selection deterministic under a deterministic domain contract.

- start states are ordered by stable state ID;
- expanded neighbors are ordered by stable state ID;
- equal-cost frontier entries are resolved by state ID;
- state IDs may not be reused for different observed states;
- receipts use canonical JSON and SHA-256.

Input callbacks remain part of the contract. Non-deterministic callbacks can
still produce non-deterministic graphs.

---

## Failure behavior

v0.2 fails closed where failure could accidentally broaden the graph.

- a hard-constraint exception blocks the transition;
- malformed state IDs are rejected;
- negative, infinite, or NaN weights/costs are rejected;
- axis-evaluation failures raise `RelationalFieldContractError`;
- relation-cost failures raise `RelationalFieldContractError`;
- goal or expansion failures raise `RelationalFieldContractError`;
- conflicting reuse of one state ID for different states is rejected;
- search is bounded by `max_states`.

---

## Relationship to v0.1

The two layers are complementary:

```text
Geometric Reasoning v0.1
  symmetry / quotienting
  forbidden regions
  conserved invariants
          ↓
Relational Field v0.2
  hard transition boundaries
  soft field costs
  pairwise relation costs
  least-declared-cost observed path
          ↓
exact verifier / Reality Gate
          ↓
separate explicit action authority
```

Future integrations may combine quotient reduction with relational field costs,
but v0.2 does not silently assume that quotient-equivalent states have identical
field costs or transition futures.

---

## Intended future domains

The v0.2 primitive can support later PhiOS work in:

- agent/tool routing;
- model selection;
- memory traversal;
- research search spaces;
- dependency planning;
- simulation;
- lifecycle planning;
- computational scheduling;
- evidence-directed exploration.

Those domains should define their own fields and hard constraints rather than
pretending one universal weighting system fits everything.

---

## Tests

Focused coverage verifies:

- scalar field change contributes deterministic cost;
- pairwise relation costs contribute directional cost;
- hard authority-like gates cannot be outvoted by low soft cost;
- hard-gate exceptions fail closed;
- path search follows declared geometry;
- blocked transitions disappear from the admissible path graph;
- equal-cost path selection is deterministic;
- negative weights are rejected;
- all receipts retain `action_authority = false`.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```
