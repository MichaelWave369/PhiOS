# PhiOS Spine v0.16 - Bounded JSON Structural Predicates

Spine v0.16 adds the Reality Gate claim kind `local_http_json_predicate`.

It verifies small structural facts about one pointed JSON value without comparing or persisting the value itself.

## Epistemic rung

```text
HTTP 200
  ≠
valid JSON
  ≠
pointer exists with expected type
  ≠
pointed structure satisfies a bounded predicate
  ≠
application is healthy
```

v0.16 adds only the structural-predicate rung.

## Authority

The existing semantic boundary remains:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`

## Contract fields

Required:

- `http_url`
- `expected_http_status`
- `json_pointer`
- `json_predicate_kind`

Length/key-count predicates also require `json_predicate_bound`, limited to 0 through 1,000,000.

## Whitelisted predicates

String:

- `string_non_empty`

Array:

- `array_length_eq`
- `array_length_gte`
- `array_length_lte`

Object:

- `object_key_count_eq`
- `object_key_count_gte`
- `object_key_count_lte`

The predicate determines the required JSON type.

## Privacy boundary

For `string_non_empty`, PhiOS records only whether the string is non-empty. It does not persist the string contents or string length.

For array and object predicates, PhiOS may persist the structural count used by the predicate:

- array length
- decoded object key count

It does not persist array elements, object values, or arbitrary pointed scalar contents.

## Verdict semantics

Wrong HTTP status, invalid JSON, missing pointer, wrong JSON type, or a false predicate:

`CONTRADICTED / DISPUTED`

Truncated body, unavailable transient body, or transport failure:

`UNRESOLVED / UNKNOWN`

Missing authority or malformed predicate contract:

`BLOCKED`

Predicate match:

`SUPPORTED / ACCEPTED`

## Evidence

The content-addressed semantic evidence contains only the bounded facts required for audit:

- redacted HTTP observation metadata
- expected status
- JSON pointer
- predicate kind
- predicate bound when applicable
- predicate-derived expected JSON type
- JSON validity
- pointer existence
- observed JSON type
- type match
- structural measurement name/value
- predicate result

The raw HTTP body and pointed raw value are not persisted.

## Examples

Non-empty version string:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  verify-claim \
  --kind local_http_json_predicate \
  --statement "The local version field is non-empty." \
  --http-url http://127.0.0.1:11434/api/version \
  --expected-http-status 200 \
  --json-pointer /version \
  --json-predicate string_non_empty
```

At least one model:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  verify-claim \
  --kind local_http_json_predicate \
  --statement "The local model list contains at least one item." \
  --http-url http://127.0.0.1:11434/api/tags \
  --expected-http-status 200 \
  --json-pointer /models \
  --json-predicate array_length_gte \
  --json-predicate-bound 1
```

Neither claim establishes model loadability, inference readiness, remote reachability, or general service health.

## Deliberate exclusions

v0.16 does not add exact value equality, secret/token matching, substring matching, regex, arbitrary numeric value comparisons, JSONPath/JMESPath, executable expressions, JSON Schema, or automatic health promotion.

```text
Observe only what you were authorized to observe.
Measure only what the contract requires.
Persist less than you inspected.
Claim only what the measurement establishes.
```
