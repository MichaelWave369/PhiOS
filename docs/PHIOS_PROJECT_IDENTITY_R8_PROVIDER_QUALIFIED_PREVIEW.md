# PhiOS R8: Provider-Qualified Project Identity Preview (Browser Only)

**Status:** candidate for review. Not an active v2 registry, an app installer, a PhiID integration, or a release authorization.

## Why

PhiShell's existing `phios.project-registry.v1` and `phios.project-references` portable bundle use `projectRef` as a global browser-local identity key. If another application independently uses the same `project:...` ID, the v1 registry cannot safely distinguish the two providers.

R8 introduces a **separate, read-only proposed v2 format**, where lookup identity is the pair `[providerAppId, projectRef]`. The review-only preview derives `providerAppId` from the compile-time, reviewed adapter catalog. It will never trust a provider field supplied by arbitrary import JSON.

### Current scope

The only active reviewed adapter remains PhiOffice's `phioffice369.project_manifest.v0.1` source, with `providerAppId=phioffice`.

The new `projectRegistryV2.ts` exposes:
- `providerQualifiedProjectKey(providerAppId, projectRef)`: collision-free tuple lookup; not a URL, wire token or credential.
- `validateQualifiedProjectEntry`: exact **four metadata fields** (`providerAppId/projectRef/title/source`), with exact existing source allowlist and source-to-provider binding.
- `decodeProjectRegistryV2` / `encodeProjectRegistryV2`: 16 KiB, 24 entries, exact schema/version/field allowlist, no duplicate pairs or any grants.
- `previewV1ToV2Migration`: v1 input validation, reviewed adapter attribution, immutable preview, **zero storage writes**, **zero approval transfer**, refusal if any destination v2 bytes already exist.

The existing v1 store, v1 portable file format, default app selection, cross-origin v1 protocol and browser consent mechanism remain unchanged. Merely inspecting a project does not migrate it.

### Operator-visible preview

In the opt-in, explicitly configured PhiOffice bridge pilot, click **Preview provider-qualified project IDs**. The UI reads local browser registry bytes only after that click and shows `phioffice / project:...` for reviewed local entries.

There is **no migrate/confirm/write action**. The UI clears its preview after remembering, forgetting, clearing or importing local references and after disconnect. The v2 schema cannot be populated by arbitrary import descriptors or network responses.

### Security and future admission gates

A second provider **remains unregistered**. Before admitting a real second app:

1. Review its authentic versioned identity manifest and named source parser; check privacy, consent and legal provenance.
2. Define user-visible v1→v2 migration including explicit confirmation, no overwrite, rollback/export, and collision handling when a v2 target already exists.
3. Include both provider namespaces in an actual test only after the second source has passed independent review; ensure that matching text IDs remain two distinct records.
4. Rebuild two independent browser apps, perform a real Chromium end-to-end test with explicit source selection, denial, fresh consent, and revoke/reconnect.
5. Separately qualify any PhiOS native install/signature/hardware requirements. Browser identity metadata never means native app installation.

**Acceptance:** `cd phishell && npm ci && npm test && npm run build`. The R8 unit test must prove that unknown providers, injected rights, mismatched provider/source, duplicate pairs, malformed v2 storage, excessive byte size and existing-v2 overwrite are all rejected. The normal PhiOffice v1 Chrome bridge remains supported by design, but R8 itself does not qualify a second provider.

No secrets, cloud accounts, PhiID grants, native files or model identities are involved.
