# Φ Universal Shell R2: App Shelf and portable source identities

**R2 status: source discovery, personal bookmarks, and interchange. Not universal installation.**

## Working interfaces

- **PhiOS Web:** an App Shelf appears on the `/os/` desktop. Pin any of the shared public source records, reorder with Up/Down, remove, export JSON, or explicitly import a JSON shelf. The browser stores it in a dedicated IndexedDB record, separate from notes and the workspace backup. The browser's PWA and the normal gateway are retained.
- **PhiOS Mobile PWA:** a matching App Shelf appears on Home above Public App Catalog. The shelf can pin/reorder/export/import the same records using local browser storage, separate from its existing Notes/Vault, PhiOperator and Field Companion state. No hidden sync.
- **PhiOS native Linux:** `python interop/app_shelf_v1.py --shelf ~/my-phios-shelf.json pin github:1312447255` is a read/write *source bookmark* CLI. `list`, `unpin`, `move ... up|down`, `export --output ...` and `import --input ... --confirm-replace` are explicit operator actions. This is not yet exposed in the Wayfire/PhiShell visual desktop. The existing OS VM boot qualification and governed App Platform remain separate.
- **PhiOS Android HOME APK:** its **already installed Android app** pin shelf remains unchanged. The portable public source shelf currently exists in the **PWA**, not the Android native APK. Native interoperability and physical-device qualification remain future work.

### One exact wire format

```json
{
  "format": "phios-app-shelf",
  "version": 1,
  "catalog_source_sha": "e295f6265e60032de98a2acd8e53295505fc47e8",
  "exported_at": "2026-11-05T22:00:00.000Z",
  "pinned": ["github:1312447255"]
}
```

The same `interop/shelf-portable.v1.js` code ships byte-identically as `os/shelf-portable.js` and `src/shelf-portable.js` in Web/Mobile. Native Python validates the same schema and identifiers. Limits: **24 unique pins**, **16 KiB JSON**, exact keys and version, stable GitHub numeric IDs, known public-source catalog only. A different snapshot hash is refused rather than silently remapping pins. Explicit confirmation is required before replacing a shelf. JSON is plaintext, contains public IDs only, and is never an application package or a proof of installation.

### Classification & compatibility badges

In R2 each source is only **SOURCE ONLY**. Existing catalog `declared_homepage` can produce a separate **SITE DECLARED (UNVERIFIED)** label, but never a clickable launch-certified or installable badge. Owner-declared URLs are not an installation endpoint and their availability is unverified. Device-specific *installed* and *launch authorized* badges require actual local runtime evidence later.

`interop/app-descriptor.v1.schema.json` is the common proposal-only manifest vocabulary. A proposal may classify candidate runtime type and targets but fixes `review_status: unreviewed`, `install_authority: false`, `launch_authority: false`. It cannot bypass any PhiOS App Platform v0.58 compatibility, exact source/commit, license, sandbox, install, update, rollback or launch gates.

### Future installation adapters, independent of R2

1. **Web:** qualified browser app/PWA service worker with explicit browser install prompt, or verified external URL opened by the user. Pinning a repo is not installing its code.
2. **Android:** signed APK intake and platform Package Installer with independent user approval, manifest/permission review, package identity and rollback. Retain stock Home, never silently change defaults or firmware.
3. **Linux PhiOS:** only governed source build/runtime/installation through existing operator App Platform grants, exact artifacts, receipts, and rollback readiness. Public release and physical hardware remain unqualified until separately proven.

This R2 implementation does **not** flash phones, boot Linux in a browser, clone repositories, run remote code, install packages, grant native permissions, or sync cross-device data.

## Release/test gates

- Core: `pytest -q tests/test_universal_app_shelf_v1.py`, full PhiOS CI, native image/recovery jobs remain separate.
- Mobile: `npm run check && npm test && npm run build`; native Android HOME code and APK signing remain unchanged.
- Web: Python contract tests, complete no-build Netlify ZIP including offline shell, and Chromium desktop/phone shelf pin/reload/export/import regression.
- No Netlify production deployment or automatic phone install is performed by any PR.

**Capability != authority. Installed != runnable. Pinned != installed.**
