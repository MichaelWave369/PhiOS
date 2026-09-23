# PhiShell v0.11 — Governed Persistent History

Status: **candidate implementation**  
Target substrate: **PhiShell v0.10 history + PhiOS governed canonical memory**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.11 adds an explicit operator-governed path for persisting validated system-state and system-change receipts into PhiOS-owned canonical memory.

It does **not** make browser history persistent automatically.

## Architecture

```text
PhiShell v0.10
validated system state A
validated system state B
validated change receipt
        │
        ▼
operator-controlled export / handoff
        │
        ▼
SystemHistoryPersistenceBridge
        │
        ├─ requires history.persist
        ├─ requires memory.write
        └─ never writes SQLite directly
        │
        ▼
MemoryOperatorRuntime
        │
        ├─ deny-default MemoryAccessPolicy
        ├─ canonical revisioned MemoryStore
        ├─ durable receipt outbox
        └─ MemoryReceiptPublisher
        │
        ▼
canonical.sqlite3
        +
Mandala append-only receipt ledger
```

## No browser write authority

PhiShell continues to expose:

```text
history.inspect = available
history.persist = unavailable
```

The browser cannot:

- write the canonical memory database;
- call the persistence bridge;
- grant itself `history.persist`;
- grant itself `memory.write`;
- publish Mandala receipts;
- silently promote session history into canonical history.

Session history therefore remains:

```text
session_persistent = false
```

until an operator explicitly moves selected evidence through the governed memory path.

## Two explicit authorities

Persistent system history requires both:

```text
history.persist
memory.write
```

The bridge checks `history.persist` first.

The existing governed-memory service then independently checks `memory.write` through:

- the active AuthorityContext;
- the configured principal;
- the deny-default memory policy;
- the configured scope;
- the configured classification.

Therefore:

```text
memory.write
    !=
history.persist

history.persist
    !=
memory.write
```

Both are required.

## Canonical state records

Each persisted:

```text
phios.system-state.v1
```

receipt becomes one canonical MemoryRecord with:

```text
record_id =
  phishell.system-state.<receipt sha256>

source_id       = phishell.system-state
source_kind     = subsystem
epistemic_kind  = source
revision        = 1
```

The complete supplied receipt is stored as strict canonical JSON text.

The configured memory runtime supplies:

- scope;
- classification;
- retention policy.

The state receipt's SHA-256 is retained as provenance.

## Canonical change records

Each persisted:

```text
phios.system-change.v1
```

receipt becomes a canonical derived MemoryRecord:

```text
record_id =
  phishell.system-change.<change sha256>

source_id       = phishell.system-change
source_kind     = subsystem
epistemic_kind  = derived
revision        = 1
```

Its `derived_from` references point directly at the two canonical state record IDs.

## Transformation lineage

A change receipt is not relabeled as source evidence merely to simplify storage.

The bridge builds a real:

```text
TransformationLineageReceipt
```

with:

```text
transform_id      = phishell.system-change
transform_version = phios.memory.system-history.v0.11
source_refs       = previous + current canonical state record IDs
source_sha256s    = previous + current system-state receipt hashes
output_ref        = canonical change record ID
requested_exactness = REVERSIBLE
information_loss_possible = false
semantic_inference        = false
operational_authority     = false
action_authority          = false
execution_authority       = false
```

The change MemoryRecord carries the lineage receipt hash.

The existing GovernedMemoryService verifies that lineage before accepting the derived record.

## Descriptive semantics remain frozen

Persistence does not upgrade v0.10 semantics.

A persisted change receipt still carries:

```text
causeAssigned    = false
severityAssigned = false
```

Persistent history therefore still means:

```text
this changed
```

not:

```text
this caused that
this is dangerous
this should be repaired
```

## Canonical store boundary

The bridge never calls:

```text
MemoryStore.put_pending()
sqlite3.connect()
INSERT
UPDATE
```

directly.

It calls only:

```text
MemoryOperatorRuntime.put()
```

The existing runtime remains responsible for:

- enable/disable configuration;
- authority;
- policy;
- canonical record creation;
- publication state;
- receipt publication.

## Receipt publication

Successful writes enter the existing durable memory receipt outbox.

`MemoryReceiptPublisher` reconciles those receipts into:

```text
MandalaReceiptLedger
```

The canonical record becomes published only through that existing path.

v0.11 therefore does not create a second history ledger.

## Idempotency

Canonical record IDs and operation IDs are derived from receipt hashes.

Re-persisting the identical transition:

- does not create duplicate canonical versions;
- does not duplicate Mandala receipts;
- returns the same canonical record identities.

## Operator command

The explicit CLI surface is:

```bash
phi-memory \
  --config ~/.phios/memory/config.json \
  --state-root ~/.phios/memory \
  --allow history.persist \
  --allow memory.write \
  persist-system-history \
  --previous-state previous-state.json \
  --current-state current-state.json \
  --change-receipt change.json
```

Without either explicit grant, persistence fails closed.

The configured memory principal must also permit the resulting records' configured scope and classification.

## Returned receipt

Successful persistence reports:

```text
persistent = true
canonical = true
state_record_ids
change_record_id
state_receipt_ids
change_receipt_id
operational_authority = false
action_authority = false
execution_authority = false
```

These authority fields mean the resulting evidence does not grant later machine authority.

They do not mean the persistence write itself was ungoverned. The write required the two explicit grants above.

## Tests

v0.11 proves:

- state receipts persist as canonical source records;
- change receipts persist as canonical derived records;
- change lineage points to the two canonical source record IDs;
- exactness is REVERSIBLE;
- transformation lineage is published in the memory operation receipt;
- scope/classification/retention come from governed memory config;
- Mandala receipts are appended;
- repeated persistence is idempotent;
- missing `history.persist` is denied;
- missing `memory.write` is denied;
- mismatched transition references are rejected.

## What v0.11 does not add

v0.11 adds no:

- automatic browser persistence;
- remote persistence API;
- generic filesystem writer;
- second SQLite database;
- second ledger;
- semantic interpretation of changes;
- severity scoring;
- remediation;
- Linux privilege;
- service/process/package/device mutation.

## Next increment

A safe v0.12 candidate is a **read-only persistent history projection**.

It should allow PhiShell to query canonical system-history records through a narrow local read adapter, with:

- explicit memory.read;
- bounded result count;
- retention/currentness checks;
- read-admissibility receipts;
- no direct SQLite access from the browser;
- no semantic retrieval requirement;
- no mutation endpoint.

Persistent write and persistent read should remain separately governed capabilities.
