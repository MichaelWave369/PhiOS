# PhiOS Reviewed Project Adapter Catalog R1

**Stage:** compile-time allowlist + local identity projections only.

The portable registry already stores IDs, titles and reviewed source labels.
This rung makes that source review explicit through the typed
`projectAdapters.ts` and `projectAdapterReader.ts` modules, rather than
assuming any imported JSON claim of compatibility is trustworthy.

## Reviewed adapter inventory

| Adapter ID | Provider | Allowed destination | Source | Scope |
|---|---|---|---|---|
| `phioffice-manifest-bridge-v1` | PhiOffice | PhiOffice | `phioffice369.project_manifest.v0.1` | Operator-selected local manifest → project ID only |

There is **one** reviewed adapter. PhiID, PhiCloud and other PhiOS apps are
**not** registered or implied to be connected. The visible adapter catalog
in the existing, opt-in PhiOffice pilot reflects actual source-code
inventory, not an app installer, runtime probe or verified service status.

## Exact trust boundaries

1. The adapter catalog is immutable reviewed code. It is never generated
   from a user-supplied manifest, downloaded plugin descriptor or cloud
   response.
2. Each entry declares an exact source schema, provider application,
   intended consumer application, existing workspace bridge protocol,
   operator-selected input, and opaque-reference-only transfer. It
   explicitly declares `executionAuthority: false`.
3. `readProjectIdentityWithAdapter` dispatches only known source-code
   implementations. The PhiOffice reader uses the established strict
   v0.1 manifest header validator and returns **exactly**
   `projectRef/title/source`.
4. The saved browser registry, portable export/import parser, and active
   selection all validate their source through the same reviewed catalog.
5. The existing browser bridge UI denies project-ID sharing if the saved
   source is not admitted for the target application.
6. This check is a **compatibility gate**, not authorization. The
   operator must still explicitly approve a reference in the current
   origin-bound, frame-bound, ephemeral workspace session.
7. An opaque project ref is never a credential, an authenticated
   ownership claim or permission to open project files. No token, path,
   manifest content, artifact inventory or cloud operation crosses.

## Adding a future app

A new source is admitted **only after** reviewing its real format, adding
a named parser, extending the statically allowlisted adapter catalog,
planning provider-qualified identity collision rules, adding malformed
input and permission-injection tests, and passing a real browser
integration check with that exact app. Introducing a descriptor alone
is not enough.

The current local registry uses `projectRef` as its uniqueness key.
Cross-provider collisions must be rejected or migrated through a new
versioned storage contract before admitting a second active provider.
**Do not** assume `project:alpha` in two unrelated applications
identifies the same entity.

## Verification

```sh
cd phishell
npm ci
npm test
npm run build
```

Tests cover the sealed catalog, exact source/target matching, rejection of
fake provider claims, strict reader dispatch, metadata-only projections and
malformed project manifests. The PhiOffice two-app Chrome acceptance is
the companion gate: it verifies that the visible panel contains only the
reviewed PhiOffice adapter, no unreviewed source can be imported, and
fresh approval is still necessary for any reference reply.

This is **not** a PhiID/PhiCloud integration and does not attest
ownership, remote endpoints or installed application packages.
