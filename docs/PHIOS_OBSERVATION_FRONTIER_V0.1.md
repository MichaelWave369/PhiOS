# PhiOS Observation Frontier v0.1

## Status

Research-hardening candidate.

Schemas:

- `phios.observation_frontier.v0.1`
- `phios.observability_boundary_receipt.v0.1`

Primary rule:

```text
NOT OBSERVED
!=
DID NOT OCCUR
```

## Purpose

The Observation Frontier records what PhiOS was actually able to observe when a Reality
Gate verdict was produced.

It exists to stop a bounded observation from silently becoming a global negative claim.

For example:

```text
no listener observed on 127.0.0.1:8123
at observation T
```

does not establish:

```text
no listener existed anywhere
before T
after T
on another address
on another host
or through another transport
```

The frontier preserves that distinction as runtime evidence rather than documentation
etiquette.

## Architecture

```text
RealityClaim
    ↓
bounded provider / evidence source
    ↓
actual observation evidence
    ↓
ObservationCoverage
    ↓
ObservationFrontier
    ↓
ObservabilityBoundaryReceipt
    ↓
RealityReceipt binds hashes/status
```

The existing Reality Gate verdict remains canonical.

The observability layer does not replace:

- Reality permissions;
- Reality verdicts;
- Mandala gates;
- capability permissions;
- action authority;
- execution authority.

## ObservationCoverage

One coverage record is created per claim.

Each record binds:

- claim ID;
- claim kind;
- observation surface;
- bounded target;
- observer/provider ID;
- observer version when available;
- coverage kind;
- status;
- exact evidence references;
- limitations;
- explicit negative-state classification;
- bounded negative-state support.

### Coverage status

The vocabulary is:

```text
COVERED
PARTIAL
UNOBSERVED
```

### COVERED

The declared observer completed the bounded observation contract and produced the
required evidence.

Examples:

- exact local TCP listener filter at one point in time;
- exact interface state with persisted observation evidence;
- one bounded local HTTP response;
- complete bounded HTTP observation series;
- finite readable cited text-evidence set.

### PARTIAL

Some relevant observation happened, but the evidence does not justify the complete
bounded claim.

Examples:

- interface lookup completed but no persisted absence observation exists;
- semantic HTTP body was truncated;
- repeated observation series contains unresolved or missing samples.

### UNOBSERVED

No qualifying observation supports the claim scope.

Examples:

- observation permission was denied;
- provider failed before evidence was produced;
- generic world-state claim has no independent observer;
- unsupported observation surface.

## Coverage kinds

v0.1 uses bounded descriptive kinds such as:

```text
exact_point
bounded_set
bounded_series
none
```

These are evidence descriptors, not confidence scores.

## ObservationFrontier

A complete verification aggregates all claim coverage entries.

The frontier stores:

- all coverage entries;
- covered claim IDs;
- partial claim IDs;
- unobserved claim IDs;
- deterministic canonical SHA-256.

The aggregate status is:

```text
COVERED
PARTIAL
UNOBSERVED
```

A verification with one covered exact TCP claim and one unobserved world-state claim is
therefore `PARTIAL`.

Coverage is never transferred between claims merely because they were verified in the
same request.

## Negative-state claims

v0.1 recognizes explicit structured negative state only when the claim contract contains
a negative boolean expectation.

Current examples:

```text
LOCAL_INTERFACE_STATE
expected_is_up = false

LOCAL_TCP_LISTENER_STATE
expected_listening = false
```

When such a claim is supported by `COVERED` observation evidence, the claim result is
annotated:

```text
negative_state_support_scope =
supported_only_within_observation_frontier
```

This wording is deliberate.

The verifier has established a state within its observation boundary. It has not proved
global or continuous absence.

## Generic negative prose

The Observation Frontier does not infer negative semantics from natural-language wording.

For example:

```text
"No external side effect occurred anywhere."
```

is a generic `WORLD_STATE` claim.

Without an independent world-state verifier it remains:

```text
UNRESOLVED
OUTSIDE_FRONTIER
```

This prevents wording tricks from turning a broad claim into a stronger observation
contract than the runtime actually possesses.

