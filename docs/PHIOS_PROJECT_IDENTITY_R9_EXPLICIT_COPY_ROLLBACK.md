# PhiOS R9: Explicit Provider-Qualified Registry Copy and Rollback

**Stage:** opt-in browser-local V2 **copy only**. PhiOS continues to use V1 for the existing PhiOffice session, local saved project selection, portable reference export, and consent-gated `phios.workspace-bridge.v1` transport.

R8 introduced an identity pair `[providerAppId, projectRef]` and read-only preview. R9 adds the minimum governed, reversible *local metadata copy* for the existing, reviewed PhiOffice provider. **This does not activate a second provider, cut the application over to V2, enable file access, install PhiOffice, or authorize an agent.**

## Operator path

The feature appears only in a PhiShell build with an explicitly reviewed, different-origin PhiOffice pilot URL and approved origin configured. An unconfigured PhiOS/standalone PhiOffice does not run the bridge.

1. Start the opt-in PhiOffice pilot. Select or remember actual local reviewed PhiOffice project references in the usual V1 interface.
2. Use the existing **Export project references** button to *request* an external V1 JSON export. **Check the downloaded file**; initiating the browser download does not prove persistence. The export contains project titles and may be sensitive but carries no credentials.
3. Click **Preview provider-qualified project IDs**. This performs reads only. Each mapping derives the provider from the sealed reviewed adapter catalog. A missing/empty/damaged V1 store, unknown source, existing V2 store or schema conflict refuses the preview.
4. Review each entry. Click **Create V2 metadata copy (keep V1)** and answer the explicit confirmation. The commit re-reads the exact V1 bytes and demands an absent V2 destination, verifies the previously reviewed payload and performs exactly one `localStorage.setItem` to `phios.project-registry.v2`.
5. Successful commit reads V2 back and checks the exact bytes. **Browser API read-back is not disk/power-loss durability evidence.** V1 was not rewritten and remains the active application registry. No session approval transfers.
6. For rollback, click **Inspect existing V2 copy**. The UI validates V2 and refuses to offer deletion unless the current V1 record set yields the **exact same V2 serialization**. Review every provider/project reference, then click **Remove reviewed V2 copy (keep V1)** and separately confirm. The removal rechecks source equivalence and byte-for-byte V2 agreement before deleting V2, and verifies V2 is absent afterward.

Rollback can be reviewed again after page reload because no secret runtime rollback token is needed. Conversely, a changed V1/V2 record, missing V1 or malformed V2 blocks deletion. Do not delete a V2 record that is the only surviving metadata copy or that contains unique entries. V1 remains available throughout the R9 flow.

## Exact boundaries

- All V1 codecs, V1 persistent bytes, V1 portable exports, the PhiOffice manifest reader, and the cross-origin bridge protocol remain unchanged.
- No automatic copy occurs on page load, a regular app launch, or background browser events. V2 writes/removal require a **visible button and explicit operator confirmation**.
- The V2 record contains only `providerAppId`, `projectRef`, `title`, and `source`. Allowed providers come from reviewed source code. Only PhiOffice is allowed.
- No publisher signing, artifact content, private manifest fields, paths, credentials, PhiID, PhiCloud, external fetch, device rights, or native install occurs.
- **No cross-tab atomicity guarantee:** `localStorage` does not provide compare-and-swap or multi-key transactions. The implementation revalidates immediately before writes/removals and fails closed on known changes. Concurrent writes from another tab, hostile scripts in the same origin, storage eviction and actual disk durability remain separate security/reliability issues.
- If a write reports a read-back mismatch, do **not** blindly retry; inspect current V1 and V2 first. The system will never implicitly overwrite an occupied V2 destination.

## Tests and acceptance

```sh
cd phishell
npm ci --no-audit
npm test
npm run build
```

`projectRegistryV2Copy.test.ts` covers no writes until confirmed, byte-preserved V1, exact source matching, storage quota failures, changed V1 between preview/commit, destination conflicts, malformed/unreviewed sources, exact V2 verification, safe rollback, post-review modification refusal, and no deletion if V1 has disappeared or diverged.

**Additional release gate:** A rendered Chrome acceptance must exercise the UI buttons, confirm/cancel, the exact V1/V2 storage bytes, reconnect without revived app permission, and malformed destination refusal before calling R9 cross-app browser qualified. Existing PhiOffice R7 Chromium evidence verifies the unchanged V1 handoff, not this new V2 copy UI.

A second provider still requires separate real source-format review, collision and migration testing, a working standalone app, a new origin-bound two-app browser acceptance, and an explicitly governed admission decision.
