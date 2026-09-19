# PhiOS Geometric Reasoning v0.1

## Status

Geometric Reasoning v0.1 is an **advisory core primitive** for reducing large
computational state spaces before exact verification.

It is intentionally non-authoritative:

```text
reasoning capability
≠ execution authority

equivalent representation
≠ identical provenance

search reduction
≠ proof of correctness

invariant mismatch
≠ universal impossibility
```

Every v0.1 receipt records:

```text
action_authority = false
```

The human/operator authority model remains unchanged.

---

## Purpose

Brute-force search treats every generated state as if it deserves independent
work. Many PhiOS workloads contain symmetry, repeated structure, forbidden
regions, or conserved quantities that allow large parts of a search space to be
collapsed or ruled out first.

v0.1 introduces four structural ideas:

1. **equivalence classes** — structurally equivalent states share one quotient
   class;
2. **constraints** — invalid states are pruned before expansion;
3. **conserved invariants** — mismatched conserved values can establish that a
   target is unreachable under the declared transition system;
4. **quotient-space search** — only one representative of each equivalence
   class is expanded.

The operating rule is:

```text
reason about the shape first
        ↓
remove forbidden regions
        ↓
quotient equivalent states
        ↓
prove away incompatible targets
        ↓
search remaining representatives
        ↓
exact verification / Reality Gate
```

---

## Implementation

The implementation lives at:

```text
phios/core/geometric_reasoning.py
```

Main public types:

- `ConstraintSpec`
- `InvariantSpec`
- `QuotientClass`
- `ReductionReceipt`
- `InvariantReceipt`
- `SearchReceipt`
- `GeometricReasoner`

The engine accepts domain-provided functions for:

- stable state identity;
- equivalence keys;
- admissibility constraints;
- invariants;
- state expansion;
- goal recognition.

PhiOS therefore owns the **governed reduction mechanism** without pretending
that one universal geometry describes every workload.

---

## Quotient reduction

Given raw states (S) and a declared equivalence relation represented by a
canonical key, v0.1 builds a quotient view:

```text
S / ~
```

Only admissible states enter the quotient.

For example:

```text
(0, 1) ~ (1, 0)
```

under coordinate-swap symmetry can be represented by one quotient class.

The reduction receipt records:

- raw state count;
- admissible state count;
- rejected state count;
- quotient-class count;
- deterministic representative IDs;
- member IDs;
- rejection reasons;
- canonical SHA-256;
- zero action authority.

---

## Conserved-invariant reasoning

A workload may declare an invariant as conserved by its transition set.

If:

```text
I(source) != I(target)
```

for a declared conserved invariant, v0.1 may emit:

```text
unreachable_under_conserved_invariants
```

This claim is deliberately narrow.

It means the target is unreachable **under the supplied transition model and
the supplied conservation declaration**.

It does not establish that the target is impossible under every conceivable
system, transformation, or future capability.

If conserved invariants match, the result is only:

```text
not_disproved_by_conserved_invariants
```

That is not proof of reachability.

---

## Quotient-space search

The bounded search engine performs deterministic breadth-first exploration over
equivalence classes.

Search is disabled by default. The caller must explicitly set
`quotient_search_safe=True`, declaring that the chosen equivalence relation
preserves the transition and goal structure relevant to that search. The
declaration is not itself proof, but it prevents PhiOS from silently assuming
that representational equivalence implies identical futures.

When a newly generated state belongs to an already visited class, it is counted
as:

```text
equivalent_states_skipped
```

and is not expanded again.

Search receipts distinguish:

- `found`
- `exhausted_under_declared_geometry`
- `limit_reached`

and record:

- raw states seen;
- quotient classes visited;
- constraint-pruned states;
- equivalent states skipped;
- representative path;
- solution state ID when found;
- the explicit quotient-search-safety declaration;
- canonical SHA-256;
- zero action authority.

---

## Failure behavior

v0.1 fails closed around the structural contract.

- malformed or non-canonical equivalence keys are rejected;
- duplicate state IDs are rejected for explicit reduction;
- duplicate constraint/invariant names are rejected;
- constraint exceptions classify that state as rejected;
- invariant-evaluation failure raises `GeometryContractError`;
- expansion or goal-predicate failure raises `GeometryContractError`;
- quotient search is refused unless quotient safety is explicitly declared;
- search is bounded by `max_classes`.

The engine does not silently invent geometry when a domain contract cannot be
evaluated.

---

## Determinism

Receipts use canonical JSON and SHA-256.

Reduction input order does not change the resulting receipt when the state set
and declared geometry are otherwise identical.

For search, neighbor states are ordered by stable state ID before they are
queued. Domain-provided state IDs and transition functions therefore remain part
of the deterministic contract.

---

## Authority boundary

Geometric reasoning may reduce work. It may not grant permission.

A geometric result cannot by itself:

- launch a program;
- mutate a file;
- approve an app install;
- promote a kernel adapter;
- bypass a Reality Gate;
- expand a permission set;
- rewrite a governing rule.

Any later action must pass through the same explicit authority path it required
before geometric reasoning existed.

This preserves the PhiOS rule:

```text
capability ≠ authority
```

while adding another one:

```text
representation ≠ distinct state
```

---

## Why this matters for PhiOS

The geometric layer gives PhiOS a reusable way to stop treating every possible
representation as independent work.

It can eventually support domains such as:

- research-state enumeration;
- configuration solving;
- governed agent planning;
- dependency and lifecycle planning;
- simulation;
- topology-aware routing;
- field-weighted computational scheduling.

Those integrations are future rungs. v0.1 deliberately establishes the small,
testable structural primitive first.

---

## Tests

Current focused coverage verifies:

- symmetry-equivalent states collapse into one quotient class;
- invalid regions are pruned;
- conserved-invariant mismatch produces a narrow unreachable result;
- quotient search skips already visited equivalent states;
- receipts are deterministic across input ordering;
- constraint exceptions fail closed;
- all receipts retain `action_authority = false`.

The normal PhiOS CI gates remain authoritative for merge:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```
