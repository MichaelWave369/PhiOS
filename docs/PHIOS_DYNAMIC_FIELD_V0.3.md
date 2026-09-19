# PhiOS Dynamic Field State v0.3

## Status

Dynamic Field State v0.3 extends the geometric / relational reasoning stack with
**bounded field evolution over time**.

The previous rungs established:

```text
v0.1
shape / quotient / invariants

v0.2
admissible edges / relational cost / path geometry
```

v0.3 adds:

```text
evidence / contradiction / failure / resource signal
                    ↓
             bounded field event
                    ↓
          immutable governing law
                    ↓
          new advisory field state
```

The defining rule is:

```text
the field may change
the governing law may not
```

Every state and update receipt remains non-authoritative:

```text
action_authority = false
```

---

## Why this exists

A static field cannot represent learning.

Evidence can reduce uncertainty.
Contradiction can increase uncertainty.
Repeated failures can raise a historical-failure field.
Resource observations can increase or decrease pressure.

Those changes should affect later advisory routing without allowing the system
to rewrite the rules that define valid updates.

Formally, v0.3 separates:

```text
L = immutable governing law
F_t = dynamic advisory field state
E_t = bounded event

F_(t+1) = U_L(F_t, E_t)
```

The update function is governed by `L`.

The event cannot replace `L`.

---

## Implementation

The implementation lives at:

```text
phios/core/dynamic_field.py
```

Main public types:

- `FieldVariableRule`
- `DynamicFieldLaw`
- `FieldEvent`
- `DynamicFieldState`
- `FieldValueChange`
- `FieldUpdateReceipt`
- `DynamicField`

---

## Immutable governing law

Each field variable has a fixed rule declaring:

- variable name;
- minimum value;
- maximum value;
- initial value;
- event kinds allowed to modify it;
- maximum absolute delta per event.

Example conceptually:

```text
uncertainty:
  bounds = [0.0, 1.0]
  initial = 0.8
  allowed events = evidence, contradiction
  max |delta| = 0.4
```

The complete law is canonically hashed:

```text
law_sha256
```

Every dynamic state is bound to that exact law hash.

A state created under one law cannot be evolved by another law.

This turns law identity into a verifiable contract rather than an ambient
assumption.

---

## Dynamic field state

A state snapshot contains:

- exact governing-law SHA-256;
- monotonic revision;
- current bounded field values;
- ordered applied-event IDs;
- event-chain SHA-256;
- explicit zero action authority;
- state SHA-256.

State snapshots are immutable Python dataclasses.

Applying an event creates a new snapshot rather than mutating the prior one in
place.

That preserves the transition:

```text
F_t
 ↓ event
F_(t+1)
```

as an inspectable provenance path.

---

## Field events

An event contains:

- stable `event_id`;
- event `kind`;
- requested variable deltas;
- source label;
- optional evidence SHA-256.

The optional evidence digest allows a field change to be anchored to an
external artifact or observation without embedding the evidence itself in the
dynamic field state.

An event may request only variables already declared by the law.

This means an event cannot smuggle in a new variable such as:

```text
authority = 1
```

unless the governing law itself had explicitly defined such a field beforehand.

v0.3 does not define authority as a dynamic field variable.

---

## Bounded updates

For each requested change:

```text
x_(t+1) = x_t + delta
```

the law requires:

```text
event kind is allowed
|delta| <= max_abs_delta
minimum <= x_(t+1) <= maximum
```

v0.3 does **not** silently clamp oversized or out-of-range updates.

If an otherwise well-formed event violates an update rule, the entire event is
blocked and the prior field state is returned unchanged.

This preserves atomicity:

```text
all requested changes pass
or
none are applied
```

---

## Failure may change routing without changing governance

A declared law can include a field such as:

```text
historical_failure
```

and permit only `failure` or `recovery` events to change it.

A failed operation can therefore produce:

```text
historical_failure: 2.0 -> 3.0
```

Later routing can treat that higher field value as a soft cost input.

What did **not** change:

- the hard authority model;
- transition constraints;
- permission grants;
- the governing law;
- Reality Gate semantics.

So failure may reshape the advisory landscape without promoting itself into a
rule-making mechanism.

That is the intended boundary.

---

## Replay protection

Applied event IDs are retained in the state.

If the same event ID is presented again:

```text
status = blocked
blocked_by = event_replay
```

The field remains unchanged.

This prevents one evidence or failure event from being accidentally counted
multiple times in the same state lineage.

---

## Event chain

Each accepted event extends a deterministic hash chain:

```text
chain_(t+1)
  = SHA256(chain_t || event_sha256)
```

The chain does not prove that an event was true.

It proves which accepted event sequence produced the present field state under
the declared update law.

Evidence validity remains the job of the relevant evidence / verification
layer.

---

## Tamper detection

Before applying an event, v0.3 verifies:

- state schema;
- governing-law hash;
- zero action authority;
- revision / event-count consistency;
- exact field-variable set;
- field bounds;
- uniqueness of accepted event IDs;
- state SHA-256.

A modified state snapshot is rejected rather than silently normalized.

---

## Blocked vs malformed

v0.3 distinguishes two categories.

### Valid event blocked by law

Examples:

- replayed event ID;
- event kind not permitted for that variable;
- delta exceeds declared maximum;
- resulting value would leave declared bounds.

These return a deterministic `blocked` receipt and leave the state unchanged.

### Malformed contract

Examples:

- unknown field variable;
- invalid SHA-256 evidence digest;
- empty event identity;
- state bound to another law;
- state-hash mismatch.

These raise `DynamicFieldContractError`.

The distinction prevents malformed structure from being treated as merely an
ordinary routing outcome.

---

## Authority boundary

Dynamic field evolution is advisory.

A field update cannot:

- grant permission;
- revoke operator authority;
- mutate a grant;
- change a hard transition constraint;
- rewrite the governing law;
- bypass Reality Gate;
- execute a selected path;
- promote a model or adapter.

Every update receipt states:

```text
governing_law_mutated = false
action_authority = false
```

A later subsystem may read field values when computing advisory costs, but
execution still requires its normal independent authority checks.

---

## Relationship to v0.1 and v0.2

The reasoning stack now becomes:

```text
Geometric Reasoning v0.1
  equivalence
  constraints
  invariants
        ↓
Relational Field Geometry v0.2
  hard transition boundaries
  soft path geometry
  least-declared-cost paths
        ↓
Dynamic Field State v0.3
  evidence-driven field evolution
  failure history
  resource change
  replay-safe provenance
        ↓
Reality Gate / exact verification
        ↓
separate explicit action authority
```

v0.3 changes the **inputs to later advisory geometry**.

It does not alter the authority architecture surrounding that geometry.

---

## Tests

Focused coverage verifies:

- deterministic initialization bound to the exact law;
- evidence can change a permitted field variable;
- failure can alter historical-failure state;
- governing-law hash remains unchanged;
- disallowed event kinds are blocked atomically;
- oversized deltas are blocked rather than clamped;
- out-of-bound results are blocked;
- replayed event IDs are blocked;
- unknown variables cannot smuggle governance changes;
- law-hash mismatch is rejected;
- state-hash tampering is rejected;
- identical accepted event sequences reproduce identical state and receipts;
- all states and receipts retain zero action authority.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```


---

## Next rung

Dynamic Field State v0.3 is integrated into advisory path selection by
[Field-Aware Routing v0.4](PHIOS_FIELD_AWARE_ROUTING_V0.4.md). v0.4 binds one
exact validated field snapshot into explicit relational cost terms while hard
transition constraints and execution authority remain separate.
