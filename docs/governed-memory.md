# Governed memory v0.1

PhiOS governed memory is a canonical local record service. It is not an authority
service, executor, truth engine, or automatic belief system.

## Ownership

PhiOS owns canonical records in `memory/canonical.sqlite3`. Records preserve source
identity, provenance references, scope, classification, retention policy, expiry,
source-versus-derived status, contradiction links, content digests, and immutable
revision identity.

The existing experimental `phios.services.agent_memory` narrative archive is unchanged.
It is a future explicit import source, not an implicit fallback.

## Authority boundary

Every operation requires both the existing PhiOS `AuthorityContext` permission and a
deny-default `MemoryAccessPolicy` rule. Unknown principals, scopes, classifications,
or operations deny. Caller content cannot create or widen authority.

Memory content is untrusted contextual data. Instruction-like text inside a memory
record has no operational meaning. Any later action must pass the existing governed
action and execution boundaries independently.

Ordinary memory operations emit `MemoryOperationReceipt`, never
`MemoryPromotionReceipt`. Operation receipts fix promotion and execution authority
to false.

## Lifecycle

Writes use an idempotent host-assigned operation ID. The canonical record, receipt
outbox entry, and future index-work item are committed in one SQLite transaction.
A record remains unavailable until its receipt is marked published.

Deletion creates a tombstone before any future derived-index cleanup. Expiry is checked
on every read, so a late sweeper cannot make expired data readable. Source evidence
owned by SOMA or another subsystem is not deleted when a memory record is deleted.

SQLite and the append-only Mandala ledger are not presented as one atomic transaction.
The durable outbox is the reconciliation boundary.

## Canonical versus derived data

PR 1 contains no vector dependency. `RetrievalIndex` exists only as a replaceable
protocol and defaults to `UnavailableRetrievalIndex`.

Future embeddings and vector indexes are derived artifacts. They must never become the
canonical source of record text, provenance, classification, retention, contradiction,
or authority. Failure of a future index must leave canonical storage intact and must not
fabricate fallback memories.

## Storage and schema

The stdlib SQLite store uses schema version 1 with foreign keys enabled. It contains
immutable record revisions, active heads, tombstones, a receipt outbox, future index
work, and store metadata. SQLite extension loading is not used by the canonical store.

A newer unknown schema version fails closed rather than being silently interpreted.
