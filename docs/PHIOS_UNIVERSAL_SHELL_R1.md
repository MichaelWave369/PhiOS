# Φ Universal Shell R1 — One catalog, three honest runtimes

**Status:** proposed interoperability contract and public snapshot reader. This does **not** release a bootable native OS, a flashable Android image, or a universal GitHub installer.

## Product target

A recognizable PhiOS desktop, mobile Home, and browser desktop with the **same public application identities, discovery semantics, portability principles and user-visible capability statuses**.

| Surface | Boot model | GUI | App action at R1 |
|---|---|---|---|
| PhiOS Web | PWA/service worker on browser origin | Existing `phi-field.com/os/` desktop | Browse public source; user-initiated website navigation where independently qualified |
| PhiOS Mobile browser | Browser/PWA on Android or another phone | Existing touch PhiShell | Browse public source; native Android apps are not installed by web JavaScript |
| PhiOS Mobile native | Android boots; PhiOS is a user-selectable HOME APK | Existing Android launcher | Discover and launch **already installed** current-user apps; package installation requires separate Android workflow, consent and policy |
| PhiOS Linux | x86_64 UEFI VM-tested experimental Arch/Wayfire/PhiShell image | Actual Wayland session | Governed source intake, exact source/build/launch/install gates; public OS release and physical hardware remain held |

The three targets share **semantic shell + catalog contracts**, not identical kernels or privileges.

## Public source inventory contract

Canonical pinned snapshot: `interop/public-repo-catalog.v1.json`.

- Derived solely from **FieldConstellation `src/repos.json`**, public scope, complete at the recorded **2026-11-04** identity snapshot.
- **225 public repositories**, not all repositories in the connected GitHub account; private, renamed after the snapshot, newly created and otherwise inaccessible repositories are not represented.
- Stable GitHub numeric ID (`github:123`) and public repository URL are cross-platform identities. Repositories are sorted for discovery, not install priority.
- `declared_homepage` is **unverified owner metadata**. Do not silently navigate or represent it as a qualified live launch surface. May include HTTP and broken pages; applications should prefer the exact source URL.
- `availability: "source_only"` and global `review_required: true`, `automatic_install: false`, `automatic_launch: false`, `cross_platform_qualification: false` deliberately bind zero install authority.
- Copies to browser/mobile builds must preserve the same schema and `source_blob_sha` and be tested for ID set equality. New snapshots require explicit refresh, privacy review, provenance and release step.
- The offline Python reader `python interop/shell_catalog_v1.py --search PhiOS` validates the snapshot and prints source locations; it has **no network, installer, environment mutation or runtime authority**.

## Runtime actions and evidence (future shared app manifest)

1. **DISCOVERED:** repository appears in a public catalog. No installation claims.
2. **WEB URL DECLARED:** owner homepage metadata exists. Until navigational verification, it is an unverified external website address.
3. **WEB LAUNCH QUALIFIED:** a reviewer has verified the exact HTTPS endpoint, compatibility/security policy and successful browser acceptance for the target browser, with dated receipt.
4. **NATIVE CANDIDATE:** governed `phi-app profile-github` and separate exact source, license, toolchain and sandbox review pass. A green profiler alone does not install.
5. **INSTALLED ON THIS DEVICE:** actual platform package-manager or app-registry state observed locally with signed/hashed provenance; not inferred from a public repository.
6. **LAUNCH AUTHORIZED:** explicit action permission on this device/session under platform's authority rules. Not implicit in installation.

**Never:** treat a GitHub URL, README, repo license, CI badge, or a declared website homepage as proof the program can be installed. Android/desktop/browser have different execution formats. When not qualified, show **VIEW SOURCE** and optionally **REQUEST REVIEW**, not **INSTALL**.

## Three separately mediated installation adapters

- **Web:** an independently qualified same-origin PWA bundle or a user-requested external web app launch. Browser PWA installation belongs to the browser; pinning a repository shortcut is **not** an app install.
- **Mobile:** native Android installed-app discovery/launch uses existing LauncherApps APIs; future package installs must go through an explicit Android package installer and per-device user confirmation. No silent APK sideloading, firmware flash or default-Home takeover.
- **Linux:** existing PhiOS App Platform governable intake/source acquisition/build/install/launch chain. Requests must bind source commit, manifest, license, sandbox plan, evidence, explicit human authorization and receipts.

Private account repositories can be added to an operator's **local authenticated private catalog** later; they must never leak through public JSON, static GitHub Pages, or Netlify.

## Acceptance ladder

- R1: pinned, typed, public **source-only** catalog and strict validation tests (this PR)
- R2: browse/catalog UI in Web and Mobile, same source set and clear freshness; read-only external links, no fake installs
- R3: user-pinned shortcuts with **portable app shelf backup**; equal identities but origin-scoped data, no silent sync
- R4: verified browser app descriptors + explicit launch; audit each actual endpoint and license
- R5: native Linux install-gate integration and Android installed-app registry display, independent of web's shortcuts
- R6: device-specific signed install and rollback qualification; physical hardware tests before release

Native Linux release **still blocked** by the exact artifact source/license, signing and physical-support gates in `docs/os/RELEASE_CONTRACT.md` and `docs/os/IMPLEMENTATION_STATUS.md`. GitHub repository count is *inventory*, not a release-readiness score.

**Non-negotiable:** Capability != authority. Installed != runnable. Public source != permission to redistribute.
