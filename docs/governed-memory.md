# Governed memory v0.3

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


## Research hardening v0.1: consumption-time read admissibility

The ENTER THE FIELD hardening track adds a narrow consumption-boundary contract without
turning memory into an authority service.

A successful canonical `get()` now returns an inline `ReadAdmissibilityReceipt`.
Every returned semantic-search hit carries one as well. The receipt binds the exact
record version and canonical hash to the principal/task context, current memory-policy
digest, supplied `AuthorityContext` digest, scope, classification, epistemic kind, and
currentness at the point the record is consumed.

The receipt deliberately fixes:

```text
readable_as_context = true
operational_authority = false
action_authority = false
execution_authority = false
```

This makes the no-mint boundary explicit even when a source or derived memory literally
contains instruction-like or permission-like text. Readability means only that the
record may enter bounded context. It does not mean the record is a grant, approval,
verified claim, or executable instruction.

The existing durable `MemoryOperationReceipt` remains the operation-level receipt for
semantic retrieval. These per-record admissibility receipts are returned inline at the
consumption seam; they are not a second canonical memory store or an authority ledger.

The same hardening increment introduces `phios.mandala.AuthorityProjection`, a pure
read-only replay primitive for already-authoritative grant/revoke/expiry events. It can
reconstruct a present-tense `AuthorityContext` within a frozen ceiling, but it does not
authenticate events, mint grants, write authority state, replace `ActionBindingGrant`,
or bypass existing execution-time revalidation.

## Research hardening v0.5: derived transformation lineage

Derived memory now has a stricter provenance boundary.

A record with `epistemic_kind="derived"` must carry:

- one or more `derived_from` source references;
- an `ExactnessClass`;
- the SHA-256 values of the transformation receipts that produced it;
- the effective transformation taint labels.

The full `TransformationLineageReceipt` chain is supplied to
`GovernedMemoryService.put()` and validated before the canonical record is accepted.

Validation binds the final transformation output SHA-256 to the canonical memory content
SHA-256 and rejects broken parent links, exactness upgrades, dropped taints, source
mismatches, or inconsistent final exactness/taint metadata.

This makes the distinction explicit:

```text
derived_from(source)
!=
identical_to(source)
```

The generic operator `put` command therefore refuses direct derived records. A derived
record must arrive through a lineage-producing subsystem or importer rather than through
operator-supplied provenance claims.

The legacy agent-memory importer is one such bounded path. It now receipts extraction
of each deliberation from the complete source JSON as `LOSSY_DERIVED`, with
`canonicalized_representation` and `extracted_subset` taints.

At consumption time, `ReadAdmissibilityReceipt` exposes exactness, lineage hashes, and
taints while retaining:

```text
operational_authority = false
action_authority = false
execution_authority = false
```

Transformation provenance is therefore inspectable context, not permission.

See [Transformation Lineage v0.1](PHIOS_TRANSFORMATION_LINEAGE_V0.1.md).

## Research hardening v0.9: evidence horizon and reconsolidation

Governed memory can now opt into an age-bounded context-admission layer without changing
canonical retention.

Configure `GovernedMemoryService` with an `EvidenceHorizonController` to separate:

```text
record exists canonically
from
record may enter active context now
```

The policy declares a direct-admission age and a later reactivation window.

Direct reads return an `EvidenceHorizonReceipt`. A record that is still inside the
context horizon can proceed to the existing `ReadAdmissibilityReceipt`.

A record that has crossed the context horizon remains in canonical storage but is not
returned as active context. It receives a `ReactivationWindowReceipt` stating whether
the record is still inside the configured reactivation window. That receipt never
authorizes or completes reactivation.

Semantic retrieval applies the horizon filter before vector ranking so stale records do
not consume the top-k ranking budget.

When an already-published head is stale, a newer revision on the hardened path must pass
the `ReconsolidationGate`. The candidate must advance one revision, have a later
creation time, and bind at least one new provenance reference as explicit
reconsolidation evidence.

This remains a provenance/admissibility rule, not a truth engine. Fresh provenance does
not by itself prove the new revision is correct.

See [Memory Evidence Horizon v0.1](PHIOS_MEMORY_EVIDENCE_HORIZON_V0.1.md).

## Operator integration v0.3

The official operator surface is `phi-memory`. Governed memory remains disabled until
an operator creates and edits a local config. Merely installing the optional vector
backend does not enable memory or semantic retrieval.

Create the initial fail-closed template:

```bash
phi-memory init-config
phi-memory status
```

The generated config has both `enabled=false` and `semantic_enabled=false`.
Enabling the feature changes availability only; it does not create grants. Every
mutating or retrieval operation still requires explicit per-invocation permissions.

Examples:

```bash
phi-memory \
  --allow memory.write \
  put \
  --record-id note-001 \
  --source-id operator \
  --source-kind human \
  --scope private \
  --classification operator \
  --text "bounded local memory"

phi-memory \
  --allow memory.read \
  get note-001

phi-memory \
  --allow memory.read \
  search "bounded local memory"

phi-memory \
  --allow memory.index \
  reindex --full
```

Semantic search also requires `semantic_enabled=true` plus an already-installed local
Ollama embedding model. The config declares model name and dimensions and may pin the
model digest. The CLI never pulls a model.

### Legacy agent-memory import

The old `phios.services.agent_memory` narrative files are never migrated
automatically. Import is an explicit, bounded, one-file operation.

Dry-run validation reads the named JSON file and reports deterministic source/record
identities without writing canonical memory:

```bash
phi-memory legacy-import \
  --file ~/.phios/journal/visual_bloom/narratives/agent_memory_example.json \
  --scope private \
  --classification operator \
  --dry-run
```

Actual import requires two distinct grants:

```text
memory.import
+
memory.write
```

Imported deliberations retain the legacy file SHA-256 and deliberation ID as provenance,
are marked as `derived`, and receive deterministic record and operation identities so
the same unchanged source file can be replayed safely. Import does not delete or rewrite
the legacy narrative.

### Receipt reconciliation

v0.3 connects the canonical SQLite outbox to the append-only Mandala ledger through an
idempotent publisher. If a process crashes after ledger append but before the outbox row
is marked published, replay detects the existing deterministic receipt ID and marks the
outbox complete without appending a duplicate. Canonical writes remain unreadable until
their required receipt has been reconciled.

The operator wrapper does not release semantic-search hits when receipt reconciliation
fails.

### Reindex authority

Derived-index maintenance is explicit. `memory.index` is separate from
`memory.read`, `memory.write`, and `memory.import`. A full reindex queues only
currently live, published records inside the configured operator scopes and
classifications. Reindexing still changes only derived state and never changes canonical
record authority or content.
