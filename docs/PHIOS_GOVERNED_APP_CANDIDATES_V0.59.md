# PhiOS v0.59: First-Wave Governed Application Candidates

## Status: SOURCE-REVIEW ONLY, ZERO INSTALL/LAUNCH AUTHORITY

PhiOS v0.58 merged an offline catalog of 132 public first-party repositories into the
existing PhiShell Apps window. v0.59 now nominates **Vessie Web** and **Φ ThinkTank**
as the first two *proposed executable applications*, without pretending they have
been installed or that their redistribution, offline assets, dependencies or
runtime environment have passed independent review.

## Immutable first-wave sources

| App | Pinned source commit | Proposed runtime | Existing upstream build |
| --- | --- | --- | --- |
| Vessie | `69a558ea2d1e8b361e05ded9bed4fc27b32e30cd` | static_web; `index.html` in a future reviewed bundle | `apps/vessie-web: npm run build` → `site/vessie`, asset base `/SuperPhiVessel/vessie/` |
| ThinkTank | `1e8084a684ccf400c37d05d8bfe992680a72e887` | static_web; `index.html` in a future reviewed bundle | repo root: `npm run build` → `dist`, asset base `/` |

Each proposal includes a complete, parseable PhiOS `phios.app_manifest.v0.1`
declaration, a proposed runtime/build path, immutable source commit, explicit
preparation gaps and an existing public website reference. The source licenses
have a declared MIT expression, but **redistribution remains `unknown`** until
the actual transitive dependency and asset license inventory is reviewed.
`permissions:[]` means **none declared**, *not* an independently verified
zero-capability sandbox.

The manifests live in
`phishell/src/ecosystem/app-candidates.json` and are shown in the existing
PhiShell Apps window as **HELD_FOR_OPERATOR_REVIEW / NOT INSTALLED**.
Source review links are pinned to the exact commit and not the moving main branch.

## Absolutely not done by this PR

- No GitHub archive acquisition, cloning, package download or automatic refresh
- No compiler, bundler, program, AI model, service or browser execution
- No AppRegistry enrollment saved to the installed OS
- No v0.27 onward dependency/build/sandbox/install receipt fabrication
- No v0.38 desktop-launch grant, live-browser authority, provider-bridge permission, API key or local Ollama deployment
- No broad assertion that all 132 source entries are compatible or runnable
- No new installer or shortcut that bypasses App Platform v0.25–v0.57

The Python validator uses `AppManifest.from_dict` and an **ephemeral, in-memory**
`AppRegistry` to verify the frozen schema, duplicate IDs and canonical manifest
digests. It compares source repositories to the v0.58 public catalog, checks
fixed SHA-1 source pins, and refuses any false installed, build-verified,
launch-authorized, redistribution-approved or external-DONE flags.
This does not create a registry record in the OS.

## Practical promotion checklist, starting with Vessie and ThinkTank

1. **Verify exact source revision and third-party licenses.** Reconcile transitive
   npm dependencies, runtime asset redistribution, and future update rights.
2. **Produce a relocatable offline frontend.** Vessie's current Pages bundle
   embeds the `/SuperPhiVessel/vessie/` asset base and must be built with a
   separately reviewed offline-root base. ThinkTank's plain build currently
   targets `/` but still needs actual offline installation verification.
3. **Review dependencies and control-plane boundaries.** The React frontends
   cannot import host model execution authority just because they are installed.
   ThinkTank's local bridge and Vessie's model providers require separate
   operator-controlled runtime agreements; no cloud keys in client bundles.
4. **Run the established App Platform.** The v0.26 acquisition/intake,
   build-plan, backend qualification, one-use execution lease, artifact
   inspection, sandbox, install, v0.38 desktop plan/grant and v0.39 catalog
   are existing authorities. Verify the recorded lineage before promotion.
5. **Qualify an app-enabled ISO.** Rebuild the exact PhiShell/OS packages from
   reviewed sources, qualify image boot, desktop launch, app window, offline
   startup, rollback/recovery and permission refusal in real QEMU.
6. **Expand across the public source catalog** only when each repo has a
   legitimate software runtime. Documentation, research assets, shared
   libraries, and non-GUI tools remain source/resources rather than fake apps.

## Verification

```sh
python scripts/sync_public_ecosystem_catalog.py --check
python scripts/verify_ecosystem_app_candidates.py
python -m unittest discover -s tests -p 'test_ecosystem_app_candidates.py' -v
cd phishell
npm ci --no-audit --no-fund
npm test
npm run build
```

The dedicated PhiOS ecosystem CI checks the compiled PhiShell assets contain
both proposed app IDs. Regular PhiOS qualification still runs independently.
A green v0.59 pipeline proves **reviewable candidate metadata and a rendered
catalog**, not two installed executable PhiOS apps.

**Ledger Above Ego. DONE Means Verified.**
