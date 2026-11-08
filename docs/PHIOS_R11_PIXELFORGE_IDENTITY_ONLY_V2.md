# PhiOS R11 · PixelForge identity-only V2 import and removal

**Review status:** candidate. Zero additional browser app authority. No new native package, service, account, or device permission.

## Provenance and scope

- PixelForge [PR #88](https://github.com/MichaelWave369/parallax-pixelforge/pull/88) is merged to PixelForge `main` as `208e70ffcd467551d25a9f9c1058a6ced37f0fd5`. Its real VR Studio exporter and Chromium download acceptance were green on the merged commit.
- PhiOS [PR #407](https://github.com/MichaelWave369/PhiOS/pull/407) is merged, with an independent strict parser for `pixelforge.phios-vr-world-identity.v0.1`. That R10 parser intentionally remained unadmitted to the active browser project adapter catalog.
- PhiOS #408 fixed a pinned Arch archive transient connect-timeout path. Its **post-merge** fixture-free native-image qualification passed at `a3e1e8278d094ef32a8ef9808b9a1aa7c56c8486`.

**R11 identity-only scope:** V2 metadata recognizes two explicitly bounded sources:
`phioffice369.project_manifest.v0.1` provider `phioffice`, and
`pixelforge.phios-vr-world-identity.v0.1` provider `pixelforge`.
This does **not** register PixelForge as a `REVIEWED_PROJECT_ADAPTERS` runtime app, launch an iframe, create cross-origin message handlers, upload a world, attest a project owner, or grant access to a file.

V1 and its portable reference format stay PhiOffice-only, unchanged. The existing PhiOffice `phios.workspace-bridge.v1` session, frame source, origin and approval mechanism are unchanged.

## Operator workflow (Build workspace)

1. Use the **PhiOffice bridge pilot** to remember a reviewed PhiOffice V1 reference. Export its V1 reference JSON to an independently checked file if desired; a browser download request is not proof that the file exists.
2. Use the existing **Preview provider-qualified project IDs** and operator-confirmed **Create V2 metadata copy**. This establishes the initial existing V1/V2 source-preserving relationship. No approval transfers.
3. In **PixelForge VR Studio** separately, enter an operator-chosen durable ID under World File and click **Export PhiOS identity-only JSON**. Check that the browser really saved the file. Do not substitute a full world JSON or an unreviewed schema.
4. In PhiOS Build → **PixelForge → PhiOS · reviewed identity-only metadata**, select that file. The file is read only after the operator picks it. It must be under 4 KiB and pass the independent strict R10 parser.
5. The desk shows provider, project ref, title, and whether an identical text ref is present in PhiOffice. **Import does not occur until the separate Confirm button and browser confirmation**. The V2 commit checks exact previous V1+V2 bytes and the newly validated payload, then performs one `localStorage.setItem` to V2 and checks its read-back.
6. To remove one PixelForge metadata record, click **Inspect saved PixelForge V2 IDs**, then **Review PixelForge identity removal** next to the exact ID, then **Confirm removal** and approve the dialog. Only that provider-qualified pair is removed. PhiOffice records, all V1 bytes and actual PixelForge scenes remain untouched.

### Same-ID example

For independent IDs `project:same-project`:
```json
["phioffice", "project:same-project"]
["pixelforge", "project:same-project"]
```

They are distinct keys and may coexist as two V2 entries. The V2 store remains capped at 24 records and 16 KiB. Both are metadata labels, not capabilities or proof of ownership.

### Refusal and rollback behavior

- Malformed/unknown sidecar schemas, unsafe IDs, extra fields, forged grants, oversized JSON and corrupt stored V1/V2 are rejected.
- A PixelForge pair already in V2 is rejected, even when its title differs. There is no implicit rename/update; remove it after review, then import a new version deliberately.
- Source or destination changes between preview and approval cause rejection. `localStorage` is not cross-tab transactional, so known drift is refused, but simultaneous-tab races and physical durability cannot be guaranteed.
- The older R9 **Remove reviewed V2 copy (keep V1)** action refuses mixed-provider V2, because V2 is no longer an exact copy of V1. This is intentional: R9 must not accidentally delete the new PixelForge records. Use the R11 **per-PixelForge identity removal** flow first, then (once V2 equals V1 again) the existing R9 entire-copy rollback can be reviewed.
- A missing/uninitialized V1/V2 PhiOffice foundation is not silently manufactured or replaced.

## Evidence and next gates

`phishell/src/shell/pixelForgeV2IdentityImport.test.ts` verifies two different providers with identical text IDs, explicit approvals, exact current-state checks, multi-ID import, per-record removal and safe denial. The previous PixelForge candidate contract continues to check the merged producer format, though its compiled adapter is **still not a live app**.

Run `cd phishell && npm ci --no-audit && npm test && npm run build` and the full PhiOS qualification workflow before reviewing. No merge or release is authorized by this change.

**Still not completed:** independent **real two-origin browser app bridge** from actual merged PixelForge to PhiOS, with a separately reviewed PixelForge client, origin/frame/session selection, request denial before approval, explicit consent, revocation, fresh reconnect, and native launch/install checks. That is a later rung. A green V2 metadata-import test cannot substitute for it.
