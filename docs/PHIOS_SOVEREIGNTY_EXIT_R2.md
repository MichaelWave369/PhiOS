# PhiOS Sovereignty Exit Test R2: scoped portable state snapshots

**Status: PARTIAL when a real supported backup is successfully bundled and
independently checked. No EXIT-VERIFIED badge or OS publication authority.**

R2 follows [Issue #340](https://github.com/MichaelWave369/PhiOS/issues/340)
without rewriting the existing `phi-state` backup/restore implementation. The
producer's [state recovery contract](os/STATE_RECOVERY.md) already uses SQLite
online backup and validates canonical memory, published receipts and custody.
R2 makes the verified **data-only backup** portable in a standard ZIP envelope,
which can be checked and extracted with Python 3.11+ standard library, even on a
machine without PhiOS installed.

## Scope inventory

| State | R2 status | Basis |
| --- | --- | --- |
| Governed canonical memory | Supported **when present in verified phi-state backup** | `memory/canonical.sqlite3`, SQLite backup API in producer |
| Memory's published receipts | Supported **when present with canonical DB** | `spine-v0.1/ledger/mandala-receipts.jsonl` |
| Curiosity artifacts and pointers | Supported **when present** | Two bounded JSONL files in existing `phi-state` producer |
| Historical audit | Archived only, **never reactivated** | `audit/*.jsonl` and explicitly preserved incomplete tails |
| PhiShell browser-local settings | Not exported | Current Sovereignty Center is a self-audit, not a browser data exporter |
| GitPorch local repositories | Not exported | Separate product and gateway; no complete state-export adapter |
| Enabled config, keys, credentials, grants | Excluded | No reenrollment or resumed authority |
| Derived indexes and model weights | Excluded | Rebuild or acquire separately with permission |
| Other ecosystem app state | Not inventoried exhaustively | Requires app-specific contracts and opt-in adapters |
| Disconnected OS boot and external provider replacement | Not tested | Require future platform-level exit trials |

`inventory` is a **static source-reviewed coverage list**, not an automatic
device scan. Paths are not discovered or harvested.

## Operator flow (source checkout; no local install for independent verifier)

Never commit or upload a real backup. Archives are **UNENCRYPTED** and can
contain private memory and audit content. Preserve offline/private custody.

1. On the **producer machine**, create a verified phi-state snapshot:

   ```sh
   phi-state backup --state-root "$PHIOS_STATE_ROOT" --output ./private-phios-snapshot
   phi-state verify ./private-phios-snapshot
   ```

2. Review the snapshot and explicitly approve packaging:

   ```sh
   python scripts/sovereignty_exit_r2.py inventory
   python scripts/sovereignty_exit_r2.py bundle \
     --verified-phi-state-backup ./private-phios-snapshot \
     --output ./private-phios-r2.zip \
     --i-approve-unencrypted-export
   ```

   `bundle` **requires PhiOS locally** to call its canonical producer verifier.
   It packages only files referenced by the verified phi-state manifest. It
   refuses an existing archive or an output nested in the snapshot directory,
   and never reads browser state, tokens or unlisted sibling files.

3. On a separate compatible machine, copy only
   `scripts/sovereignty_exit_r2.py`, `scripts/sovereignty_exit_v01.py`,
   and the ZIP file. **PhiOS is not needed for these commands:**

   ```sh
   python -S sovereignty_exit_r2.py verify --bundle ./private-phios-r2.zip
   python -S sovereignty_exit_r2.py extract \
     --bundle ./private-phios-r2.zip --output ./inert-snapshot
   ```

   `extract` writes to a **new** directory, creates private directories/files
   (POSIX mode 0700/0600), and never activates credentials, leases, history or
   PhiOS runtime. The extracted SQLite/JSONL files are open formats and can be
   inspected with standard tooling; that is not a validated semantic migration.
   On Windows, review filesystem ACLs separately.

4. An actual PhiOS runtime data restore, if desired, is a **separate,
   operator-directed action** using the PhiOS `phi-state restore` mechanism
   after reading [STATE_RECOVERY](os/STATE_RECOVERY.md). Never copy historical
   approval/lease records into active runtime paths.

## Evidence semantics and limitations

- Outer `phios.exit.v0.1` ZIP manifest verifies size and SHA-256 of the bytes.
  Inner `phios.data-backup.v1` manifest is checked again for file allowlist,
  sizes, hashes, schema and false authority/config/index flags.
- Both manifests are **unsigned**: checksums indicate self-consistency, not
  authenticity, a trusted publisher, or that the producer captured everything.
- The producer is responsible for live SQLite consistency and canonical
  semantic verification. Independent R2 verification does **not** repeat those
  PhiOS-specific semantic checks or prove a new runtime can use the contents.
- The v0.1 ZIP envelope limits total uncompressed input to 512 MiB and 10,000
  files. Larger real-state exports need a reviewed streaming successor.
- Receipt output intentionally prints coverage, omissions and content digests
  without raw memory, audit text, secret values or host-specific paths.
- No service startup, network request, background scan, auto-remediation,
  revocation, application import or authority change occurs.
- R2 passing test fixtures do **not** satisfy the physical disconnected
  cold-boot, complete ecosystem inventory, cloud-provider exit, secret scrub,
  hardware or independently signed evidence gates in #340.

## CI

```sh
python -m unittest discover -s tests -p "test_sovereignty_exit_r2.py" -v
```

Tests produce actual `phi-state` backups from synthetic data, check ZIP/manifest
tampering, excluded extra files, fresh private extraction, refusal to overwrite,
and run stdlib verification/extraction from a separate directory with Python
site packages disabled (`-S`). This demonstrates a bounded standalone code
path, not a physically disconnected device test.

**Ledger Above Ego: PARTIAL is not EXIT-VERIFIED.**
