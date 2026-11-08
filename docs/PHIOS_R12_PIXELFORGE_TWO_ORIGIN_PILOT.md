# PhiOS R12 · Separate PixelForge browser pilot, not native installation

**Stage:** exact-origin, operator-consented **browser-only** project-label exchange. Requires a separately reviewed PixelForge child, an exact configured PhiOS origin, and actual two-app browser acceptance. Does not authorize reading world files or importing assets.

## Versioned sources and the connection

- PhiOS [#409](https://github.com/MichaelWave369/PhiOS/pull/409) merged at `0f2438e6877603a4229b5bae2268337168cc0c18`. Two providers can coexist in the V2 browser-local metadata registry, and a real Chrome local-file/import/removal proof passed post-merge.
- PixelForge R12 **client**: [PR #89](https://github.com/MichaelWave369/parallax-pixelforge/pull/89), merged at `b1c6314da005de801ba3b0417ffe4b4abe461828`, now pinned exactly by the R12 two-origin test. Later PixelForge `main` commits added unrelated Metroidvania functionality; we intentionally qualify the reviewed merge revision instead of tracking a moving branch.
- Existing `phios.workspace-bridge.v1` is used with `app_id=pixelforge`, but PixelForge gets **its own iframe, origin binding, session UUID and explicit approval state**; it does not reuse PhiOffice's `app_id`, origin, frame or stored approvals.
- The host requires a strict `VITE_PHIOS_PIXELFORGE_BRIDGE_URL` **and** `VITE_PHIOS_PIXELFORGE_BRIDGE_APPROVED_ORIGIN` pair, configured only for a reviewed, different-origin PixelForge VR Studio URL. No endpoint configured means **no iframe** and no external connection. URLs must match exact origin, cannot have fragment, credentials, or query parameters.
- PixelForge child embeds a single `?phios_parent_origin=` parameter on its URL, checks a matching real `document.referrer` origin, and binds messages to the actual `window.parent`. Host uses `referrerPolicy=origin` for this test-only pilot. The referrer is a consistency check, *not publisher authentication*.

## Actual operator path

1. Export a stable identity-only sidecar in PixelForge VR Studio and import it into PhiOS V2 using the existing R11 local file desk. No scene contents are imported; V1 remains PhiOffice-only.
2. Build PhiOS with the exact reviewed PixelForge endpoint and approved origin. Navigate to Build Field → **PixelForge browser connection**.
3. Click **Start PixelForge pilot**. Only then does the host read the reviewed V2 identities and instantiate the separate PixelForge iframe. A new unapproved host session is generated when that frame loads.
4. Select a previously reviewed **PixelForge V2** ref (never a raw V1 PhiOffice ID). Click **Approve selected PixelForge ref**, read the source/ref, and explicitly confirm the dialog. Sharing is for this frame's session only.
5. In embedded PixelForge click **Request project reference**. Without approval, the host returns `host.denied`; after approval it returns only `host.context` with an opaque `project_ref`.
6. **Revoke PixelForge approval** denies later requests, with the child clearing stale displays after denial. **Disconnect PixelForge pilot** removes the iframe and host. Reconnecting creates a fresh unapproved session; no stored approval is revived.

An operator's approval does not assert ownership of the PixelForge world, guarantee matching world content, or grant access to PhiOffice records, local assets, installed apps, shell commands, network services, private GLBs, credentials, cloud identities, or a native OS installer.

## Fail-closed boundaries

- The host selector uses `decodeProjectRegistryV2` and accepts **only** `providerAppId=pixelforge` plus `source=pixelforge.phios-vr-world-identity.v0.1`. It rechecks exact title/ref/source at approval and again before answering any subsequent request. Any drift revokes the active host grant.
- Every incoming packet requires the exact configured origin, actual iframe `WindowProxy`, versioned protocol, matching app ID/session/request ID and exact shape. The bridge has no wildcard origin and never passes a title, path, project manifest, GLB, world object, token or grant.
- The PixelForge client is dormant standalone; an embedded session requires a valid explicit parent-origin query and matching referrer, and it cannot turn received labels into world-file access. Invalid source, fields, session or replay cannot be accepted.
- Existing PhiOffice R7/R9, the standalone PixelForge scene/save/export workflow, and identity-only R11 operations are unchanged. Different provider IDs do not create shared app permissions.
- An old approved ID is **non-secret** and cannot be retroactively erased from an app's memory. Revocation affects future replies. The runtime's project-ref exchange is not a network credential or production publisher certification.
- The live V2 store uses browser `localStorage`; same-tab and detected cross-tab edits are checked but localStorage does not supply cross-tab compare-and-swap, guaranteed durability or encrypted storage.

## Acceptance before review

- PixelForge #89 must pass its 7 bridge client tests, existing real Chromium sidecar export, and Full Studio validation. Pin its exact revision or merged commit in independent CI.
- PhiOS: `cd phishell && npm ci --no-audit && npm test && npm run build`; full PhiOS qualification including OS/VM gates must pass.
- R12 actual two-origin Chromium: build exact PhiOS and separately checked-out PixelForge, require two distinct `127.0.0.1` origins, isolated browser profile, no live services; assert default denial, unrelated frame/origin impersonation refusal, deliberate selection/confirmation, one opaque field, explicit revocation, fresh reconnect and standalone silence. Stamp the exact source commits.
- **No merged release/native app claim until these pass**. A successful Chromium origin-bound session still does not establish native PhiOS installation, device readiness, production authentication, signed publisher identity or Quest VR compatibility.
