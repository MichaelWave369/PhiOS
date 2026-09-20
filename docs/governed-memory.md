# Governed memory v0.2

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


## Semantic retrieval v0.2

Semantic retrieval is optional and replaceable. Install the reviewed backend with
`phios[memory-vector]`, which pins `sqlite-vec==0.1.9`. Base PhiOS does not require
the native extension.

The canonical database never loads sqlite-vec. Each embedding identity owns a separate
derived generation under a caller-selected index path. A generation stores only record
ID, revision, canonical record hash, and float32 vector bytes. Canonical text, grants,
classification policy, and source evidence remain outside the vector database.

`OllamaEmbeddingProvider` accepts only a loopback HTTP server root. It checks the
configured model against Ollama's local model inventory, binds the resolved model
digest and Ollama version into `EmbeddingIdentity`, disables truncation, validates
finite dimensions, and has no model-pull or cloud-fallback path.

Retrieval order is deliberately strict:

1. resolve existing PhiOS authority and deny-default memory policy;
2. select only live/published canonical versions in authorized scopes/classifications;
3. generate a query embedding with the active local model identity;
4. rank only the pre-authorized version allowlist in the derived sqlite-vec database;
5. rehydrate every candidate from canonical storage and recheck current policy/liveness;
6. persist a `MemoryOperationReceipt` binding the query digest, model identity, index
   generation and returned record versions before returning hits.

The public score is named `retrieval_distance`, never confidence. Similarity does not
promote a source or derived record, resolve contradictions, grant capabilities, or
authorize tool execution.

`sync_index()` is explicit maintenance rather than an automatic background actor.
It processes canonical index-work items, refuses stale/deleted/expired upserts, purges
deleted record vectors, and receipts successful derived indexing. If the embedding
model, digest, native extension, or active generation is unavailable/mismatched, the
work remains retryable and semantic retrieval reports unavailable. There is no lexical,
generated, or cloud fallback presented as semantic memory.
