# Φ Universal Shell R3 — native GUI integration, no installer shortcuts

R3 adds the **actual PhiShell Apps-window GUI** for the versioned, public-source-only `phios-app-shelf` format used by PhiOS Web and PhiOS Mobile PWA. The PWA and Android HOME are distinct runtimes.

## Linux PhiShell

- The current real Wayfire/PhiShell user session has an **Apps** window that includes **My App Shelf**, a searchable offline copy of the pinned **225-public-source catalog**, and source-only badges.
- Users can pin 24 known GitHub source IDs, reorder, remove, **export** portable JSON, and **import** after an explicit replacement confirmation. The full catalog and canonical `shelf-portable.v1.js` are copied into the existing Vite bundle with byte identity checks.
- Browser localStorage on this **local PhiShell web origin** is used for its own session; it is **not** the same as native Python `interop/app_shelf_v1.py --shelf PATH` storage, and it is not a native host broker. To transfer, export/import JSON deliberately.
- External GitHub source links open only on explicit user click; no automatic network fetch is performed by the shelf. Declared homepage metadata is displayed as **unverified**, never a certified launch endpoint.
- This does **not** install a Linux package, invoke `phi-app`, grant a capability, or infer image readiness. The native OS artifact still requires exact image/recovery/release qualifications.

## Android HOME

The companion PhiOS-Mobile R3 PR adds **Source Shelf** to the *actual Android Home test APK*, independently of the existing native **Pinned Shelf** for installed Android apps. It bundles the identical public catalog JSON, implements a strict Java 24-pin/16-KiB `phios-app-shelf` wire codec and uses Android's document-picker for user-selected import/export. The only action on a source bookmark is explicit external GitHub viewing; no Internet permission is added to the launcher itself, and no APK install is attempted. The native launcher remains an Android HOME test APK, not an Android ROM, and still needs spare-device qualification before daily use.

## Cross-platform proof

- Catalog bytes `interop/public-repo-catalog.v1.json`, PhiShell `phishell/src/data/public-repo-catalog.v1.json`, and Android `android/app/src/main/assets/public-repo-catalog.v1.json` should be byte-identical.
- The original JS portable shelf contract is byte-identical to PhiShell `phishell/public/shelf-portable.js`, Web and Mobile PWA copies.
- Import must reject extra authority fields, unexpected identifiers, duplicate pins, stale snapshot hash, invalid UTF-8, unsupported version and files above 16 KiB.
- Source-only bookmarks must be isolated from real installed-app state and note backups.
- Tests: `cd phishell && npm test && npm run build`; Android `gradle -p android :app:testDebugUnitTest :app:assembleDebug`, then disposable emulator/rollback acceptance. Do not claim physical-device qualification from emulator evidence.

Next: signed app descriptor review and per-platform *verified* launch/installation adapters. Those are separate authority gates, not inferred from any R3 source bookmark.

**Capability != authority. Source pin != installed application.**
