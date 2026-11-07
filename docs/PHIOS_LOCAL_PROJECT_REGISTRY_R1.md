# PhiOS Local Project Registry R1

**Status:** browser-local, opt-in, metadata-only foundation. Not a
cloud registry, database service, identity provider, project filesystem, or
cross-origin sharing entitlement.

## What is implemented

PhiOS now has `phishell/src/shell/projectRegistry.ts`, a strict,
versioned codec for **operator-saved project references**. PhiOffice's
`phioffice369.project_manifest.v0.1` is the first reviewed source.
Other source adapters must be individually added and tested. Saved records
contain exactly:

```json
{
  "projectRef": "project:example",
  "title": "Example Project",
  "source": "phioffice369.project_manifest.v0.1"
}
```

All three fields are metadata. A project ID is **not** a password, token,
permission, or filesystem path. No ownership or authenticity attestation
occurs when a local project manifest is selected.

## Operator workflow

1. Use an explicitly configured, approved two-origin PhiOffice browser pilot.
   Without that build-time setup, **no iframe or registry UI is active**.
2. Start the pilot and choose a valid local PhiOffice v0.1 project manifest.
3. Optionally click **Remember this project on device** to save **only** its
   validated ID, display title and source to this browser origin's
   `localStorage`. No project data, title encryption, file handles or grants
   are saved.
4. Disconnect or reload the page. When reopening the pilot, the operator can
   choose a saved reference and click **Use remembered project**.
5. Sharing is **still disabled** until a separate
   **Approve selected project ref** action. Each iframe navigation,
   selection replacement and disconnect revokes future reads.
6. **Forget saved project** deletes that local list entry. **Clear saved
   project list** explicitly clears all saved entries. Neither operation can
   revoke an ID that was already delivered to a previously connected app.

## Data and storage boundaries

- Storage key: `phios.project-registry.v1` (separate from layout snapshots).
- Strict format/version; allowlisted source; exact entry fields only; max
  24 projects and 16 KiB of JSON. Duplicate refs, unknown fields,
  permissions, tokens and unreviewed sources are rejected.
- Malformed storage is **not overwritten automatically**. The pilot shows a
  local notice; the operator must explicitly clear the list to repair it.
  Browser storage quota/security errors are surfaced.
- Saving is **never automatic** when a manifest is selected, and neither
  consent nor the selected active project is restored after reload.
- The list is tied to the current PhiOS browser origin and browser profile.
  It is not magically synchronized across browsers, devices, users,
  separate hosting origins, or the native PhiOS system.
- `localStorage` is readable by scripts running on the same trusted PhiOS
  origin. Treat project titles/IDs as locally visible metadata, not secrets.
  Use **Forget** or **Clear** if leaving the device or browser profile.
- The displayed source is informational provenance, not a certification of
  a document or identity. Every future artifact API needs independent,
  per-operation authorization.

## Tests

```sh
cd phishell
npm ci
npm test
npm run build
```

`projectRegistry.test.ts` covers strict schema validation, injected grants,
unknown fields, duplicates, cap enforcement, controlled upsert/delete,
storage failures, and explicit persistence without authority state.

PhiOffice's companion real-Chrome two-app acceptance tests an actual
file picker, explicit Save, disconnect/reconnect, selecting a saved
reference and **default denial on reconnect**, plus no private manifest
fields crossing the existing read-only protocol.

## Next rung

Add a reviewed portable metadata-only export/import contract and a typed
multi-provider adapter, then an explicit consent and authorization layer
before any PhiID/PhiCloud integration. This registry should **never**
automatically make a project readable by another app.
