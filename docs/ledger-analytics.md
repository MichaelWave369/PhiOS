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
ledger.analytics.export
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
<state_root>/analytics/snapshots/<snapshot-id>/
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
phi-analytics \
  --allow ledger.analytics.export \
  snapshot-export
```

No DuckDB dependency exists in v0.1. That is intentionally deferred to the next
increment, where a disposable projection will consume only validated snapshots and will
expose named reports rather than arbitrary SQL.
