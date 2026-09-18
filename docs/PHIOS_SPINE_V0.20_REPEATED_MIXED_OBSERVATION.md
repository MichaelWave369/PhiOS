# PhiOS Spine v0.20 - Bounded Repeated Mixed Observations

Spine v0.20 adds a new Reality Gate claim kind:

`local_http_json_repeated_mixed_contract`

It evaluates the same v0.19 mixed JSON contract against a bounded series of independent local HTTP observations.

## Why this exists

v0.19 answers:

> Did this mixed contract match one captured response?

v0.20 can answer:

> Did this same mixed contract match each of these explicitly requested observations?

Those are different claims.

Repeated observations provide more temporal evidence, but they do not establish continuous truth between samples.

## Core model

```text
same mixed contract
       ↓
2-5 explicit provider observations
       ↓
sample 0 → digest / timestamp / clause results
sample 1 → digest / timestamp / clause results
sample N → digest / timestamp / clause results
       ↓
bounded series aggregation
       ↓
one series evidence record
```

There is no minimum interval in v0.20.

The provider is called repeatedly as quickly as normal execution permits.

Therefore v0.20 does not claim a duration, uptime percentage, or continuous stability window.

## Observation count

A repeated mixed contract requires exactly 2 through 5 requested observations.

The count is part of the claim contract.

Counts outside that range fail closed before provider I/O.

## Repetition requires separate authority

Repeated reading is treated as a stronger capability than one bounded read.

Every v0.20 claim requires:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`
- `reality.local_http.repeat.read`

If any mixed clause inspects a scalar value, it additionally requires:

- `reality.local_http.semantic.value.read`

All required grants are checked before the first HTTP request.

Thus:

```text
one semantic read
      ≠
permission to repeat reads
```

and:

```text
repeated structural reads
      ≠
permission to inspect scalar values
```

## Clause semantics

v0.20 reuses the v0.19 `JsonMixedContractClause` exactly.

It does not add a fourth clause mode.

The existing modes remain:

- type;
- structural predicate;
- scalar predicate.

This release adds repetition around the mixed contract, not new JSON expression semantics.

## Every requested sample is attempted

After authority and claim validation succeed, the verifier attempts every requested observation.

It does not stop after:

- a contradiction;
- a transport timeout;
- a malformed response;
- a truncated response.

This produces a complete bounded series instead of a first-failure trace.

The observation count remains bounded to at most five.

## Per-sample evidence

Every successful HTTP observation receives its own content-addressed evidence record.

A sample evidence record contains:

- sample index;
- redacted HTTP observation metadata;
- that observation's body digest;
- that observation's capture timestamp;
- the admitted mixed contract;
- JSON validity;
- clause results;
- per-sample verdict and reason.

The raw HTTP body is not persisted in the observation metadata.

For scalar clauses, observed scalar values remain transient.

## Aggregate series evidence

After all requested attempts, PhiOS writes one aggregate content-addressed series record.

It contains:

- the mixed contract;
- requested observation count;
- `minimum_interval_seconds: null`;
- sample outcome summaries;
- supported / contradicted / unresolved counts;
- whether every requested observation matched.

The series record does not invent data for provider failures.

A provider failure has no fabricated observation evidence reference.

## Aggregate verdict precedence

v0.20 uses this deterministic rule:

```text
if any sample is CONTRADICTED:
    overall = CONTRADICTED
elif any sample is UNRESOLVED:
    overall = UNRESOLVED
else:
    overall = SUPPORTED
```

This is deliberate.

If one captured response actually contradicts the contract, a later timeout does not erase that counterexample.

If no observation contradicts the contract but one or more attempts are unresolved, PhiOS cannot establish that every requested observation matched.

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.repeat.read \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_repeated_mixed_contract \
  --statement "Three bounded observations satisfy the local model-service contract." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --observation-count 3 \
  --json-mixed-clause '{"pointer":"/models","type":"array"}' \
  --json-mixed-clause '{"pointer":"/models","predicate":"array_length_gte","bound":1}' \
  --json-mixed-clause '{"pointer":"/ready","scalar_predicate":"boolean_is_true"}' \
  --json-mixed-clause '{"pointer":"/queue_depth","scalar_predicate":"integer_lte","operand":"10"}'
```

If scalar clauses are removed, the value-read grant is not required.

The repeat-read grant remains required because the claim still requests multiple observations.

## What SUPPORTED means

A supported v0.20 claim establishes:

> The admitted contract matched every successfully requested observation in this bounded series, and no requested observation was unresolved.

It does not establish:

- continuous health between observations;
- a minimum amount of elapsed time;
- an uptime percentage;
- future behavior;
- remote reachability;
- model loadability;
- successful inference;
- general application health.

## Repeated observation is not retry

These observations are requested evidence samples.

They are not an automatic recovery mechanism.

A failed sample remains unresolved in the series even if later observations succeed.

PhiOS does not silently convert:

```text
timeout → later success
```

into:

```text
all observations succeeded
```

## Privacy boundary

v0.20 preserves the v0.18/v0.19 scalar rule:

```text
explicit contract operand  → may persist
observed scalar value      → transient only
predicate outcome          → may persist
```

Tests plant recognizable numeric values into repeated responses and verify that those values do not appear in:

- per-sample evidence;
- aggregate series evidence.

## Deliberate exclusions

v0.20 does not add:

- minimum sample interval;
- sleep scheduling;
- long-running monitoring;
- background polling;
- continuous uptime claims;
- percentages or SLO calculations;
- automatic retries;
- remote HTTP;
- arbitrary expressions;
- automatic service-health promotion.

Controlled timing can be introduced later as a distinct authority and contract rung rather than smuggled into repetition.

## Design rule

```text
One read is not permission to poll.
Several observations are not continuous observation.
A counterexample stays a counterexample.
An unresolved sample stays unresolved.
Persist receipts, not raw scalar values.
Claim only what the bounded series establishes.
```
