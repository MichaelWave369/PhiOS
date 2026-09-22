# PhiShell v0.9 — Unified System State Receipt

Status: **candidate implementation**  
Target substrate: **Linux / existing PhiShell observation planes**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.9 composes the five existing read-only observation planes into one versioned machine-state receipt.

It adds no new Linux observation source and no new effect path.

## Existing planes

The composer consumes only the already-governed observations:

```text
host
services
processes
packages
devices
```

Each input is validated by its existing host-side contract before it is admitted to the unified receipt.

The composer therefore does not bypass:

- host privacy minimization;
- service allowlisting;
- current-user process scope;
- package-field minimization;
- device-field minimization.

## Architecture

```text
host observation ───────┐
service observation ────┤
process observation ────┤
package observation ────┼─> validated parallel composition
device observation ─────┘            │
                                     ▼
                          phios.system-state.v1
                                     │
                                     ▼
                            SHA-256 receipt ID
                                     │
                                     ▼
                        same-origin local transport
                                     │
                                     ▼
                           browser revalidation
                                     │
                                     ▼
                         PhiShell System Inspector
```

## No sixth probe

v0.9 is intentionally a composer.

It does not read:

- additional procfs paths;
- additional sysfs paths;
- additional package files;
- additional D-Bus interfaces;
- shell commands;
- arbitrary files.

All machine facts in the receipt are derived from the five existing bounded observation contracts.

## Parallel capture

The five observations are collected in parallel.

The receipt records:

```text
captureWindowStart
captureWindowEnd
captureSkewMs
maxCoherentSkewMs = 5000
```

This makes temporal coherence visible rather than implied.

## Coherence

The receipt has two states:

```text
coherent
degraded
```

A receipt is `coherent` only when:

1. all five components report available; and
2. the difference between the earliest and latest component capture timestamp is at most 5000 ms.

Otherwise the receipt is:

```text
degraded
```

PhiShell does not silently treat missing or temporally scattered observations as a coherent machine state.

## Component receipts

Each component contributes only provenance metadata to the unified receipt:

```text
id
schemaVersion
source
capturedAt
availability
digest
readOnly
executionAuthority
effectPerformed
```

The component IDs and order are frozen:

```text
host
services
processes
packages
devices
```

The expected schema and source identity for each component are also frozen.

## Component digests

Each validated source observation receives:

```text
sha256:<64 lowercase hexadecimal characters>
```

computed over its bounded JSON observation.

The digest is an integrity identity for that captured observation.

It is **not**:

- a digital signature;
- proof of an external trusted party;
- authority;
- permission to act;
- proof that the underlying operating system itself is uncompromised.

## Unified receipt digest

The unified receipt carries:

```text
receiptDigest = sha256:<hex>
```

The hash is computed over every receipt field except `receiptDigest` itself.

The host-side validator recomputes it before transport.

The browser recomputes it again before display.

If the body and digest do not match, PhiShell refuses the receipt.

## Derived summary

The receipt includes only a small summary derived from existing bounded observations:

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

No new raw host data is added by the summary.

## Authority boundary

Every unified receipt carries:

```text
readOnly           = true
executionAuthority = false
effectPerformed    = false
```

Every component receipt must independently carry the same authority boundary.

A single component claiming execution authority causes receipt validation to fail.

The composer contains no Linux mutation API.

Therefore:

```text
coherent state
    !=
authority

valid digest
    !=
authority

all five planes available
    !=
authority
```

## Local transport

The v0.4 loopback host adds one endpoint:

```text
GET /api/v1/system-state
```

The transport envelope is:

```text
transportSchemaVersion = phios.system-state-transport.v1
transport              = loopback-http
transportIdentity      = phishell-local-observer
localOnly              = true
readOnly               = true
executionAuthority     = false
effectPerformed        = false
servedAt               = <timestamp>
snapshotAgeMs          = <freshness>
receipt                 = phios.system-state.v1
```

The server remains hard-bound to:

```text
127.0.0.1
```

No CORS permission is introduced.

Non-GET requests still receive:

```text
405 Method Not Allowed
```

## Browser trust boundary

Before the System Inspector displays a unified receipt, the browser verifies:

- transport schema;
- transport identity;
- local-only assertion;
- transport authority fields;
- freshness;
- exact unified receipt field set;
- component count;
- component order;
- component schema identities;
- component source identities;
- component authority fields;
- component digest shapes;
- summary field set;
- temporal capture window;
- temporal skew;
- available-component count;
- derived coherence status;
- unified SHA-256 receipt digest.

Failure returns no trusted unified receipt.

Unlike earlier per-plane fallback views, v0.9 does not synthesize a fake unified receipt.

## System Inspector hierarchy

The system window now renders:

```text
Unified System State Receipt
    ↓
Host observation
    ↓
Service observation
    ↓
Process observation
    ↓
Package observation
    ↓
Hardware observation
    ↓
Capability boundary
```

The unified receipt shows:

- coherence;
- number of available planes;
- receipt hash prefix;
- capture skew;
- composition duration;
- each component source and hash prefix;
- bounded machine summary.

## CI proof

The PhiShell lane now executes:

```text
npm install
    ↓
browser and native contract tests
    ↓
live host probe
    ↓
live systemd service probe
    ↓
live current-user process probe
    ↓
live package inventory
    ↓
live sysfs device inventory
    ↓
compose unified receipt
    ↓
require coherence
    ↓
TypeScript / Vite build
    ↓
launch loopback host
    ↓
GET /api/v1/system-state
    ↓
verify receipt schema / digest shape / authority=false
    ↓
POST /api/v1/system-state
    ↓
405 Method Not Allowed
```

The explicit CI command is:

```text
npm run probe:state -- --require-coherent
```

If one source plane is unavailable or the capture skew exceeds 5000 ms, this CI gate fails.

## Security properties

v0.9 adds no:

- privileged broker;
- command execution;
- arbitrary file reads;
- new D-Bus methods;
- new procfs fields;
- new sysfs fields;
- process control;
- package control;
- service control;
- device control;
- network configuration;
- power control.

The unified system-state path is a derived read model only.

## Next increment

A safe v0.10 candidate is **observation history and change receipts**.

Rather than adding new visibility, PhiShell can begin comparing two validated unified receipts and describing bounded change:

```text
service active state changed
process count changed
package count changed
device count changed
resource totals changed
component became unavailable
coherence degraded or recovered
```

That history should record change without automatically assigning cause, severity, or authority.

The v0.9 unified receipt should remain permanently read-only.
