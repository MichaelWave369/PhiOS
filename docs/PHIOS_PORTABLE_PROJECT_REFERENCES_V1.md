# Portable PhiOS Project References v1

**Status:** offline, manually exported and imported project reference metadata.
No file transfer, authority grants, cloud account, ownership attestation, or
automatic application permission is involved.

## Scope

The `phios.project-references` v1 portable format has three top-level keys:

```json
{
  "format": "phios.project-references",
  "version": 1,
  "entries": [
    {
      "projectRef": "project:sample",
      "title": "Sample Workspace",
      "source": "phioffice369.project_manifest.v0.1"
    }
  ]
}
```

Each entry is checked against the existing strict PhiOS project registry
codec. Only the reviewed PhiOffice source is accepted for now. Future
applications can only join through reviewed, versioned source adapters.

**The bundle is NOT a PhiOffice project manifest** and contains no documents,
artifact inventory, file handles, paths, tags, owner data, account identity,
tokens, or consent. The file's titles/IDs may still be personal metadata.
Inspect it before distributing it.

## Export

In the explicitly configured PhiOffice browser pilot, choose
**Export project references** after opt-in saving some references.
The browser creates a local JSON download with at most 24 entries and 16 KiB.
The export re-reads the current local registry and refuses corrupt content.
No server endpoint is contacted. The file contains neither runtime
session state nor application permissions.

## Import

Use **Import project reference bundle** to choose a local JSON file.
The picker does not write to storage. The preview verifies exact format,
version, fields, reviewed source, unique IDs, size and capacity. The operator
must then click **Confirm reference import**.

- Existing local entries always win on identical `projectRef`, including
  their local titles.
- New entries are appended in file order.
- If the combined list would exceed 24 items, the entire import is rejected.
  Nothing is silently dropped or overwritten.
- The confirmation re-reads local storage and revalidates the merge to
  reduce stale-tab clobbering. The browser storage API still offers no
  cross-tab transaction guarantee; do not claim otherwise.
- Import never selects a project, starts an application, approves access,
  restores a session or enables future artifact APIs.
- Cancel or disconnect clears the preview; no data is written.
- Invalid local storage is not silently replaced. Use the existing explicit
  **Clear saved project list** control to repair it.

## Validation

`cd phishell && npm ci && npm test && npm run build`

`projectRegistryPortable.test.ts` covers metadata-only round-trip,
malformed formats, injected permissions and tokens, unapproved source
types, duplicate identities, byte limits, conflict resolution and atomic
limit rejection. The companion two-app Chrome gate should cover
preview-before-write, explicit confirm, invalid bundle rejection, and
the original fresh-consent on reconnect invariant.

## No cross-app data access

Even when an imported project reference becomes selected in the future,
the existing `phios.workspace-bridge.v1` host still requires explicit
per-session operator approval and supplies only an opaque reference.
That reference cannot open documents or authorize PhiID/PhiCloud requests.
Provider-specific data operations must define separately scoped, revocable,
user-auditable permissions.

Next engineering rung: a typed application project adapter registry that
accepts providers only through explicit validation and conflict policies.
