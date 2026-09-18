# PhiOS Spine v0.23 - Temporal Envelope Mixed Contracts

Spine v0.23 adds a new Reality Gate claim kind:

`local_http_json_temporal_envelope_mixed_contract`

It evaluates the existing mixed JSON contract across a bounded cadenced series while also constraining the total monotonic span from the first provider invocation start to the last.

## Why this exists

v0.22 proves each adjacent provider-start interval is inside an admitted cadence window.

v0.23 adds a second temporal scale:

- local cadence between neighboring observations;
- whole-series span from first start to last start.

A series can satisfy every adjacent cadence interval and still violate the admitted whole-series span.

## Core model

```text
same mixed contract
      ↓
2-5 provider observations
      ↓
each adjacent start in [interval MIN, interval MAX]
      ↓
first-to-last start in [series MIN, series MAX]
      ↓
semantic + cadence + envelope evidence
      ↓
RealityReceipt
```

## Temporal contract

A v0.23 claim requires:

- 2-5 observations;
- 1-8 existing mixed clauses;
- minimum interval from 0.05 through 10.0 seconds;
- maximum interval from 0.05 through 10.0 seconds;
- maximum interval >= minimum interval;
- minimum first-to-last series span from 0.05 through 40.0 seconds;
- maximum first-to-last series span from 0.05 through 40.0 seconds;
- maximum series span >= minimum series span.

The cadence window is inclusive.

The series-span window is also inclusive.

## Pre-I/O feasibility

The requested observation count and cadence imply a possible whole-series range.

For N observations:

```text
cadence implied minimum span
    = (N - 1) * minimum interval

cadence implied maximum span
    = (N - 1) * maximum interval
```

The explicit series-span window must intersect that implied range.

Example:

```text
N = 5
cadence = [1, 2]

implied series span = [4, 8]
```

A requested series span of `[10, 12]` is impossible and is rejected before provider I/O.

## Temporal-envelope authority

v0.23 requires the existing bounded read and cadence authorities plus:

- `reality.local_http.timing.envelope`

The full authority set is:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`
- `reality.local_http.repeat.read`
- `reality.local_http.timing.wait`
- `reality.local_http.timing.cadence`
- `reality.local_http.timing.envelope`

If any mixed clause reads a scalar value, the existing:

- `reality.local_http.semantic.value.read`

is also required.

All required grants are checked before the first provider invocation.

## Future-feasible scheduling

v0.23 does not blindly schedule every observation at the minimum cadence.

Before every provider start after the first, PhiOS calculates:

1. the start window allowed by the previous observation's cadence;
2. the start window that still leaves enough remaining cadence capacity to finish inside the admitted whole-series span;
3. the intersection of those two windows.

The next invocation is scheduled at the earliest point inside that intersection when possible.

For the current sample at index `i`:

```text
remaining_after_current = N - 1 - i

earliest_by_cadence
    = previous_start + interval_min

latest_by_cadence
    = previous_start + interval_max

earliest_by_envelope
    = first_start
      + series_min
      - remaining_after_current * interval_max

latest_by_envelope
    = first_start
      + series_max
      - remaining_after_current * interval_min

admissible earliest
    = max(earliest_by_cadence, earliest_by_envelope)

admissible latest
    = min(latest_by_cadence, latest_by_envelope)
