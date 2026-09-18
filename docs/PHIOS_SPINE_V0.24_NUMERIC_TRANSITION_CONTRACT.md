# PhiOS Spine v0.24 - Numeric Transition Contracts

Spine v0.24 adds a new Reality Gate claim kind:

`local_http_json_numeric_transition_contract`

It compares bounded numeric JSON values across adjacent observations without persisting the observed values themselves.

## Why this exists

Earlier repeated contracts answer questions about each snapshot independently:

> Did every observation satisfy this predicate?

v0.24 can answer a different question:

> Did this numeric field change between adjacent observations according to the admitted transition rule?

This introduces cross-snapshot semantic evidence without claiming timing, health, or causality.

## Core model

```text
2-5 discrete HTTP observations
        ↓
strict JSON parse per successful response
        ↓
extract admitted numeric pointer values transiently
        ↓
compare adjacent observation pairs
        ↓
persist relation + predicate outcome
        ↓
discard observed numeric values
        ↓
one transition-series evidence record
```

## Transition predicates

v0.24 deliberately supports only eight bounded predicates:

```text
integer_non_decreasing
integer_non_increasing
integer_strictly_increasing
integer_strictly_decreasing

number_non_decreasing
number_non_increasing
number_strictly_increasing
number_strictly_decreasing
```

No arbitrary expression language is added.

## JSON type semantics

Integer predicates require every admitted value to be a JSON integer.

Number predicates use the existing PhiOS JSON number rule and accept either:

- JSON integer;
- JSON number.

Booleans never count as integers.

Strict JSON decimal values are parsed with `Decimal`, preserving exact decimal comparison semantics.

## Adjacent-pair scope

For N observations, each transition clause evaluates N - 1 adjacent pairs.

For samples:

```text
0  1  2  3
```

the evaluated pairs are:

```text
0 → 1
1 → 2
2 → 3
```

v0.24 does not compare every sample against every other sample.

The evidence records:

`comparison_scope = adjacent_observation_pairs`

## Transition authority

Cross-snapshot comparison is stronger than one scalar read.

Every v0.24 claim requires:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`
- `reality.local_http.repeat.read`
- `reality.local_http.semantic.value.read`
- `reality.local_http.semantic.transition.read`

All grants are checked before the first provider call.

Thus:

```text
permission to inspect one scalar
      ≠
permission to retain it transiently across observations
      ≠
permission to compare cross-snapshot state
```

## Privacy boundary

The actual observed numbers are used only in the transient execution plane.

Persisted sample evidence may contain:

- pointer;
- transition predicate;
- expected JSON type;
- pointer-exists result;
- observed JSON type;
- type-match result;
- value-available Boolean.

Persisted pair evidence may contain:

- left/right sample indices;
- left/right observed JSON types;
- comparison-evaluated result;
- derived relation: `increase`, `equal`, or `decrease`;
- predicate-match result;
- verdict and reason.

Persisted evidence does not contain:

- left numeric value;
- right numeric value;
- raw delta;
- raw HTTP body;
- an `observed_value` field.

## Derived relation

The relation:

```text
increase
equal
decrease
```

is derived evidence.

It intentionally reveals ordering because ordering is the subject of the admitted claim.

It does not reveal numeric magnitude or delta.

## Observation failures

All requested observations are attempted after authority and validation succeed.

A transport failure or unavailable complete body is unresolved.

A status mismatch, invalid JSON, missing pointer, or wrong numeric JSON type is a contradiction of the admitted input contract.

Adjacent pairs touching an unresolved sample are unresolved.

Adjacent pairs touching a contradicted input are contradicted.

## Aggregate precedence

```text
any contradicted sample or transition pair
    → CONTRADICTED

else any unresolved sample or transition pair
    → UNRESOLVED

else
    → SUPPORTED
```

A later successful observation does not erase an earlier transition mismatch or unresolved sample.

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.repeat.read \
  --allow reality.local_http.semantic.value.read \
  --allow reality.local_http.semantic.transition.read \
  verify-claim \
  --kind local_http_json_numeric_transition_contract \
  --statement "Queue depth never increases across three observations." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --observation-count 3 \
  --json-transition-clause '{"pointer":"/queue_depth","predicate":"integer_non_increasing"}'
```

## What SUPPORTED means

A supported v0.24 claim establishes:

- every requested observation resolved successfully;
- every transition pointer existed;
- every transition input had the required JSON numeric type;
- every adjacent pair satisfied every admitted numeric transition predicate.

It does not establish:

- any particular elapsed time between observations;
- causality;
- rate of change;
- numeric delta;
- continuous monotonic behavior between observations;
- application health;
- future behavior.

## No implicit timing

v0.24 intentionally has no cadence or temporal-envelope fields.

The observations are discrete and unspaced by contract.

A transition such as:

```text
1 → 2 → 3
```

does not establish whether that happened across milliseconds or minutes.

Timing and transition semantics can be composed deliberately in a later release rather than silently coupling two authority axes.

## Frozen prior semantics

- v0.23 temporal-envelope semantics remain unchanged;
- v0.22 cadence semantics remain unchanged;
- v0.20 repeated mixed contracts remain unchanged;
- v0.18 scalar privacy remains unchanged.

v0.24 introduces its own transition-clause format instead of overloading mixed scalar clauses.

## Deliberate exclusions

v0.24 does not add:

- Boolean transition state machines;
- string transitions;
- arbitrary subtraction or delta persistence;
- percentage change;
- rate calculations;
- user-defined expressions;
- transition timing;
- background monitoring;
- remote HTTP;
- automatic health promotion.

## Design rule

```text
Repeated state is not state transition.
Scalar authority is not transition authority.
Compare transient values.
Persist relation, not magnitude.
Adjacent observed order is not continuous monotonicity.
Claim only what the bounded transition series establishes.
```
