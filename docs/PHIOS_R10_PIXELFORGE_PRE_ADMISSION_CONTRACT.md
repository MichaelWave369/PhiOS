# PhiOS R10: PixelForge VR candidate identity pre-admission contract

**State:** independent parser and pinned producer contract **only**. PixelForge PR #88 is still open at producer commit `b74802b358e9c23bc520ef3c0a46699498186c51`. PhiOS must not list PixelForge as a reviewed project adapter or treat its R1 identity sidecar as an active application connection until the producer itself is merged, its actual browser export is inspected, and the PhiOS bridge is separately qualified.

## What actually exists

- **PhiOffice**: reviewed browser app adapter, versioned local manifest, V1 local identity list, V2 metadata copy/rollback, actual separate-origin Chromium permission/revocation evidence.
- **PixelForge VR Studio**: real `pixelforge.vr-world.v1` scenes, local save/JSON export, operator-chosen ID and `pixelforge.phios-vr-world-identity.v0.1` four-field identity-only sidecar **in PR #88**, green producer CI.
- **PhiOS R10 candidate**: `pixelForgeCandidateIdentity.ts` independent parse of the exact sidecar format, refusing arbitrary schema/world versions, extra fields, unsafe IDs, bidirectional/control titles, and oversized JSON. Parsed results are frozen and visibly marked `candidate-only` and `executionAuthority:false`.

The **existing** `REVIEWED_PROJECT_ADAPTERS`, `readProjectIdentityWithAdapter`, V1 and V2 persistent registry codecs, project selectors, localStorage write paths, browser protocol, iframe URLs and permission UI are unchanged. Unknown PixelForge source fields still fail the active v2 registry allowlist. This is not a second working app connection.

## Evidence design

The workflow [PixelForge candidate identity contract](../.github/workflows/pixelforge-candidate-identity.yml) checks out the **exact** PR #88 source commit separately, runs its **real** `newWorld() → buildPhiOSWorldIdentityManifest() → encodePhiOSWorldIdentityManifest()` producer, and requires **byte-identical** JSON with the pinned fixture committed to PhiOS. It then tests PhiOS's **independent** parser, provider namespace collision, and type-check/build. No floating producer branch, network manifest, or plugin registry is permitted.

A test constructs a valid reviewed PhiOffice V2 record with `project:same-project`, parses a PixelForge sidecar with the same literal ID, and requires distinct tuple keys:

- `["phioffice","project:same-project"]`
- `["pixelforge","project:same-project"]`

The test also requires **active PhiOS V2 to refuse PixelForge** and no bridge access or approval carried over. This demonstrates *identity-separation design*, not a successful multi-app browser runtime.

## Admission gates that remain intentionally open

1. **Producer merge:** Review and merge PixelForge PR #88; verify post-merge CI and actual browser export. Only after that may the producer pin be updated to an approved merged source commit.
2. **Real reviewed adapter:** Add a separately reviewed, named `pixelforge` parser to PhiOS with exact source/version matching. Review whether allowing two same-text IDs in V2 requires V1/V2 data-migration and UI changes. V1 remains provider-unqualified and **must not** silently store these candidate references.
3. **Explicit chooser and consent:** Use a PixelForge-specific target and origin, not PhiOffice's frame. Before any project ref crosses frames, establish origin and session binding, operator-selected source and target, and allow/deny/revoke/reconnect semantics. No project contents or private GLB files cross.
4. **Real two-origin Chromium run:** Build the actual merged PixelForge and PhiOS apps from pinned sources; test two provider namespaces, same text IDs, no cross-provider read grants, and protected standalone operation. Record exact commits and counts, not personal world metadata.
5. **Platform boundary:** Native PhiOS installer/device readiness, Quest WebXR, signed app packages, cross-tab localStorage concurrency, durable backups and production publisher authentication remain separate gates.

## Operator runbook

```sh
cd phishell
npm ci --no-audit
npx vitest run src/shell/pixelForgeCandidateIdentity.test.ts
npm run build
```

The pinned cross-repository test runs on the GitHub candidate workflow and must pass at the PR head before reviewer signoff.

**No merge, permission, registry migration, installer, release, live website update or background workflow dispatch is performed by R10.**
