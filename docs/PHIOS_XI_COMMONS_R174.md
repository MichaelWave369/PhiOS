# R17.4 · Xi ⇄ Φ Commons public source tile in PhiOS

**Status:** bundled **offline catalog description** only. The Xi Commons Gateway web app has **not** been bundled as an offline-launchable PhiOS app, nor has a real Xi partner endpoint been authenticated.

The existing PhiShell `Φ ECOSYSTEM` public-source catalog now includes a clearly separated Xi ⇄ Φ Common collaboration reference panel (`XiCommonsSourceTile.tsx`). It uses the same tested, source-only boundary as the existing public repository catalog:

- **Canonical public source:** `https://github.com/MichaelWave369/xi-vessel-bridge`
- **Gateway design and publishing instructions:** `https://github.com/MichaelWave369/xi-vessel-bridge/blob/main/docs/XI_COMMONS_GATEWAY_R173.md`
- **Offline availability:** only the text and source URLs of this PhiShell catalog tile, which ship in the compiled shell; the Xi-Phi website, scripts and partner files are *not* in the PhiOS image.
- **Known local evidence:** R15 read-only porch fixture; R16 signed two-process loopback fixture.
- **Unresolved external evidence:** R17 partner crossing **BLOCKED**; R18 real two-host pilot **NOT RUN**.
- **Launch status:** `installed=false`, `launchAuthorized=false`, `bundledWebApp=false`, `repoWriteAuthorized=false`, `liveXiConnected=false`.

This is intentionally not inserted into `app-candidates.json`, the v0.25–v0.58 App Platform lifecycle, XDG desktop entries or runtime permission broker. The public static Gateway is now independently verified through R17.5, but that does not permit PhiOS to install, bundle, or invoke any Xi-side function.

## Human-led future promotion

**R17.6 update (2026-10-25):** The website is now verified at `https://michaelwave369.github.io/xi-vessel-bridge/` by GitHub Actions run `40243474173` (both deploy and verify jobs succeeded; public handoff manifest SHA-256 `a85309f577e73d20b96fb1442f1f6d0628195805033b456fa81aa39fda9647f3`). PhiOS provides the verified website **as an ordinary user-clicked external link**, alongside the canonical GitHub source. This does not add a web app to the PhiOS offline bundle. Complete source/dependency/install review and explicit operator consent remain prerequisites for any future native app promotion.

Nothing from Hunter's side is required to view this source tile, and an offline PhiOS boot can display the catalog text without making network requests. Following either the public website or GitHub source link while offline naturally requires internet connectivity.

The `public-ecosystem-catalog.yml` GitHub Action now checks this tile's scope, refuses accidental installation/authority claims, and requires the tile's honest labels in the bundled offline shell JavaScript.

**Capability ≠ Authority · Both houses keep their keys.**
