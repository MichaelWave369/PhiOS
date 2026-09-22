# PhiShell v0.10 — Observation History + Change Receipts

Status: **candidate implementation**  
Target substrate: **validated v0.9 unified system-state receipts**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.10 adds bounded session-local history over validated unified system-state receipts.

It answers:

```text
What changed between two trusted observations?
```

It does **not** answer:

```text
Why did it change?
How severe is the change?
What should be done?
Who has authority to act?
```

## Input boundary

History admits only validated:

```text
phios.system-state.v1
```

receipts from the v0.9 provider.

An invalid, stale, authority-bearing, or digest-invalid system-state response is not added to history.

## Storage scope

v0.10 history is intentionally:

```text
historyScope = session-memory
persistent   = false
historyLimit = 16
```

The browser keeps:

- at most 16 trusted system-state receipts;
- at most 15 adjacent change receipts.

Closing or reloading the PhiShell session discards this history.

v0.10 performs no filesystem, SQLite, DuckDB, IndexedDB, localStorage, or remote persistence for observation history.

This keeps the first history rung small and reversible.

## Change receipt

Adjacent trusted system-state receipts produce:

```text
phios.system-change.v1
```

A change receipt records:

```text
recordedAt
sequence
fromReceiptDigest
toReceiptDigest
fromComposedAt
toComposedAt
elapsedMs
coherence transition
component availability changes
component digest changes
summary metric deltas
```

Every receipt also carries:

```text
causeAssigned        = false
severityAssigned     = false
readOnly             = true
executionAuthority   = false
effectPerformed      = false
```

## Descriptive-only semantics

The change deriver compares only fields already admitted by the v0.9 system-state contract.

It may report facts such as:

```text
currentUserProcessCount +2
installedPackageCount +1
activeServiceCount -1
devices digest changed
coherence coherent -> degraded
```

It does not convert those facts into claims such as:

```text
a package installation caused this
the system is unhealthy
this change is dangerous
the operator should restart something
```

Cause and severity remain unassigned.

## Component changes

The five fixed components remain:

```text
host
services
processes
packages
devices
```

For each component the change receipt records:

```text
fromAvailability
toAvailability
availabilityChanged
fromDigest
toDigest
digestChanged
```

Digest change means only that the bounded component observation changed.

It does not independently identify which field changed unless that field is also represented in the bounded summary.

## Summary changes

The bounded numeric metrics eligible for explicit delta reporting are:

```text
cpuLogicalCores
memoryTotalBytes
rootStorageTotalBytes
observedServiceCount
activeServiceCount
currentUserProcessCount
installedPackageCount
blockDeviceCount
networkDeviceCount
pciDeviceCount
usbDeviceCount
drmDeviceCount
powerDeviceCount
```

For each changed metric:

```text
metric
from
to
delta
```

is recorded.

No threshold, alarm class, risk score, or severity label is assigned.

## Change digest

Each change receipt receives:

```text
changeDigest = sha256:<hex>
```

computed over every field except `changeDigest` itself.

The digest is an integrity identity only.

It is not:

- a signature;
- authority;
- a causal proof;
- a security verdict.

## Canonical host deriver

The host-side canonical implementation is:

```text
phishell/host/systemChangeDeriver.mjs
```

It is a pure comparison layer over two already validated system-state receipts.

It adds no new Linux observation surface.

The validator is:

```text
phishell/host/systemChangeContract.mjs
```

It recomputes:

- coherence transition;
- component availability-change flags;
- component digest-change flags from the recorded digest transition;
- elapsed time from the two composed timestamps;
- changed component count;
- canonical summary-delta order and values;
- changed summary count;
- change digest.

## Browser session history

The browser implementation is:

```text
phishell/src/shell/systemHistory.ts
```

The System Inspector starts with one validated system-state receipt.

Each explicit:

```text
Capture next
```

request fetches another governed v0.9 receipt.

If it validates, PhiShell:

1. appends it to the session ring;
2. derives a change receipt from the previous trusted receipt;
3. trims the ring to the fixed bound;
4. displays recent descriptive changes.

If it fails validation, it is not admitted.

## Monotonic sequence

Change receipt sequence numbers remain monotonic even when old history entries are trimmed.

Storage truncation therefore does not reset the observation sequence.

## No new transport endpoint

v0.10 intentionally adds no history or change HTTP endpoint.

The browser already receives validated v0.9 receipts through:

```text
GET /api/v1/system-state
```

History and change derivation remain local derived state.

This avoids adding a server-side mutable history store merely to obtain the first bounded history capability.

## Capability plane

v0.10 adds:

```text
history.inspect = available
```

This is a derived read capability only.

It does not add:

```text
history.persist
history.delete
history.export
history.replay
history.execute
```

or any Linux effect capability.

## UI

The unified System Inspector now displays:

```text
current unified receipt
    ↓
session observation history
    ↓
recent change receipts
    ↓
detailed host/service/process/package/device evidence
```

Recent change entries show:

- sequence;
- change digest prefix;
- source and destination receipt digest prefixes;
- elapsed time;
- changed component count;
- changed summary metric count;
- coherence transition;
- explicit numeric deltas;
- cause unassigned;
- severity unassigned;
- authority false.

## CI proof

The PhiShell lane now executes:

```text
contract tests
    ↓
live host observation
    ↓
live service observation
    ↓
live process observation
    ↓
live package observation
    ↓
live hardware observation
    ↓
coherent v0.9 system-state receipt
    ↓
derive bounded v0.10 change receipt
    ↓
TypeScript / Vite build
    ↓
same-origin transport verification
```

The explicit host-side change check is:

```text
npm run probe:changes -- --check
```

Tests also prove:

- at most 16 receipts are retained;
- at most 15 change receipts are retained;
- sequence remains monotonic after trimming;
- cause stays unassigned;
- severity stays unassigned;
- no persistence or Linux effect surface is introduced.

## Security properties

v0.10 adds no:

- process execution;
- service control;
- package management;
- device control;
- network configuration;
- power control;
- arbitrary file reads;
- persistent history database;
- telemetry;
- remote transport;
- automatic remediation.

History is evidence, not authority.

## Next increment

A safe v0.11 candidate is **bounded persistent observation history backed by PhiOS-owned canonical records**, with explicit retention, schema versioning, content hashes, provenance, and read-only analytics.

That rung should integrate with the existing governed-memory / Reality Ledger architecture rather than quietly turning browser history into an accidental source of truth.

Persistent history must remain separate from action authority.
