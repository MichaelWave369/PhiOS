# PhiOS Governed Replanning v0.5

## Status

Governed Replanning v0.5 adds **stable adaptive routing** to the merged PhiOS
reasoning stack.

The previous rungs established:

```text
v0.1  geometric reduction
v0.2  relational field geometry
v0.3  dynamic field state
v0.4  exact-snapshot field-aware routing
```

v0.5 adds:

```text
previous recommendation
        ↓
new field snapshot
        ↓
re-score incumbent under new snapshot
        +
compute fresh candidate under same snapshot
        ↓
fixed hysteresis policy
        ↓
KEEP | REPLAN | UNRESOLVED
```

The result remains advisory:

```text
REPLAN
≠ execution authority
```

Every v0.5 receipt records `action_authority = false`.

## Same-snapshot comparison

A stale route cost from field state `F_t` must not be compared directly with a
candidate cost from `F_(t+1)`.

v0.5 evaluates both alternatives under the exact current field snapshot:

```text
incumbent_current_cost
  = cost(incumbent | F_current)

candidate_current_cost
  = cost(candidate | F_current)

improvement
  = incumbent_current_cost - candidate_current_cost
```

This prevents fake improvement created by comparing costs from different field
revisions.

## Implementation

The main implementation lives at:

```text
phios/core/governed_replanning.py
```

Main public types:

- `ReplanPolicy`
- `GovernedReplanReceipt`
- `GovernedReplanner`

v0.5 also extends `phios/core/field_aware_routing.py` with:

- `FieldAwarePathAssessmentReceipt`
- `FieldAwareRouter.assess_path(...)`

so an explicit incumbent path can be re-scored under one exact validated field
snapshot.

## Replan policy

The immutable hysteresis policy declares:

```text
policy_id
minimum_cost_improvement
```

A changed candidate route replaces an admissible incumbent only when:

```text
improvement > minimum_cost_improvement
```

The strict greater-than comparison creates a deadband. Improvement exactly
equal to the threshold yields `KEEP`.

## Decisions

v0.5 emits exactly three advisory decisions.

### KEEP

Returned when the same route remains preferred, or a changed candidate does not
beat the incumbent by more than the hysteresis threshold.

### REPLAN

Returned when a changed candidate materially improves current cost, or the
incumbent path is now hard-blocked and a candidate route exists.

A blocked incumbent bypasses the soft threshold because:

```text
inadmissible
≠ merely expensive
```

### UNRESOLVED

Returned when current candidate search does not produce a found route.

```text
no better route found
≠
proved incumbent is best
```

v0.5 therefore does not silently convert an unresolved search into `KEEP`.

## Incumbent provenance

The previous v0.4 route receipt is validated before use.

v0.5 requires:

- supported v0.4 receipt schema;
- `action_authority = false`;
- status `found`;
- non-empty path IDs;
- matching receipt SHA-256.

The explicit incumbent path supplied for re-scoring must reproduce the exact
path IDs recorded in that previous route receipt.

## Field-time monotonicity

The current dynamic field revision may be equal to or later than the revision
that produced the previous route.

A regression:

```text
current_revision < previous_route_revision
```

is rejected as a contract error.

## Hard constraints

Both incumbent and candidate are evaluated through the existing v0.4/v0.2
routing stack.

If the incumbent contains a transition that is now blocked and a valid
candidate exists:

```text
incumbent_status = blocked
decision = REPLAN
reason = incumbent_path_blocked
```

The hysteresis threshold cannot rescue an inadmissible path.

## Deterministic receipts

Each v0.5 receipt binds:

- policy ID and policy SHA-256;
- hysteresis threshold;
- previous route receipt SHA-256;
- previous field-state SHA-256;
- exact current field-state SHA-256;
- current field revision;
- incumbent assessment SHA-256;
- incumbent path, status, and current cost;
- candidate route receipt SHA-256;
- candidate path, status, and current cost;
- route-changed flag;
- computed improvement;
- decision and reason;
- comparison scope;
- zero action authority.

The comparison scope is:

```text
incumbent_and_candidate_evaluated_at_exact_current_field_snapshot
```

## Stable adaptation

The stack now distinguishes:

```text
adaptation
  field state changes

routing
  preferred path changes

replanning
  decides whether the new preference is materially strong enough
  to replace the incumbent recommendation
```

That keeps tiny field fluctuations from becoming constant route churn.

## Authority boundary

A v0.5 `REPLAN` receipt may recommend replacing an advisory route.

It may not:

- execute the replacement;
- launch a program;
- mutate or create a grant;
- bypass a hard gate;
- alter the Dynamic Field law;
- rewrite the replan policy;
- change a Reality Gate verdict;
- promote a model or adapter.

Execution remains separately authorized.

## Reasoning stack

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
  KEEP / REPLAN / UNRESOLVED
        ↓
Reality Gate / exact verification
        ↓
separate explicit execution authority
```

## Tests

Focused coverage verifies:

- same-snapshot incumbent/candidate comparison;
- material improvement produces `REPLAN`;
- small improvement inside hysteresis produces `KEEP`;
- unchanged route produces `KEEP`;
- newly blocked incumbent produces `REPLAN` when a candidate exists;
- unresolved candidate search produces `UNRESOLVED`;
- tampered previous route receipts are rejected;
- field-revision regression is rejected;
- negative hysteresis thresholds are rejected;
- repeated assessment is deterministic;
- every receipt retains zero action authority.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```


---

## Next rung

Governed Replanning v0.5 is followed by
[Governed Plan Adoption v0.6](PHIOS_GOVERNED_PLAN_ADOPTION_V0.6.md). v0.6 makes
REPLAN explicitly non-self-executing: a narrowly scoped external grant must
match the exact plan state, exact replan receipt, and requested disposition
before the candidate can become a new immutable incumbent plan revision.
