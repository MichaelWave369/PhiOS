# PhiOS Public Ecosystem Catalog v0.58 (source-only foundation)

## Mission

Make **all discoverable public GitHub repositories from `MichaelWave369` visible inside the PhiOS desktop environment**, including when the PhiOS ISO starts **offline**, without automatically installing, executing, re-licensing, or copying third-party artifacts.

PhiOS is already a real Linux/Wayfire/PhiShell system and already has a strict, separate App Platform v0.25–v0.57 lifecycle. **Do not build a second installer or bypass those reviewed authority gates.**

## Implemented in this rung

- `phishell/src/ecosystem/public-repos.json` is a deterministic offline public-source snapshot. At the initial discovery point there are **132 founder-owned public GitHub repository entries**. The initial source was the GitHub repository search result filtered by **exact owner** and **visibility=public**, across returned pages. The total is a snapshot, not a promise it never changes.
- `phishell/src/components/EcosystemCatalog.tsx` adds a searchable/paged **Φ ECOSYSTEM** collection inside the existing Apps window. Each entry links only to its public GitHub source. Two previously known public web destinations (SuperPhiVessel Vessie React, ThinkTank) offer an additional explicit external site link; these are **not installed or offline-runnable apps**.
- No automatic GitHub requests on shell startup; no network is needed to view/search the snapshot; no repos cloned; no packages installed; no source executed. The shell's existing shipped-app claims and desktop catalog remain intact.
- Every source entry contains `availability:SOURCE_ONLY`, `installed:false`, `launch_authorized:false`, and `redistribution_reviewed:false`. This catalog is **not** a v0.25 `AppManifest`, installed-app receipt, XDG desktop launcher grant, or ActionLease. No permission upgrade can be inferred.
- `python scripts/sync_public_ecosystem_catalog.py --check` validates the **committed** catalog using no network. `--refresh` is an **explicit operator action** that queries the public, paginated GitHub REST owner endpoint, strictly verifies `private:false`, exact owner and canonical repo URL and then replaces the snapshot **only after complete collection and validation**. Review that source diff before merging to an ISO branch.
- `public-ecosystem-catalog.yml` runs offline validation, negative tests and the real PhiShell React/TypeScript production build. It checks the resulting JS assets contain the repo catalog, which is included in the packaged `phishell/dist` of the existing Linux ISO build.

## Visibility is not application readiness

All public repos appear as **source entries**, including libraries, reference implementations, documentation, research tools, CLI code, experimental demos, and runnable React projects. GitHub visibility does NOT prove:

1. A GUI application exists or has a working Linux build/entrypoint.
2. Its license is compatible with redistribution, or its dependencies can be redistributed.
3. It is safe to run, suitable for the target x86_64 Linux image, or compatible with Chromium/Wayland/installed toolchains.
4. A deployment URL is available, reachable offline, or functional.
5. PhiOS has ever installed, launched, reviewed, or granted execution authority to the app.

Source catalog visibility deliberately cannot call the App Platform install or launch surfaces.

## Evolution to actual executable PhiOS ecosystem apps

**Stage A (this PR):** Offline all-public-source catalog + search + explicit source/web navigation. Works on installed PhiShell once a new ISO/installed-package build is actually produced.

**Stage B:** Create reviewed per-project **application declarations** for projects that are real web/desktop/CLI apps. Use the existing v0.25 strict manifest schema with pinned source, honest license expression/redistribution status, explicit runtime and requested permissions. Distinguish `browser_link_only` from a truly bundled offline PWA/static app, Node service, native binary or Python CLI. Unknown is held, not guessed.

**Stage C:** Use existing v0.26–v0.57 App Platform intake, acquisition, sandboxed build, install, desktop launch, updates and rollback gates. Only verified-ready installed desktop bundles reach the governed v0.39 desktop app catalog and the OS launcher. Vessie/ThinkTank inference requires its existing separately approved localhost/model provider design and is not a browser or ISO authority shortcut.

**Stage D:** Provide a reviewed **PhiOS Ecosystem Pack** build profile: lightweight core PhiOS ISO, optionally selected/size-budgeted reviewed app bundles on the install media, and optional post-install app collection available online. Pinned commits, exact build receipts, signed package metadata where supported, offline dependency caches, storage budgets and first-boot installation approvals must be designed separately. Bundling **all GitHub repositories** into one ISO unreviewed would be expensive and unsafe; this is expressly not implemented now.

**Stage E:** Rebuild and qualify the **actual Linux image** under the existing QEMU boot/install/recovery and release checks. A green PhiShell web build alone does not prove a new ISO boots or ships all executable apps.

## Verification

From repository root:

```sh
python scripts/sync_public_ecosystem_catalog.py --check
python -m unittest discover -s tests -p 'test_public_ecosystem_catalog.py' -v
cd phishell
npm ci --no-audit --no-fund
npm test
npm run build
```

To refresh the public snapshot deliberately:

```sh
python scripts/sync_public_ecosystem_catalog.py --refresh
git diff -- phishell/src/ecosystem/public-repos.json
```

The refresh uses GitHub's public API only and has no credentials; API rate limits apply. Nothing refreshes automatically and new repos will appear in new ISO builds only after their refreshed snapshot is reviewed and merged.

**Ledger Above Ego. DONE Means Verified.**
