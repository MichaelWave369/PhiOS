# PhiShell v0.12 — Governed Persistent History Projection

Status: **candidate implementation**  
Target substrate: **PhiShell v0.11 canonical history + governed memory read policy**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.12 adds a bounded read-only projection of canonical persistent machine history back into the System Inspector.

It does not give the browser direct database access.

## Architecture

```text
canonical.sqlite3
       │
       ▼
MemoryStore bounded ID enumeration
       │
       ▼
GovernedMemoryService.get()
       │
       ├─ memory.read authority
       ├─ deny-default policy
       ├─ published/current check
       ├─ tombstone check
       ├─ retention/expiry check
       └─ ReadAdmissibilityReceipt
       │
       ▼
SystemHistoryProjectionService
       │
       ├─ history.read authority
       ├─ max 16 records
       ├─ PhiShell source IDs only
       ├─ source/derived contract checks
       └─ authority = false
       │
       ▼
127.0.0.1:3970 Python read sidecar
       │
       ▼
fixed Node loopback proxy
       │
       ▼
GET /api/v1/persistent-history
       │
       ▼
browser revalidation
       │
       ▼
System Inspector
```

## Separate read and write authority

v0.11 persistence requires:

```text
history.persist
memory.write
```

v0.12 canonical history reads require:

```text
history.read
memory.read
```

These capabilities do not imply one another.

```text
history.read    != history.persist
memory.read     != memory.write
persistent data != execution authority
```

The browser still exposes no persistent write path.

## Canonical enumeration boundary

A new MemoryStore helper can enumerate current record IDs only when given explicit:

- source IDs;
- allowed scopes;
- allowed classifications;
- bounded result count.

For v0.12 the source IDs are frozen to:

```text
phishell.system-state
phishell.system-change
```

The maximum projection is:

```text
16 records
```

The enumeration query requires:

- published head;
- no tombstone;
- current revision;
- non-expired retention state;
- allowed scope;
- allowed classification.

The browser never sees or controls the SQLite query.

## Re-read through governed memory

Enumeration alone is not sufficient.

Every enumerated record ID is re-read through:

```text
MemoryOperatorRuntime.get()
    ↓
GovernedMemoryService.get()
```

This produces a fresh:

```text
ReadAdmissibilityReceipt
```

for each record displayed.

If a candidate cannot be read under the current policy/currentness boundary, it is omitted and the projection becomes:

```text
status = degraded
```

## Projection contract

The projection schema is:

```text
phios.system-history-projection.v0.12
```

It includes:

```text
generatedAt
status
historyScope = canonical-memory
persistent = true
limit <= 16
count
omittedRecordCount
records
readAdmissibilityReceiptSha256s
readOnly = true
causeAssigned = false
severityAssigned = false
operationalAuthority = false
actionAuthority = false
executionAuthority = false
effectPerformed = false
```

## Projected record metadata

Each returned record includes only governed canonical metadata plus its persisted receipt payload:

```text
kind
recordId
revision
recordSha256
contentSha256
createdAt
scopeId
classification
retentionPolicyId
epistemicKind
exactnessClass
derivedFrom
transformationLineageSha256s
readAdmissibilityReceiptSha256
payload
```

State records must remain:

```text
kind = state
epistemicKind = source
exactnessClass = null
derivedFrom = []
```

Change records must remain:

```text
kind = change
epistemicKind = derived
exactnessClass = REVERSIBLE
derivedFrom = [state A, state B]
one transformation lineage hash
causeAssigned = false
severityAssigned = false
```

## Receipt digest repair

During v0.12 implementation, the v0.11 import boundary was tightened.

v0.11 already checked:

- receipt digest format;
- state/change source identity;
- zero-authority fields;
- transition references.

v0.12 additionally recomputes the supplied:

```text
receiptDigest
changeDigest
```

from the JSON receipt body before canonical persistence.

A hand-edited receipt with a stale digest is now rejected before it can enter canonical memory.

After persistence, governed memory stores strict canonical JSON, which may reorder object keys relative to the original JavaScript receipt serialization. Read-back therefore does not incorrectly recompute the original receipt hash from reordered JSON. Instead it verifies:

