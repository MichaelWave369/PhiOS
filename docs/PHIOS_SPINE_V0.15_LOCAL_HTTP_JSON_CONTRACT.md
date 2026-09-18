# PhiOS Spine v0.15 - Bounded Local HTTP JSON Contract Verification

Spine v0.15 adds the first semantic response verifier above the v0.14 live loopback HTTP adapter.

It answers a deliberately narrow question:

```text
Did this exact loopback HTTP endpoint return the expected status,
with a complete strict-JSON body in which this exact JSON pointer exists
and the pointed value has this expected JSON type?
```

It does not answer:

```text
Is the application healthy?
```

## New claim kind

`local_http_json_contract`

Required fields:

- `http_url`
- `expected_http_status`
- `json_pointer`
- `expected_json_type`

The existing bounded HTTP parameters remain available:

- `http_timeout_seconds`, 0.1 through 10.0 seconds
- `http_max_body_bytes`, 1 through 1,048,576 bytes

## Separate semantic authority

Three grants are required:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`

The third grant is new in v0.15.

Reading and hashing response bytes is not silently treated as permission to interpret response meaning.

## Transport reuse

v0.15 does not add another network stack.

It reuses the v0.14 `StdlibLoopbackHttpStateProvider`.

The provider now carries the bounded response body transiently in memory as part of the live observation object. That transient field is explicitly removed by `LocalHttpObservation.to_dict()` and is therefore not serialized into ordinary HTTP evidence.

The Reality Gate still defaults to `UnavailableLocalHttpStateProvider`; the CLI explicitly supplies the live adapter for the two local HTTP claim kinds.

## Semantic contract

A claim is SUPPORTED only when all of the following are true:

1. the exact observed HTTP status equals `expected_http_status`;
2. the body did not exceed the configured byte budget;
3. the complete observed body decodes as UTF-8;
4. the body parses as strict JSON;
5. the exact JSON pointer exists;
6. the value at that pointer has the expected JSON type.

## Strict JSON

The parser rejects non-standard constants such as:

- `NaN`
- `Infinity`
- `-Infinity`

Those values are accepted by some permissive parsers but are not part of standard JSON.

## JSON pointer

v0.15 implements a bounded RFC-6901-style pointer subset suitable for deterministic lookup.

Examples:

- root: ``
- object field: `/version`
- nested field: `/model/name`
- array index: `/models/0/name`
- escaped slash in a key: `/a~1b`
- escaped tilde in a key: `/~0key`

Bounds:

- maximum pointer length: 512 characters
- maximum depth: 32 tokens
- invalid `~` escape sequences are rejected

Array lookup accepts canonical non-negative indices. A leading zero is rejected except for index `0`.

## Supported JSON types

- `object`
- `array`
- `string`
- `number`
- `integer`
- `boolean`
- `null`

For matching purposes, `integer` also satisfies an expected `number` contract.

A Boolean does not count as an integer even though Python's runtime type hierarchy would otherwise invite that particular bit of nonsense.

## Evidence minimization

v0.15 stores a content-addressed semantic observation record containing:

- the ordinary redacted HTTP observation metadata;
- the semantic contract:
  - expected HTTP status
  - JSON pointer
  - expected JSON type
- semantic outcomes:
  - JSON valid: true / false / not evaluated
  - pointer exists: true / false / not evaluated
  - observed JSON type, when available
  - type match: true / false / not evaluated

The raw response body is not persisted in this record.

The pointed value itself is also not persisted.

## Verdict semantics

Expected status mismatch:

`CONTRADICTED / DISPUTED`

Complete body is invalid JSON:

`CONTRADICTED / DISPUTED`

Pointer absent:

`CONTRADICTED / DISPUTED`

Pointed value has wrong type:

`CONTRADICTED / DISPUTED`

Body exceeds the observation byte budget:

`UNRESOLVED / UNKNOWN`

Transport failure or transient response body unavailable:

`UNRESOLVED / UNKNOWN`

Missing grant or invalid contract:

`BLOCKED`

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  verify-claim \
  --kind local_http_json_contract \
  --statement "Ollama exposes a string version field." \
  --http-url http://127.0.0.1:11434/api/version \
  --expected-http-status 200 \
  --json-pointer /version \
  --expected-json-type string
```

A SUPPORTED result establishes only the bounded response contract observed at that timestamp.

It does not establish model readiness, semantic correctness of the version string, database health, remote reachability, authentication correctness, or general application health.

## Deliberate exclusions

v0.15 does not add:

- arbitrary JSONPath or JMESPath expressions
- regex predicates
- executable predicates
- JSON Schema
- exact secret/value matching
- POST or mutation requests
- HTTPS
- remote hosts
- redirects
- application-specific health promotion

Those should be added only through separate explicit contracts if they become necessary.