```

This lets PhiOS intentionally preserve future feasibility instead of discovering at the last sample that it knowingly finished too early.

## Provider overrun remains evidence

The scheduler cannot repair elapsed time.

If a provider call runs long enough that the next actual start falls outside the admissible start window, the evidence records that fact.

All requested observations are still attempted within the existing 2-5 bound.

A provider overrun can therefore cause:

- a cadence contradiction;
- a whole-series span contradiction;
- or both.

Semantic success does not erase temporal failure.

## Timing basis and precision

All timing uses the process monotonic clock.

The cadence basis remains:

`provider_invocation_start_monotonic`

The whole-series basis is:

`first_to_last_provider_invocation_start_monotonic`

Persisted measurements include:

- elapsed time since previous start;
- elapsed series span since first start;
- admissible start offsets;
- minimum and maximum observed cadence intervals;
- total first-to-last series span.

Timing measurements used for evidence decisions are rounded to 9 decimal places before comparison and persistence.

Absolute monotonic timestamps are not persisted.

Wall-clock capture timestamps remain provenance only.

## Sample timing evidence

A sample may include:

- `elapsed_since_previous_start_seconds`
- `series_span_so_far_seconds`
- `admissible_start_offset_min_seconds`
- `admissible_start_offset_max_seconds`
- `lower_bound_satisfied`
- `upper_bound_satisfied`
- `cadence_satisfied`
- `start_window_satisfied`

The first observation has no previous interval or derived next-start window.

## Series timing evidence

The aggregate series record includes:

- requested cadence MIN/MAX;
- requested series-span MIN/MAX;
- cadence-implied minimum and maximum series span;
- minimum observed interval;
- maximum observed interval;
- total first-to-last series span;
- cadence satisfied;
- scheduling path satisfied;
- series-span lower-bound result;
- series-span upper-bound result;
- series-span satisfied;
- temporal-envelope satisfied.

## Verdict precedence

The temporal envelope is part of the admitted claim.

```text
cadence violation
    → CONTRADICTED

else whole-series span violation
    → CONTRADICTED

else semantic sample contradiction
    → CONTRADICTED

else unresolved sample
    → UNRESOLVED

else
    → SUPPORTED
```

A valid cadence does not imply a valid series span.

A valid series span does not repair an invalid cadence.

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.repeat.read \
  --allow reality.local_http.timing.wait \
  --allow reality.local_http.timing.cadence \
  --allow reality.local_http.timing.envelope \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_temporal_envelope_mixed_contract \
  --statement "Three bounded observations satisfy the temporal envelope." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --observation-count 3 \
  --minimum-interval-seconds 1 \
  --maximum-interval-seconds 2 \
  --minimum-series-span-seconds 3.5 \
  --maximum-series-span-seconds 4 \
  --json-mixed-clause '{"pointer":"/models","type":"array"}' \
  --json-mixed-clause '{"pointer":"/ready","scalar_predicate":"boolean_is_true"}'
```

## What SUPPORTED means

A supported v0.23 claim establishes:

- every requested observation was attempted;
- every observed adjacent provider-start interval satisfied the admitted cadence;
- the measured first-to-last provider-start span satisfied the admitted series-span window;
- every observation resolved successfully;
- every admitted semantic clause matched every observation.

It does not establish:

- continuous health between observations;
- unobserved behavior inside the gaps;
- uptime percentage;
- SLO compliance;
- future behavior;
- background monitoring;
- remote reachability;
- successful model inference;
- general application health.

## Privacy

v0.23 preserves the scalar privacy boundary.

Observed pointed scalar values remain transient.

No raw HTTP body, raw scalar value, or absolute monotonic timestamp is added to sample or aggregate evidence.

## Frozen prior semantics

v0.22 remains the adjacent cadence-window contract.

v0.21 remains the minimum-only timed contract.

v0.20 remains unspaced repeated observation.

v0.23 introduces new series-span fields and a new claim kind instead of mutating those earlier contracts.

## Deliberate exclusions

v0.23 does not add:

- background workers;
- asynchronous monitoring;
- cron scheduling;
- recurrence after the bounded invocation ends;
- continuous observation;
- uptime or SLO math;
- remote HTTP;
- automatic retries;
- automatic health promotion.

## Design rule

```text
Adjacent cadence is not whole-series duration.
A feasible contract should be proven feasible before I/O.
The scheduler may preserve future feasibility.
The scheduler may not erase elapsed time.
Discrete temporal envelopes are still not continuous monitoring.
```
