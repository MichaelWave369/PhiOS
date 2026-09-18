# PhiOS Spine v0.18 - Bounded JSON Scalar Predicates

Spine v0.18 adds a new Reality Gate claim kind:

`local_http_json_scalar_predicate`

The purpose is to inspect one bounded scalar value transiently, evaluate one whitelisted predicate, and persist only the type and comparison outcome rather than the observed value.

## Epistemic rung

```text
HTTP response
    ↓
strict JSON
    ↓
pointer exists
    ↓
scalar has required type
    ↓
bounded value predicate
    ↓
comparison outcome only
```

v0.18 does not turn a scalar match into general application health.

## Stronger authority boundary

Structural semantic reads from v0.15-v0.17 require:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`

v0.18 additionally requires:

- `reality.local_http.semantic.value.read`

This is intentional. Inspecting whether an array has two elements is not the same authority as inspecting whether a particular scalar value is true, false, larger, or smaller than a threshold.

## Whitelisted predicates

Boolean:

- `boolean_is_true`
- `boolean_is_false`

Integer:

- `integer_eq`
- `integer_gte`
- `integer_lte`

Number:

- `number_eq`
- `number_gte`
- `number_lte`

Boolean predicates do not accept an operand.

Integer and number predicates require an explicit numeric operand. Operands are limited to 64 characters and must parse as finite decimal values. Integer predicates additionally require an integral operand.

## Type semantics

`integer_*` predicates require a JSON integer.

`number_*` predicates accept either a JSON integer or JSON number, matching the existing PhiOS JSON type contract.

Booleans are never treated as integers.

Non-standard JSON constants such as NaN and Infinity remain rejected by strict JSON parsing.

## Evidence minimization

The observed scalar value is used only in memory while the predicate is evaluated.

Persisted semantic evidence may include:

- expected HTTP status;
- JSON pointer;
- scalar predicate kind;
- explicit contract operand;
- expected JSON type;
- observed JSON type;
- type-match result;
- predicate-match result;
- ordinary bounded HTTP observation metadata and body digest.

It does not persist:

- raw HTTP body;
- observed Boolean value;
- observed integer value;
- observed number value;
- arbitrary pointed scalar contents.

There is deliberately no `observed_value` field.

## Verdict semantics

Wrong HTTP status:

`CONTRADICTED / DISPUTED`

Invalid JSON:

`CONTRADICTED / DISPUTED`

Missing pointer:

`CONTRADICTED / DISPUTED`

Wrong scalar type:

`CONTRADICTED / DISPUTED`

Correct type but predicate false:

`CONTRADICTED / DISPUTED`

Predicate true:

`SUPPORTED / ACCEPTED`

Transport failure, unavailable transient body, or truncated body:

`UNRESOLVED / UNKNOWN`

Missing value-read authority or malformed contract:

`BLOCKED`

## Examples

Boolean readiness flag:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_scalar_predicate \
  --statement "The local endpoint reports ready true." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --json-pointer /ready \
  --json-scalar-predicate boolean_is_true
```

Bounded numeric threshold:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_scalar_predicate \
  --statement "The local queue depth is at most ten." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --json-pointer /queue_depth \
  --json-scalar-predicate integer_lte \
  --json-scalar-operand 10
```

A supported result proves only the named scalar predicate for that one observation.

It does not establish successful inference, model loadability, remote reachability, or general service health.

## Deliberate exclusions

v0.18 does not add:

- arbitrary string equality;
- token or secret matching;
- substring search;
- regex;
- user-defined expressions;
- JSONPath or JMESPath;
- executable code;
- automatic health promotion;
- scalar predicates inside v0.17 multi-clause contracts.

Keeping scalar predicates separate from v0.17 composition preserves the frozen v0.17 contract. A later version can compose value predicates deliberately rather than silently changing old semantics.

## Design rule

```text
Value inspection requires value authority.
Use the value transiently.
Persist the comparison, not the observed value.
Claim only what the predicate establishes.
```
