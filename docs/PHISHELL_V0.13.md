# PhiShell v0.13 — Governed Canonical History Comparison

Status: **candidate implementation**  
Target substrate: **PhiShell v0.12 governed persistent history projection**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.13 lets the operator select two read-admissible canonical machine-state records and derive a temporary bounded comparison.

The comparison is not a persisted memory record, not a historical event claim, not a causal claim, and not an authority grant.

## Core rule

```text
comparison != change event
comparison != cause
comparison != severity
comparison != persistence
comparison != authority
```

## Authority split

Canonical history projection still requires:

```text
history.read
memory.read
```

Canonical state comparison additionally requires:

```text
history.compare
```

Canonical persistence remains separate:

```text
history.persist
memory.write
```

Therefore:

```text
history.read    != history.compare
history.compare != history.persist
memory.read     != memory.write
```

The history sidecar can continue serving ordinary persistent-history projection without a `history.compare` grant. Comparison requests fail closed with HTTP 403 when that separate grant is absent.

## Input boundary

Comparison accepts exactly two distinct canonical record IDs:

```text
phishell.system-state.<sha256>
```

It does not accept:

- canonical change-record IDs;
- arbitrary memory record IDs;
- raw state JSON supplied by the browser;
- filesystem paths;
- database queries;
- semantic-search queries.

Both selected records are re-read independently through:

```text
MemoryOperatorRuntime.get()
    ↓
GovernedMemoryService.get()
```

Each side must therefore pass the current:

- `memory.read` authority check;
- deny-default policy;
- scope/classification policy;
- published-head check;
- tombstone check;
- retention/expiry check;
- evidence-horizon/currentness checks when configured.

Each input receives a fresh `ReadAdmissibilityReceipt`.

## Canonical state integrity

A selected canonical state must retain:

```text
source_id      = phishell.system-state
epistemic_kind = source
record_id      = phishell.system-state.<receipt digest>
provenance     includes the receipt digest
```

The canonical MemoryRecord content and record hashes are revalidated before comparison.

The comparison input also requires the bounded component identities used by the live system-state composer:

| Component | Schema | Source |
| --- | --- | --- |
| host | `phios.host-observation.v1` | `linux-readonly-node-probe` |
| services | `phios.service-observation.v1` | `systemd-dbus-list-units` |
| processes | `phios.process-observation.v1` | `procfs-current-user` |
| packages | `phios.package-observation.v1` | `dpkg-status-file` |
| devices | `phios.device-observation.v1` | `linux-sysfs-bounded` |

Every component must remain read-only and carry zero execution authority and zero performed effect.

## Comparison receipt

The receipt schema is:

```text
phios.system-history-comparison.v0.13
```

It contains:

```text
generatedAt
comparisonScope = canonical-state-pair
persistent = false

fromRecordId
toRecordId
fromRecordSha256
toRecordSha256

fromReadAdmissibilityReceiptSha256
toReadAdmissibilityReceiptSha256

fromReceiptDigest
toReceiptDigest
fromComposedAt
toComposedAt

timeDeltaMs
chronologicalOrder

coherence
changedComponentCount
componentChanges
changedSummaryMetricCount
summaryChanges

consecutiveClaimed = false
causeAssigned = false
severityAssigned = false

readOnly = true
operationalAuthority = false
actionAuthority = false
executionAuthority = false
effectPerformed = false

comparisonDigest
```

## No consecutive-event claim

A historical comparison is directional because the operator selects A and B.

The receipt reports:

```text
timeDeltaMs
chronologicalOrder = forward | reverse | same-time
```

But it always states:

```text
consecutiveClaimed = false
```

This prevents a comparison across two snapshots from silently becoming a claim that no unobserved intermediate states existed.

## Bounded differences

The comparison reuses the descriptive vocabulary already used by session change receipts.

### Components

Exactly five component rows are compared:

```text
host
services
processes
packages
devices
```

Each row reports only:

```text
fromAvailability
toAvailability
availabilityChanged
fromDigest
toDigest
digestChanged
```

### Summary metrics

Only the frozen system-state summary metrics may appear:

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