## ObservabilityBoundaryReceipt

Each Reality verification returns an inline zero-authority receipt.

Fields include:

- Reality packet ID;
- task ID;
- observation-frontier SHA-256;
- covered / partial / unobserved claim IDs;
- explicit negative-state claim IDs;
- bounded negative-state claim IDs;
- unbounded negative-state claim IDs;
- limitations;
- operational authority;
- action authority;
- execution authority;
- receipt SHA-256.

Status vocabulary:

```text
BOUNDED
PARTIAL
OUTSIDE_FRONTIER
```

The receipt always fixes:

```text
operational_authority = false
action_authority = false
execution_authority = false
```

It cannot authorize an observation, a tool, an action, or a later execution.

## Why the receipt is inline

v0.1 intentionally does not append a new Mandala ledger row.

The existing lineage remains:

```text
GateReceipt
    ↓
RealityReceipt
```

The `RealityReceipt` now binds:

```text
observation_frontier_sha256
observability_receipt_sha256
observability_status
```

The full observability receipt stays attached to the returned
`RealityVerificationResult`.

This gives the persisted Reality receipt cryptographic lineage to the frontier without
creating a second governance or authority plane.

## Source-content claims

A source-content claim is bounded to the cited readable evidence set.

If expected text is absent from every readable cited source, the existing Reality verdict
may be `CONTRADICTED`.

The frontier means that contradiction only applies to:

```text
the readable cited evidence set
```

It does not establish absence from other files, memory, the network, or the world.

## Local interface claims

An observed interface state with persisted evidence is `COVERED` for the exact
interface at the observation point.

A provider returning no matching interface is currently `PARTIAL`, not `COVERED`,
because the existing provider path does not persist an explicit absence observation
record.

That distinction is intentionally conservative.

## Local TCP claims

A successful TCP-listener provider observation is `COVERED` for:

- one exact port;
- the requested address filter or wildcard;
- one provider snapshot.

A supported `expected_listening=false` claim is therefore bounded negative-state
support, not continuous proof that the port never listened.

## Local HTTP claims

Single HTTP observations are point-in-time coverage.

Semantic HTTP claims become `PARTIAL` when the response body is truncated because the
transport was observed but the complete semantic surface was not.

## Repeated HTTP claims

Repeated, timed, cadenced, temporal-envelope, and numeric-transition verification
produce `bounded_series` coverage.

Even complete series explicitly retain:

```text
series_is_not_continuous_monitoring
```

Discrete observations do not become continuous surveillance by multiplication.

## Ledger analytics

Read-only Ledger snapshot projection may expose:

- `observation_frontier_sha256`;
- `observability_receipt_sha256`;
- `observability_status`.

The full internal frontier does not need to become an analytics authority surface.

## Threat model

v0.1 directly addresses:

- observability-boundary leakage;
- global-absence claims inferred from local observations;
- one claim borrowing another claim's coverage;
- permission denial being mistaken for negative evidence;
- provider failure being mistaken for absence;
- discrete sampling being described as continuous monitoring;
- natural-language negative wording bypassing structured observation contracts.

## Crucibles

The v0.1 test line verifies:

1. supported negative TCP state is bounded to the exact listener frontier;
2. generic world-state absence remains outside the frontier;
3. mixed observed/unobserved claims produce PARTIAL coverage;
4. RealityReceipt binds exact frontier and observability hashes;
5. observability receipts have zero authority;
6. the existing two-row Mandala Reality lineage remains intact;
7. missing observation permission cannot create bounded negative support;
8. provider lookup without persisted absence evidence is PARTIAL;
9. frontier hashing is deterministic for identical claim/evidence inputs.

## Non-goals

v0.1 does not prove:

- that every relevant surface was instrumented;
- that an observer is independent of the system under test;
- that a provider is uncompromised;
- that covert channels do not exist;
- that point-in-time evidence establishes a continuous property;
- that effect declarations from v0.3 are empirically complete;
- that one observer is enough for high-assurance corroboration.

Those are later hardening questions.

The next P1 seam in the current research track is transformation lineage and exactness,
unless a narrower P0/P1 bridge is required by review evidence.
