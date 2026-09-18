# PhiOS Spine v0.19 - Same-Snapshot Mixed JSON Contracts

Spine v0.19 adds a new Reality Gate claim kind:

`local_http_json_mixed_contract`

It composes the existing JSON type, structural predicate, and scalar predicate semantics into one bounded contract evaluated against one HTTP observation.

## Why this exists

Before v0.19, PhiOS could prove:

- several type/structural facts from one response with v0.17; or
- one Boolean/numeric scalar predicate with v0.18.

Those were intentionally separate releases.

v0.19 combines them without rewriting either earlier contract.

```text
one GET
   ↓
one bounded body
   ↓
one digest + timestamp
   ↓
one strict JSON parse
   ↓
1-8 mixed clauses
   ├─ type
   ├─ structural
   └─ scalar
   ↓
one semantic evidence record
```

## New clause type

v0.19 uses `JsonMixedContractClause`.

It does not expand or reinterpret the frozen v0.17 `JsonContractClause`.

Each mixed clause has one JSON pointer and exactly one mode.

### Type

```json
{"pointer":"/models","type":"array"}
```

### Structural predicate

```json
{"pointer":"/models","predicate":"array_length_gte","bound":1}
```

### Scalar predicate

```json
{"pointer":"/ready","scalar_predicate":"boolean_is_true"}
```

or:

```json
{"pointer":"/queue_depth","scalar_predicate":"integer_lte","operand":"10"}
```

Unknown clause keys fail closed.

## Contract bounds

A mixed contract contains between 1 and 8 clauses.

Every pointer keeps the existing bounded JSON pointer rules.

Type names use the v0.15 whitelist.

Structural predicates use the v0.16 whitelist.

Scalar predicates use the v0.18 whitelist.

A clause must select exactly one mode.

## Conditional authority

Every mixed contract requires:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`

If and only if at least one admitted clause uses scalar inspection, the claim additionally requires:

- `reality.local_http.semantic.value.read`

The service determines this requirement from the validated clause list before provider I/O.

Therefore:

```text
type + structural only
        ↓
semantic.read is enough

type + structural + any scalar
        ↓
semantic.value.read also required
```

A missing value-read grant blocks the claim before the HTTP request.

## Same-snapshot semantics

The HTTP provider is invoked exactly once per mixed-contract claim.

When transport succeeds and the body is complete:

1. the response is parsed exactly once with strict JSON rules;
2. every clause is evaluated against the same parsed document;
3. clause evaluation continues after individual contradictions;
4. all results therefore describe the same point-in-time response.

This avoids treating facts from multiple network requests as though they necessarily described one system state.

## Evidence minimization

Persisted evidence may include:

- redacted HTTP observation metadata;
- expected HTTP status;
- normalized mixed clause definitions;
- whether scalar value-read authority was required;
- JSON validity;
- pointer existence;
- observed JSON types;
- type-match results;
- structural counts or Booleans already permitted by v0.16;
- predicate-match results;
- per-clause reasons;
- aggregate contract outcome.

For scalar clauses, persisted evidence does not contain:

- raw pointed Boolean values;
- raw pointed integer values;
- raw pointed number values;
- arbitrary pointed scalar contents.

There is no `observed_value` field.

The raw HTTP body remains absent from `LocalHttpObservation.to_dict()`.

## Clause outcomes

Per-clause reasons are bounded to:

- `matches`
- `pointer_missing`
- `type_mismatch`
- `predicate_mismatch`

All clauses are evaluated after JSON parsing succeeds, even when an earlier clause fails.

## Aggregate verdict

All clauses match:

`SUPPORTED / ACCEPTED`

At least one clause contradicts the captured document:

`CONTRADICTED / DISPUTED`

Wrong HTTP status:

`CONTRADICTED / DISPUTED`

Invalid JSON:

`CONTRADICTED / DISPUTED`

Transport failure, unavailable body, or truncated body:

`UNRESOLVED / UNKNOWN`

Missing authority or malformed contract:

`BLOCKED`

## CLI example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_mixed_contract \
  --statement "The local endpoint satisfies the bounded service contract." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --json-mixed-clause '{"pointer":"/models","type":"array"}' \
  --json-mixed-clause '{"pointer":"/models","predicate":"array_length_gte","bound":1}' \
  --json-mixed-clause '{"pointer":"/models/0/name","predicate":"string_non_empty"}' \
  --json-mixed-clause '{"pointer":"/ready","scalar_predicate":"boolean_is_true"}' \
  --json-mixed-clause '{"pointer":"/queue_depth","scalar_predicate":"integer_lte","operand":"10"}'
```

If the scalar clauses are removed, the value-read grant is no longer required.

## What a supported result means

A supported mixed contract establishes only that every admitted clause matched one captured local HTTP response at the recorded observation time.

It does not automatically establish:

- successful model inference;
- model loadability;
- database integrity;
- authentication correctness;
- remote reachability;
- general application health.

## Frozen earlier contracts

v0.17 remains the structural/type-only same-snapshot contract.

v0.18 remains the single scalar predicate contract.

v0.19 introduces a new clause type and claim kind rather than changing either older format.

## Deliberate exclusions

v0.19 still does not add:

- arbitrary string equality;
- secret or token matching;
- regex;
- substring search;
- JSONPath or JMESPath;
- user-defined expressions;
- executable code;
- JSON Schema;
- remote HTTP;
- automatic promotion to service health.

## Design rule

```text
One observation.
One parsed state.
Many bounded questions.
Authority follows the strongest question asked.
Persist the result, not the raw scalar.
Claim no more than the clauses establish.
```