Summary metrics are normalized as non-negative integers for deterministic Python/JavaScript canonical digest parity.

No causal, severity, anomaly, or remediation fields are derived.

## Deterministic digest

The comparison body is serialized with recursively sorted object keys and compact JSON before SHA-256 hashing.

Python, Node, and the browser independently verify the comparison digest.

This gives three trust boundaries:

```text
Python comparison derivation
        ↓
Node comparison validation + digest replay
        ↓
browser comparison validation + digest replay
```

A body altered after digest creation is rejected.

## Python sidecar

The existing governed history sidecar adds:

```text
GET /api/v1/system-history-compare?from=<state-id>&to=<state-id>
```

It remains hard-bound to:

```text
127.0.0.1
```

No CORS permission is emitted.

Mutation methods remain rejected with:

```text
405 Method Not Allowed
Allow: GET
```

## Node same-origin boundary

PhiShell's Node host exposes one fixed route:

```text
GET /api/v1/persistent-history-compare?from=<state-id>&to=<state-id>
```

The route requires exactly two query parameters.

Both values must match:

```text
^phishell\.system-state\.[0-9a-f]{64}$
```

They must be distinct.

Node forwards only to the fixed loopback history sidecar. It is not a generic proxy.

Invalid selection returns HTTP 400.

Unavailable, denied, or invalid sidecar comparison returns a safe unavailable result rather than fabricated comparison data.

## Browser trust boundary

The browser independently validates:

- exact transport fields;
- exact comparison fields;
- exact component-row fields;
- exact summary-change fields;
- canonical state-record IDs;
- fresh read-admissibility receipt hashes;
- record hashes;
- receipt hashes;
- time-delta derivation;
- chronological-order derivation;
- coherence derivation;
- component change counts;
- summary change counts and ordering;
- zero authority;
- non-persistence;
- `consecutiveClaimed=false`;
- `causeAssigned=false`;
- `severityAssigned=false`;
- the deterministic comparison digest.

## System Inspector

Canonical state rows now include:

```text
Set A
Set B
```

The operator selects two state records and chooses:

```text
Compare selected
```

The result displays:

- chronological direction;
- signed time delta;
- changed component count;
- changed summary metric count;
- coherence A → B;
- changed summary metrics;
- comparison digest prefix.

The result is visibly marked:

```text
TEMPORARY DERIVATION
persistent = false
consecutive claimed = false
cause = unassigned
severity = unassigned
authority = false
```

Changing either selection clears the previous comparison receipt.

## Capability plane

PhiShell now advertises:

```text
history.inspect            = available
history.canonical.inspect  = available
history.compare            = available
history.persist            = unavailable
```

The visual capability plane does not itself grant the operator-side `history.compare` authority.

## Tests

v0.13 proves:

- comparison requires `history.read`;
- comparison separately requires `memory.read`;
- comparison separately requires `history.compare`;
- comparison accepts only canonical state records;
- identical state selections are rejected;
- reverse-direction comparisons remain descriptive;
- comparison reads create no new Mandala ledger writes;
- comparison persistence remains false;
- consecutive-event claims remain false;
- cause and severity remain unassigned;
- all authority fields remain false;
- Python sidecar comparison is loopback-only;
- comparison route emits no CORS permission;
- mutation methods remain 405;
- history projection still works without comparison authority;
- Node rejects authority-bearing comparisons;
- Node rejects digest tampering;
- browser rejects authority-bearing comparisons;
- browser independently rejects digest tampering;
- same-origin comparison transport is bounded to two canonical state IDs.

## What v0.13 does not add

v0.13 adds no:

- canonical comparison persistence;
- comparison history database;
- causal inference;
- severity classification;
- anomaly scoring;
- remediation;
- action recommendation;
- arbitrary record comparison;
- arbitrary proxying;
- shell execution;
- Linux privilege.

## Next safe rung

A v0.14 candidate could add **operator-authored annotations attached to a comparison as a separate, explicitly governed layer**.

Any such rung should preserve:

```text
observed difference != operator interpretation
operator interpretation != canonical fact
annotation != execution authority
```
