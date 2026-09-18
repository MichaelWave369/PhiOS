# PhiOS Spine v0.21 - Timed Mixed Observations

Spine v0.21 adds a new Reality Gate claim kind:

`local_http_json_timed_mixed_contract`

It evaluates the same bounded mixed JSON contract across 2-5 observations while enforcing an explicit minimum interval between provider invocation starts.

## Why this exists

v0.20 adds repeated observations but intentionally enforces no minimum interval.

v0.21 adds one precise temporal claim:

> each provider invocation after the first began at least N seconds after the previous invocation began.

That is narrower than continuous monitoring and stronger than unspaced repetition.

## Core model

```text
same mixed contract
       ↓
2-5 observations
       ↓
monotonic start ── at least N seconds ── next monotonic start
       ↓
per-sample digest / timestamp / clause results
       ↓
timing summary + bounded series evidence
```

## Interval contract

A timed mixed claim requires:

- 2-5 observations;
- 1-8 mixed clauses;
- `minimum_interval_seconds` from 0.05 through 10.0 seconds.

The upper bound keeps one synchronous verification invocation bounded.

The interval is a minimum, not a fixed cadence.

If an observation itself takes longer than the requested interval, PhiOS starts the next observation without adding unnecessary delay.

## Timing basis

Spacing is measured with a monotonic clock.

The timing basis is persisted as:

`provider_invocation_start_monotonic`

PhiOS does not use wall-clock capture timestamps to establish the interval.

Wall-clock timestamps remain useful provenance, but wall clocks can jump, drift, or be adjusted.

The persisted temporal measurement is:

`elapsed_since_previous_start_seconds`

The first observation has no previous start and therefore records null for this field.

## Timing authority

Timed waiting is an explicit authority boundary.

Every v0.21 claim requires:

- `reality.verify`
- `reality.local_http.read`
- `reality.local_http.semantic.read`
- `reality.local_http.repeat.read`
- `reality.local_http.timing.wait`

If any mixed clause inspects a scalar value, it additionally requires:

- `reality.local_http.semantic.value.read`

All permissions are checked before the first provider invocation.

Thus:

```text
permission to repeat reads
       ≠
permission to intentionally occupy time between reads
```

## Scheduling rule

For every observation after the first:

1. calculate the deadline as previous invocation start + minimum interval;
2. read the monotonic clock;
3. if the deadline has not arrived, sleep only for the remaining duration;
4. re-check until the deadline is reached;
5. record the next invocation start;
6. call the provider.

This makes the contract minimum-spacing rather than sleep-after-response.

## Sample semantics

Each provider attempt still receives the same mixed-contract evaluation semantics as v0.20.

Every requested observation is attempted after authority and validation succeed, even if an earlier sample:

- contradicts the contract;
- times out;
- returns malformed JSON;
- returns a truncated response.

A provider failure receives no fabricated observation evidence reference.

## Evidence

Every successful HTTP observation receives one content-addressed sample evidence record.

In addition to the v0.20 fields, timed evidence includes:

- requested minimum interval;
- measured interval since the previous provider start;
- whether that interval satisfied the timing contract;
- timing basis.

The series evidence includes:

- requested minimum interval;
- minimum observed interval;
- number of measured intervals;
- aggregate timing-satisfied result;
- all sample results and semantic counts.

Absolute monotonic clock values are not persisted because their origin is process-local and has no useful cross-process meaning.

## Aggregate verdict

A measured interval shorter than the admitted minimum is a contradiction of the timed contract.

Otherwise semantic sample precedence remains:

```text
timing violation
    → CONTRADICTED

else any semantic CONTRADICTED sample
    → CONTRADICTED

else any UNRESOLVED sample
    → UNRESOLVED

else
    → SUPPORTED
```

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  --allow reality.local_http.repeat.read \
  --allow reality.local_http.timing.wait \
  --allow reality.local_http.semantic.value.read \
  verify-claim \
  --kind local_http_json_timed_mixed_contract \
  --statement "Three observations at least one second apart satisfy the local contract." \
  --http-url http://127.0.0.1:11434/api/state \
  --expected-http-status 200 \
  --observation-count 3 \
  --minimum-interval-seconds 1 \
  --json-mixed-clause '{"pointer":"/models","type":"array"}' \
  --json-mixed-clause '{"pointer":"/ready","scalar_predicate":"boolean_is_true"}' \
  --json-mixed-clause '{"pointer":"/queue_depth","scalar_predicate":"integer_lte","operand":"10"}'
```

## What SUPPORTED means

A supported v0.21 claim establishes:

- every requested observation was attempted;
- each measured provider-start interval met the admitted minimum;
- every observation resolved successfully;
- the mixed contract matched every observation.

It does not establish:

- continuous service health between observations;
- a fixed sampling cadence;
- an uptime percentage;
- an SLO;
- future behavior;
- remote reachability;
- successful model inference;
- general application health.

## Privacy

v0.21 preserves the scalar privacy boundary.

Observed Boolean and numeric values remain transient.

Per-sample and series evidence may persist predicate outcomes, explicit contract operands, types, digests, timestamps, and timing intervals.

They do not persist raw pointed scalar values or the raw HTTP body.

## Frozen prior semantics

v0.20 remains the unspaced repeated-observation contract.

v0.21 introduces a new claim kind and a new timing field instead of silently adding sleep semantics to v0.20.

v0.19 mixed clause semantics remain unchanged.

## Deliberate exclusions

v0.21 does not add:

- background monitoring;
- asynchronous jobs;
- long-running watchers;
- wall-clock scheduling;
- cron semantics;
- fixed-period guarantees;
- uptime percentages;
- SLO calculations;
- automatic retries;
- remote HTTP;
- automatic health promotion.

## Design rule

```text
Repeat authority is not timing authority.
Wall time is not monotonic time.
Minimum spacing is not continuous monitoring.
Several spaced observations are still discrete observations.
Persist measured intervals, not meaningless absolute monotonic timestamps.
Claim only what the timed series establishes.
```
