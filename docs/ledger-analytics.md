# Reality Ledger analytics v0.1 — stable snapshots

PhiOS analytics begins with a narrow rule:

```text
analytics != authority
```

v0.1 exports immutable, derived snapshots of the two canonical append-only receipt
streams. It does not query live execution state, does not read binding claims, and does
not grant anything.

## Sources

The exporter reads exactly:

```text
<state_root>/ledger/receipts.jsonl
<state_root>/ledger/mandala-receipts.jsonl
```

It does not accept arbitrary source paths. The `binding-claims/` directory is outside
the export surface.

Export requires the explicit permission:

```text
ledger.snapshot.export
```

## Stable-prefix semantics

Each stream is captured independently.

The exporter:

1. opens the canonical file without following symlinks;
2. records the opened file identity and byte size;
3. reads at most that starting size;
4. verifies that the opened file identity did not change and that the file did not
   shrink during capture;
5. discards any incomplete final JSONL fragment;
6. rejects malformed complete rows, duplicate JSON keys, excessive JSON nesting,
   oversized rows, excessive row counts, and unknown schema/receipt versions.

Appends that happen after the starting size are outside that snapshot.

This is deliberately **not** described as one globally atomic two-file snapshot. The
execution and Mandala streams are separate append operations in the current runtime.

## Projection and redaction

The snapshot is a derived projection, not a byte-for-byte copy of every source field.

The default mapping keeps bounded analytical fields such as:

- receipt IDs and parent links;
- timestamps;
- status/outcome fields;
- capability and planner IDs;
- input/artifact hashes;
- permission status;
- receipt type;
- bounded counts;
- memory operation/index status.

The default mapping excludes fields that can carry live authority or sensitive local
details, including:

- Gate authority dictionaries;
- artifact paths;
- raw execution error text;
- external identifiers;
- perception provenance locators;
- source evidence locators.

Every projected row retains source line/byte position and a SHA-256 of the exact source
row bytes.

## Snapshot identity

Each stream manifest binds:

- logical source name;
- opened source-file identity hash;
- starting source size;
- captured byte count;
- incomplete-tail byte count;
- line count;
- SHA-256 of the exact captured source prefix;
- SHA-256 of the projected JSONL bytes.

The snapshot core also binds the mapping version, policy digest, coverage state, and
fixed no-authority metadata.

`snapshot_id` is the SHA-256 of that canonical core. Re-exporting unchanged source
streams under the same mapper/policy reuses the same snapshot directory after verifying
the existing projection hashes.

## Coverage and lineage

The exporter never invents missing relationships.

If an execution receipt points to a Gate/Action receipt outside the captured Mandala
prefix, or a Mandala receipt names a missing parent, the snapshot is still exported but
its coverage is marked incomplete and the missing links are listed in the manifest.

## Output

Default location:

```text
<state_root>/derived/ledger-snapshots/<snapshot-id>/
  manifest.json
  execution.jsonl
  mandala.jsonl
```

The manifest explicitly fixes:

```text
promotion_status = not_promoted
action_authority = false
execution_authority = false
```

## CLI

```bash
phi-ledger \
  --allow ledger.snapshot.export \
  snapshot-export
```

No DuckDB dependency exists in v0.1. That is intentionally deferred to the next
increment, where a disposable projection will consume only validated snapshots and will
expose named reports rather than arbitrary SQL.


## Read-only DuckDB reports v0.2

DuckDB is an optional, derived report engine. Install the reviewed backend with:

```bash
python -m pip install -e ".[ledger-reports]"
```

PhiOS pins `duckdb==1.5.5` for this increment. DuckDB does not open the live Ledger
files. The trusted parent validates the immutable snapshot, maps approved fields into
fixed typed rows, and passes only those rows to a disposable worker workspace.

### Isolation

The worker is qualified only on Linux in v0.2. It reuses the existing PhiOS bubblewrap
and rlimit controls with:

- network namespace denied;
- private home and temporary directory;
- read-only system roots;
- a single disposable writable workspace;
- bounded CPU, address space, open files, output size, and wall clock;
- no canonical PhiOS state root mount;
- no unsandboxed fallback.

Windows is intentionally unqualified for this worker in this increment.

### DuckDB configuration

The worker starts DuckDB with external access disabled. Known-extension auto-install
and autoload are disabled, community and unsigned extensions are disabled, persistent
secrets and global S3 configuration are disabled, logging is disabled, threads and
memory are bounded, temporary storage is bounded, and configuration is then locked.

Projection construction uses fixed `CREATE TABLE` statements and parameterized inserts.
DuckDB never receives snapshot file paths, Python data-frame objects, replacement scans,
or live Ledger locations.

Report connections reopen the finished database with `read_only=True`.

### Authority

Three permissions remain separate:

```text
ledger.snapshot.export
ledger.report.build
ledger.report.read
```

None implies either of the others.

Derived projections and reports explicitly carry:

```text
promotion_status = not_promoted
action_authority = false
execution_authority = false
```

DuckDB has no grant writer, Ledger writer, executor registry, memory service, or callback
into the Spine execution loop.

### Closed query catalog

The public surface accepts report names, never SQL text:

```text
execution_outcomes_v1
permission_denials_v1
repeated_failures_v1
lineage_v1
coverage_v1
```

Results are bounded and every report binds its snapshot ID, projection ID, projection
SHA-256, query catalog version, row limit, exact rows, and truncation state.

The first reports deliberately do not fabricate metrics the current receipts do not
contain. In particular, no latency, resource-use, fallback, or inferred root-cause
fields are synthesized.

### Derived storage

```text
<state_root>/derived/ledger-projections/
  <snapshot-id>/<projection-id>/
    manifest.json
    projection.duckdb

<state_root>/derived/ledger-reports/
  <report-id>.json
```

A projection database is hashed before publication. Every later report verifies that
hash before the worker receives a disposable copy.

DuckDB failure or sandbox unavailability affects only report capability. It cannot alter
canonical Ledger state, execution receipts, grants, governed memory, or action authority.
