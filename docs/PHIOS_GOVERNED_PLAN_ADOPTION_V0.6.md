# PhiOS Governed Plan Adoption v0.6

## Status

Governed Plan Adoption v0.6 adds the missing boundary between an advisory
`REPLAN` recommendation and a new incumbent plan.

The core rule is:

```text
REPLAN != ADOPT
ADOPT != EXECUTE
```

v0.6 introduces a typed, narrowly scoped adoption grant and an immutable plan
state. A recommendation can become the next incumbent plan only when the grant
matches the exact plan, exact replan receipt, and exact requested disposition.

## Flow

```text
v0.5 replan receipt
        ↓
current immutable plan state
        ↓
scoped PlanAdoptionGrant
        ↓
GovernedPlanAdoptionGate
        ↓
ADOPTED | REJECTED | HELD
        ↓
new incumbent plan state, if adopted
        ↓
separate execution authority
```

## Implementation

The implementation lives at:

```text
phios/core/governed_plan_adoption.py
```

Main public types:

- `PlanAdoptionGrant`
- `PlanState`
- `PlanAdoptionReceipt`
- `GovernedPlanAdoptionGate`

## Scoped grant

A `PlanAdoptionGrant` binds:

- grant ID;
- authority-source label;
- plan ID;
- exact current plan SHA-256;
- exact v0.5 replan receipt SHA-256;
- one disposition: `ADOPT`, `REJECT`, or `HOLD`.

The gate checks that scope exactly.

A grant for one plan revision cannot authorize another plan revision.
A grant for one replan receipt cannot authorize another recommendation.
A grant for `HOLD` cannot be reused as `ADOPT`.

The grant is an externally issued authority assertion. v0.6 verifies its
declared scope and deterministic identity; authentication of the external
issuer remains the responsibility of the authority source that creates it.

## Plan state

A `PlanState` records:

- plan ID;
- monotonic plan revision;
- incumbent path IDs;
- source route receipt SHA-256;
- optional source replan receipt SHA-256;
- parent plan SHA-256;
- `action_authority = false`;
- `execution_authority = false`;
- deterministic state SHA-256.

Adoption creates a new immutable state rather than mutating the previous state.

## Outcomes

### ADOPTED

Requires:

- a valid v0.5 `REPLAN` receipt;
- a found candidate route;
- a replan receipt that still refers to the current incumbent route;
- requested disposition `ADOPT`;
- a matching scoped grant.

The next plan revision adopts the candidate path and records both the candidate
route receipt and the v0.5 replan receipt as provenance.

### REJECTED

Requires a matching `REJECT` grant.

The current plan remains unchanged.

### HELD

Returned when:

- adoption authority is missing;
- grant scope does not match;
- the replan receipt is stale relative to the current plan;
- the v0.5 decision is not `REPLAN`;
- an authorized `HOLD` is requested.

`HELD` is fail-closed. It does not silently adopt a candidate.

## Stale-replan protection

A replan receipt records the previous route receipt SHA-256.

v0.6 requires that value to equal the current plan's source route receipt.

Therefore, once a newer plan revision is adopted, an older replan receipt can no
longer replace it.

```text
old REPLAN receipt
+
newer incumbent plan
=
HELD
```

## Tamper detection

v0.6 validates:

- v0.4 route receipt hashes when initializing a plan;
- v0.5 replan receipt hashes before adoption;
- current plan-state hashes before every transition.

Malformed or tampered receipts raise `PlanAdoptionContractError`.

Missing or mismatched authority is not treated as malformed data; it produces a
deterministic `HELD` receipt.

## Authority boundary

An adopted plan is an accepted incumbent plan, not permission to execute it.

Every plan state and adoption receipt retains:

```text
action_authority = false
execution_authority = false
```

v0.6 cannot:

- launch a process;
- invoke a tool;
- mutate an execution grant;
- bypass Reality Gate;
- grant itself additional scope;
- turn plan adoption into execution authority.

## Reasoning and governance stack

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
 ADOPTED / REJECTED / HELD
        ↓
separate execution authority
```

## Tests

Focused coverage verifies:

- matching authority adopts the candidate into a new plan revision;
- missing authority holds the plan;
- mismatched plan-state scope holds the plan;
- authorized rejection preserves the incumbent;
- authorized hold preserves the incumbent;
- `KEEP` cannot be promoted into adoption;
- stale replan receipts cannot replace newer plans;
- tampered replan receipts are rejected;
- tampered plan states are rejected;
- adoption receipts are deterministic;
- adopted plans retain zero execution authority.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```


---

## Next rung

Governed Plan Adoption v0.6 is followed by
[Governed Action Binding v0.7](PHIOS_GOVERNED_ACTION_BINDING_V0.7.md). v0.7
binds one exact transition from an immutable adopted plan to an existing Spine
capability and canonical payload digest, while leaving permission evaluation
and execution to the existing Spine authority path.
