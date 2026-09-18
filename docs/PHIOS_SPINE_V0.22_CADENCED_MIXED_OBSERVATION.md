# PhiOS Spine v0.22 - Cadenced Mixed Observations

Spine v0.22 adds a new Reality Gate claim kind:

`local_http_json_cadenced_mixed_contract`

It evaluates the same bounded mixed JSON contract across 2-5 observations while requiring every provider invocation after the first to begin inside an explicit monotonic timing window.

## Why this exists

v0.21 proves a minimum interval:

> each provider start occurred at least N seconds after the previous provider start.

v0.22 proves a bounded cadence window:

> each provider start occurred no earlier than MIN and no later than MAX seconds after the previous provider start.

This is stronger than minimum spacing and still narrower than continuous monitoring.

## Core model

```text
previous provider start
        ↓
   wait until MIN
        ↓
next provider start must occur
inside [MIN, MAX]
        ↓
semantic mixed-contract evaluation
        ↓
cadence + semantic series evidence
```

## Cadence window

A cadenced mixed claim requires:

- 2-5 observations;
- 1-8 mixed clauses;
- `minimum_interval_seconds` from 0.05 through 10.0;
- `maximum_interval_seconds` from 0.05 through 10.0;
- maximum interval greater than or equal to minimum interval.

The window is inclusive.

```text
MIN <= elapsed_since_previous_start <= MAX
```

## Timing basis

Cadence uses the same timing basis introduced in v0.21:

`provider_invocation_start_monotonic`

The persisted timing measurement is:

`elapsed_since_previous_start_seconds`

Absolute monotonic timestamps are not persisted.

Wall-clock capture timestamps remain provenance only and do not establish cadence.

## Cadence authority

Cadence control is a stronger authority than minimum waiting.

Every v0.22 claim requires:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`
- `reality.local_http.repeat.read`
- `reality.local_http.timing.wait`
- `reality.local_http.timing.cadence`

If any mixed clause reads a scalar value, the claim additionally requires:

- `reality.local_http.semantic.value.read`

All grants are checked before the first provider invocation.

Thus:

```text
repeat authority
    ≠
minimum-wait authority
    ≠
bounded-cadence authority
```

## Scheduling behavior

PhiOS schedules the earliest permitted next start.

For each observation after the first:

1. compute earliest start = previous start + MIN;
2. sleep only until that earliest start when necessary;
3. record the actual next monotonic start;
4. compare the actual interval against both MIN and MAX;
5. invoke the provider;
6. retain the measured interval and bound outcomes.

PhiOS does not sleep until MAX.

The maximum is a deadline boundary, not a target.

## Provider overrun

A provider call can itself cause the next start to miss MAX.

Example:

```text
window = [2, 3] seconds

sample 0 starts at 0
sample 1 starts at 2
sample 1 provider takes 4 seconds
sample 2 cannot start before 6

observed interval = 4
4 > MAX 3
→ cadence contradiction
```

PhiOS does not erase this contradiction because the semantic response happened to be valid.

## Per-sample timing fields

For observations after the first, sample evidence can include:

- `elapsed_since_previous_start_seconds`;
- `lower_bound_satisfied`;
- `upper_bound_satisfied`;
- `cadence_satisfied`;
- `interval_basis`.

The first sample records null for interval-derived fields because no prior invocation exists.

## Aggregate timing fields

Series evidence includes:

- requested minimum interval;
- requested maximum interval;
- minimum observed interval;
- maximum observed interval;
- number of observed intervals;
- aggregate cadence-satisfied result.

## Verdict precedence

Cadence is part of the admitted claim.

Therefore:

```text
any cadence-window violation
    → CONTRADICTED

else any semantic CONTRADICTED sample
    → CONTRADICTED

else any UNRESOLVED sample
    → UNRESOLVED

else
    → SUPPORTED
```

This means all semantic samples may be supported while the overall claim is contradicted because the admitted cadence was missed.

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.repeat.read \
  --allow reality.local_http.timing.wait \
  --allow reality.local_http.timing.cadence \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_cadenced_mixed_contract \
  --statement "Three observations start between one and two seconds apart and satisfy the local contract." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --observation-count 3 \
  --minimum-interval-seconds 1 \
  --maximum-interval-seconds 2 \
  --json-mixed-clause '{"pointer":"/models","type":"array"}' \
  --json-mixed-clause '{"pointer":"/ready","scalar_predicate":"boolean_is_true"}'
```

## What SUPPORTED means

A supported v0.22 claim establishes:

- every requested observation was attempted;
- every measured provider-start interval fell inside the admitted inclusive cadence window;
- every observation resolved successfully;
- every mixed semantic clause matched every observation.

It does not establish:

- continuous health between observations;
- a long-running scheduler;
- future cadence;
- uptime percentage;
- SLO compliance;
- remote reachability;
- model inference success;
- general application health.

## Privacy

v0.22 preserves all existing semantic privacy boundaries.

Observed scalar values remain transient.

Cadence evidence persists intervals and Boolean bound outcomes, not raw pointed scalar values or raw HTTP bodies.

## Frozen prior semantics

v0.21 remains the minimum-only timed contract.

v0.20 remains unspaced repeated observation.

v0.22 introduces a new claim kind and a new maximum interval field rather than mutating either earlier contract.

## Deliberate exclusions

v0.22 does not add:

- background workers;
- async scheduling;
- long-running monitoring;
- wall-clock cron schedules;
- future recurrence;
- uptime percentages;
- SLO calculations;
- remote HTTP;
- automatic retries;
- health promotion.

## Design rule

```text
Minimum spacing is not cadence.
Cadence authority is not implied by wait authority.
Semantic success does not repair timing failure.
A missed upper bound remains evidence.
Discrete cadence is still not continuous monitoring.
```