- canonical MemoryRecord content hash;
- canonical MemoryRecord record hash;
- receipt hash shape;
- canonical record ID derived from the receipt hash;
- matching provenance references;
- matching state-to-change derived_from references.

This preserves both original receipt identity and canonical storage integrity.

This repair does not grant new capability.

## Python read sidecar

The operator starts the read surface explicitly:

```bash
phi-memory \
  --config ~/.phios/memory/config.json \
  --state-root ~/.phios/memory \
  --allow history.read \
  --allow memory.read \
  serve-system-history \
  --port 3970
```

The server is hard-bound to:

```text
127.0.0.1
```

It serves only:

```text
GET /api/v1/health
GET /api/v1/system-history?limit=1..16
```

Non-GET methods return:

```text
405 Method Not Allowed
Allow: GET
```

It emits no CORS permission.

The read sidecar fails to start without either required read grant.

## Node same-origin proxy

PhiShell's existing local host does not open the canonical database and does not spawn `phi-memory`.

It performs one fixed server-to-server request to:

```text
http://127.0.0.1:3970/api/v1/system-history?limit=16
```

The port may be changed with:

```text
PHIOS_HISTORY_PORT
```

The host cannot be changed from IPv4 loopback.

The Node layer validates:

- transport schema and identity;
- local-only status;
- zero authority;
- maximum record count;
- projection status;
- exact record metadata fields;
- state/source semantics;
- change/derived semantics;
- reversible lineage requirement;
- read-admissibility receipt hashes.

Only after validation is the projection exposed at the same-origin browser route:

```text
GET /api/v1/persistent-history
```

If the sidecar is unavailable or invalid, PhiShell receives:

```text
503 persistent_history_unavailable
```

No fixture canonical history is fabricated.

## Browser trust boundary

The browser performs a second validation pass.

It verifies:

- transport identity;
- projection schema;
- record bound;
- zero-authority fields;
- state/change epistemic type;
- canonical record ID prefix;
- lineage shape;
- read-admissibility receipt membership.

Failure returns no trusted canonical projection.

## System Inspector

The System Inspector now shows two visibly separate time domains:

```text
SESSION HISTORY
  volatile
  up to 16 live receipts

CANONICAL HISTORY
  persisted through governed memory
  current/read-admissible records only
  up to 16 projected records
```

Canonical rows display:

- source/change kind;
- created time;
- canonical record ID;
- source vs derived status;
- exactness;
- canonical revision;
- read-admissibility hash prefix;
- canonical record/content hash prefixes;
- transformation lineage hash for changes.

The raw persistent write path remains absent from the browser.

## Capability plane

PhiShell now advertises:

```text
history.inspect           = available
history.canonical.inspect = available
history.persist           = unavailable
```

The first two describe read capability.

They do not grant the operator-side authorities:

```text
history.read
memory.read
```

Those must still be explicitly supplied to the read sidecar.

## Tests

v0.12 proves:

- canonical history projection is bounded to 16;
- projection requires `history.read`;
- projection independently requires `memory.read`;
- projected records carry fresh read-admissibility hashes;
- projection reads do not create new Mandala ledger writes;
- state records remain canonical source evidence;
- change records remain derived REVERSIBLE evidence;
- loopback server binds only to `127.0.0.1`;
- sidecar emits no CORS permission;
- POST is rejected with 405;
- Node rejects authority-bearing projections;
- Node rejects read-receipt mismatches;
- browser rejects the same malformed projections;
- same-origin host safely reports unavailable when the sidecar is absent;
- stale/tampered receipt digests are rejected before canonical persistence.

## What v0.12 does not add

v0.12 adds no:

- direct browser SQLite access;
- browser filesystem access;
- generic HTTP proxy;
- command execution;
- automatic sidecar startup;
- remote history server;
- persistent mutation endpoint;
- semantic search requirement;
- history deletion;
- remediation;
- Linux privilege.

## Next increment

A safe v0.13 candidate is **bounded historical comparison across canonical receipts**.

That rung could allow an operator to select two read-admissible canonical state records and derive a temporary comparison without mutating history.

It should still keep:

```text
comparison != cause
comparison != severity
comparison != authority
```

and must not silently promote the derived comparison into canonical memory.
