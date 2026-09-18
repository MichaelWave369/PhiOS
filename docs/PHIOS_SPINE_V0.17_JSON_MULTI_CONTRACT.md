# PhiOS Spine v0.17 - Same-Snapshot Multi-Clause JSON Contracts

Spine v0.17 adds the Reality Gate claim kind:

`local_http_json_multi_contract`

The purpose is to prove several bounded semantic facts from one and only one HTTP observation.

## Why this exists

Before v0.17, callers could issue several independent semantic claims:

```text
request A -> /models is an array
request B -> /models length >= 1
request C -> /models/0/name is a string
request D -> /models/0/name is non-empty
```

Those observations may occur at different times.

v0.17 provides:

```text
one request
    ↓
one captured body
    ↓
one strict JSON parse
    ↓
1-8 bounded clauses
    ↓
one same-snapshot semantic evidence record
```

## Authority

The existing semantic grants remain required:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`

No stronger authority is introduced.

## Contract bounds

A multi-contract contains between 1 and 8 clauses.

Each clause has one JSON pointer and exactly one mode.

### Type clause

Example:

```json
{"pointer":"/models","type":"array"}
```

The type must be one of the v0.15 JSON types.

### Predicate clause

Example:

```json
{"pointer":"/models","predicate":"array_length_gte","bound":1}
```

Predicates are restricted to the v0.16 structural whitelist.

No clause may combine a type check and a predicate.

The old single-clause fields are rejected on a multi-contract to keep the contract unambiguous.

## Observation semantics

The provider is called exactly once per multi-contract claim.

If the transport observation succeeds and the body is complete, the body is parsed exactly once as strict JSON.

Every clause is then evaluated against that same in-memory document.

Clause evaluation does not stop at the first contradiction. All clauses are evaluated so the receipt can describe the full same-snapshot state.

## Clause results

Each clause result may record:

- clause index
- pointer
- mode
- expected JSON type
- predicate kind and bound when applicable
- pointer existence
- observed JSON type
- type match
- structural measurement name/value
- predicate match
- overall clause match
- bounded clause reason

Raw pointed values are never placed into the clause result.

## Aggregate verdict

The claim is SUPPORTED only when every clause matches.

If one or more clauses contradict the captured document:

`CONTRADICTED / DISPUTED`

If the status is wrong or the complete body is invalid JSON:

`CONTRADICTED / DISPUTED`

If the transport fails, the body is unavailable, or the body is truncated:

`UNRESOLVED / UNKNOWN`

If authority or the claim contract is invalid:

`BLOCKED`

## Evidence minimization

The evidence record stores:

- redacted HTTP observation metadata
- expected status
- clause definitions
- JSON validity
- clause results
- evaluated clause count
- aggregate match result

It does not store:

- raw HTTP body
- pointed string contents
- array elements
- object values
- arbitrary scalar contents

## CLI

Use `--json-clause` repeatedly.

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  verify-claim \
  --kind local_http_json_multi_contract \
  --statement "The local model endpoint satisfies the bounded model-list contract." \
  --http-url http://127.0.0.1:11434/api/tags \
  --expected-http-status 200 \
  --json-clause '{"pointer":"/models","type":"array"}' \
  --json-clause '{"pointer":"/models","predicate":"array_length_gte","bound":1}' \
  --json-clause '{"pointer":"/models/0/name","type":"string"}' \
  --json-clause '{"pointer":"/models/0/name","predicate":"string_non_empty"}'
```

A supported result proves only that all four clauses were true of one observed response at the recorded time.

It does not establish model loadability, successful inference, remote reachability, or general service health.

## Design rule

```text
One observation.
One timestamp.
One digest.
Many bounded questions.
No broader conclusion than the clauses establish.
```
